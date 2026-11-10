import json
import re
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
import requests
import edge_tts

HEADERS = {"User-Agent": "AICompanyVideoStudio/1.0 (personal project)"}
VIDEO_EXTS = (".mp4", ".webm", ".ogv", ".ogg", ".mov")

def find_video_clips(topic: str, folder: Path, limit: int = 3):
    terms = [topic]
    low = topic.lower()
    if any(x in low for x in ("stoik", "stoic", "tenang", "mental", "disiplin", "motivasi")):
        terms += ["sunrise nature landscape", "person walking mountain", "calm ocean waves"]
    elif any(x in low for x in ("bisnis", "usaha", "uang", "kerja", "karier")):
        terms += ["business teamwork office", "city timelapse", "working hands computer"]
    elif any(x in low for x in ("trading", "saham", "crypto", "kripto", "bitcoin")):
        terms += ["financial market stock exchange", "computer data screens", "city at night timelapse"]
    else:
        terms += ["cinematic nature landscape", "city timelapse", "person walking outdoors"]
    found, seen = [], set()
    for term in terms:
        if len(found) >= limit:
            break
        params = {
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": "filetype:video " + term, "gsrnamespace": 6,
            "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|extmetadata"
        }
        try:
            response = requests.get("https://commons.wikimedia.org/w/api.php",
                                    params=params, headers=HEADERS, timeout=25)
            response.raise_for_status()
            pages = (response.json().get("query") or {}).get("pages") or {}
        except Exception:
            continue
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("url", "")
            if not url or not url.lower().split("?")[0].endswith(VIDEO_EXTS) or url in seen:
                continue
            seen.add(url)
            try:
                media = requests.get(url, headers=HEADERS, timeout=60)
                media.raise_for_status()
                if len(media.content) < 100_000:
                    continue
                suffix = Path(url.split("?")[0]).suffix.lower()
                target = folder / f"clip_{len(found)+1}{suffix}"
                target.write_bytes(media.content)
                meta = info.get("extmetadata") or {}
                found.append({
                    "file": str(target),
                    "title": page.get("title", ""),
                    "source": info.get("descriptionurl", url),
                    "license": (meta.get("LicenseShortName") or {}).get("value", "Check source page"),
                    "artist": (meta.get("Artist") or {}).get("value", "")
                })
                if len(found) >= limit:
                    break
            except Exception:
                continue
    return found

async def build_package(job_id: str, topic: str, style: str, script: str, subtitles: str,
                        output_zip: Path, voice: str = "id-ID-ArdiNeural"):
    with TemporaryDirectory(prefix="aivideo_") as tmp:
        folder = Path(tmp)
        clips = find_video_clips(topic, folder, 3)
        if len(clips) < 3:
            raise RuntimeError(f"Hanya ditemukan {len(clips)} klip video yang cocok. Butuh 3 klip. Tidak memakai foto acak.")
        audio = folder / "voice.mp3"
        await edge_tts.Communicate(script, voice).save(str(audio))
        (folder / "script.txt").write_text(script, encoding="utf-8")
        (folder / "subtitles.srt").write_text(subtitles, encoding="utf-8")
        attribution = {
            "job_id": job_id, "topic": topic, "style": style,
            "duration_seconds": 60, "resolution": "720x1280",
            "visual_source": "Wikimedia Commons",
            "clips": [{k: v for k, v in item.items() if k != "file"} for item in clips]
        }
        (folder / "metadata.json").write_text(json.dumps(attribution, ensure_ascii=False, indent=2), encoding="utf-8")
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(audio, "voice.mp3")
            archive.write(folder / "script.txt", "script.txt")
            archive.write(folder / "subtitles.srt", "subtitles.srt")
            archive.write(folder / "metadata.json", "metadata.json")
            for item in clips:
                archive.write(item["file"], "clips/" + Path(item["file"]).name)

import json
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import requests
import edge_tts

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "AICompanyVideoStudio/2.0 (https://github.com/Rikogun02/Ai-studio-video)",
    "Accept": "application/json",
}
VIDEO_EXTS = (".mp4", ".webm", ".ogv", ".ogg", ".mov")
MAX_CLIP_BYTES = 18 * 1024 * 1024
CLIP_COUNT = 12


def topic_search_terms(topic: str):
    low = topic.lower()
    if any(x in low for x in ("stoik", "stoic", "tenang", "mental", "disiplin", "motivasi", "emosi")):
        return ["sunrise", "mountain", "ocean", "forest", "walking", "meditation", "sunset", "waves", "nature", "calm", "river", "clouds"]
    if any(x in low for x in ("bisnis", "usaha", "uang", "kerja", "karier", "business")):
        return ["business", "office", "teamwork", "computer", "city", "factory", "working", "technology", "meeting", "industry", "entrepreneur", "commerce"]
    if any(x in low for x in ("trading", "saham", "crypto", "kripto", "bitcoin", "market")):
        return ["stock exchange", "financial market", "computer", "data center", "city", "technology", "business", "trading floor", "charts", "finance", "server", "economy"]
    words = [w for w in topic.split() if len(w) > 4][:4]
    return words + ["nature", "city", "people", "technology", "landscape", "work", "ocean", "forest"]


def _search_video_pages(term: str):
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:video {term}",
        "gsrnamespace": 6,
        "gsrlimit": 50,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
    }
    response = requests.get(API, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"].get("info", "Commons API error"))
    return list((data.get("query") or {}).get("pages", {}).values())


def _download_clip(url: str, target: Path):
    with requests.get(url, headers=HEADERS, timeout=(15, 60), stream=True) as response:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_CLIP_BYTES:
            return False
        total = 0
        with target.open("wb") as output:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_CLIP_BYTES:
                    output.close()
                    target.unlink(missing_ok=True)
                    return False
                output.write(chunk)
        if total < 100_000:
            target.unlink(missing_ok=True)
            return False
    return True


def find_video_clips(topic: str, folder: Path, limit: int = CLIP_COUNT):
    found, seen = [], set()
    errors = []
    terms = topic_search_terms(topic)
    for term in terms:
        if len(found) >= limit:
            break
        try:
            pages = _search_video_pages(term)
        except Exception as exc:
            errors.append(f"{term}: {str(exc)[:120]}")
            continue
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("url", "")
            mime = (info.get("mime") or "").lower()
            clean_url = url.lower().split("?")[0]
            if not url or url in seen:
                continue
            if not (mime.startswith("video/") or clean_url.endswith(VIDEO_EXTS)):
                continue
            seen.add(url)
            suffix = Path(clean_url).suffix.lower()
            if suffix not in VIDEO_EXTS:
                suffix = ".webm" if "webm" in mime else ".ogv"
            target = folder / f"clip_{len(found)+1:02d}{suffix}"
            try:
                if not _download_clip(url, target):
                    continue
                meta = info.get("extmetadata") or {}
                found.append({
                    "file": str(target),
                    "title": page.get("title", ""),
                    "source": info.get("descriptionurl", url),
                    "license": (meta.get("LicenseShortName") or {}).get("value", "Check source page"),
                    "artist": (meta.get("Artist") or {}).get("value", ""),
                })
                if len(found) >= limit:
                    break
            except Exception:
                target.unlink(missing_ok=True)
                continue
    if len(found) < limit and errors and not found:
        raise RuntimeError("Pencarian Wikimedia Commons gagal: " + "; ".join(errors[:2]))
    return found


async def build_package(job_id: str, topic: str, style: str, script: str, subtitles: str,
                        output_zip: Path, voice: str = "id-ID-ArdiNeural"):
    with TemporaryDirectory(prefix="aivideo_") as tmp:
        folder = Path(tmp)
        clips = find_video_clips(topic, folder, CLIP_COUNT)
        if len(clips) < CLIP_COUNT:
            raise RuntimeError(
                f"Hanya ditemukan {len(clips)} dari 12 klip video berbeda yang cocok. "
                "Tidak memakai foto acak atau mengulang klip. Coba topik lebih sederhana atau ulangi nanti."
            )
        audio = folder / "voice.mp3"
        await edge_tts.Communicate(script, voice).save(str(audio))
        (folder / "script.txt").write_text(script, encoding="utf-8")
        (folder / "subtitles.srt").write_text(subtitles, encoding="utf-8")
        attribution = {
            "job_id": job_id, "topic": topic, "style": style,
            "duration_seconds": 60, "resolution": "720x1280",
            "clip_count": CLIP_COUNT, "visual_source": "Wikimedia Commons",
            "clips": [{k: v for k, v in item.items() if k != "file"} for item in clips],
        }
        (folder / "metadata.json").write_text(
            json.dumps(attribution, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(audio, "voice.mp3")
            archive.write(folder / "script.txt", "script.txt")
            archive.write(folder / "subtitles.srt", "subtitles.srt")
            archive.write(folder / "metadata.json", "metadata.json")
            for item in clips:
                archive.write(item["file"], "clips/" + Path(item["file"]).name)

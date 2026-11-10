import json
import os
import time
import textwrap
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import requests
import edge_tts

MAGIC_API = "https://api.magichour.ai"
CLIP_COUNT = 2
CLIP_SECONDS = 5
ESTIMATED_CREDITS_PER_SECOND = 24
RESERVE_CREDITS = 72
MAX_CLIP_BYTES = 50 * 1024 * 1024
POLL_SECONDS = 10
MAX_WAIT_SECONDS = 20 * 60


def _headers():
    key = os.getenv("MAGIC_HOUR_API_KEY", "").strip()
    if not key:
        raise RuntimeError("MAGIC_HOUR_API_KEY belum terpasang di server.")
    return {"Authorization": "Bearer " + key, "Accept": "application/json"}


def _account():
    response = requests.get(
        MAGIC_API + "/v1/account", headers=_headers(), timeout=30
    )
    if response.status_code == 401:
        raise RuntimeError("API key Magic Hour tidak valid.")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data.get("credits"), int):
        raise RuntimeError("Saldo kredit Magic Hour tidak terbaca.")
    return data


def _prompts(topic: str, style: str):
    clean_topic = " ".join(topic.split())[:160]
    low = clean_topic.lower()
    visual_style = (
        "photorealistic cinematic documentary, natural human movement, "
        "soft natural lighting, subtle camera movement, realistic details, "
        "vertical 9:16 composition, no text, no subtitles, no logos, no watermark"
    )
    if any(word in low for word in ("stoik", "stoic", "tenang", "emosi", "disiplin", "motivasi")):
        scenes = [
            "A thoughtful Southeast Asian adult sitting quietly beside a window at dawn, reflecting before starting the day, calm intimate atmosphere",
            "The same type of adult walking with purpose along a misty mountain path at sunrise, gaining perspective and confidence, wide cinematic landscape",
        ]
    elif any(word in low for word in ("bisnis", "usaha", "karier", "kerja", "business", "uang")):
        scenes = [
            "A focused small business owner planning work at a tidy desk, reviewing notes and preparing the day, realistic modern workspace",
            "A small business owner actively working with a team in a bright workshop or office, purposeful collaboration and steady progress",
        ]
    elif any(word in low for word in ("trading", "saham", "crypto", "kripto", "bitcoin", "market")):
        scenes = [
            "A disciplined trader studying financial charts on multiple monitors in a realistic quiet trading workspace, focused and analytical",
            "A close cinematic view of a trader calmly reviewing market data and writing a risk plan, realistic screens with abstract charts and no readable text",
        ]
    else:
        scenes = [
            f"A realistic cinematic scene that clearly illustrates the central idea of {clean_topic}, a person thoughtfully engaging with the subject in a believable setting",
            f"A distinct follow-up scene showing a practical positive outcome or meaningful action related to {clean_topic}, natural people and environment",
        ]
    return [
        f"{scene}. Theme: {clean_topic}. Visual direction: {style}. {visual_style}."
        for scene in scenes
    ]


def _download_video(url: str, target: Path):
    total = 0
    with requests.get(url, headers={"User-Agent": "AICompanyVideoStudio/3.0"},
                      timeout=(20, 120), stream=True) as response:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_CLIP_BYTES:
            raise RuntimeError("Ukuran klip AI melebihi batas 50 MB.")
        with target.open("wb") as output:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_CLIP_BYTES:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise RuntimeError("Ukuran klip AI melebihi batas 50 MB.")
                output.write(chunk)
    if total < 100_000:
        target.unlink(missing_ok=True)
        raise RuntimeError("File video dari Magic Hour terlalu kecil atau tidak valid.")
    with target.open("rb") as source:
        if source.read(8)[4:8] != b"ftyp":
            target.unlink(missing_ok=True)
            raise RuntimeError("Hasil unduhan bukan file MP4 yang valid.")


def _create_clip(prompt: str, name: str, target: Path):
    expected = CLIP_SECONDS * ESTIMATED_CREDITS_PER_SECOND
    account = _account()
    if account["credits"] < expected + RESERVE_CREDITS:
        raise RuntimeError(
            f"Saldo {account['credits']} kredit tidak cukup untuk estimasi "
            f"{expected} kredit sambil menyisakan cadangan {RESERVE_CREDITS}."
        )

    payload = {
        "end_seconds": float(CLIP_SECONDS),
        "aspect_ratio": "9:16",
        "style": {"prompt": prompt},
        "name": name,
        "model": "ltx-2.5",
        "resolution": "480p",
    }
    response = requests.post(
        MAGIC_API + "/v1/text-to-video",
        headers={**_headers(), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if response.status_code == 402:
        raise RuntimeError("Magic Hour menolak job karena kredit tidak mencukupi.")
    response.raise_for_status()
    created = response.json()
    project_id = created.get("id")
    if not project_id:
        raise RuntimeError("Magic Hour tidak mengembalikan ID proyek.")
    charged = created.get("credits_charged")

    started = time.monotonic()
    while time.monotonic() - started < MAX_WAIT_SECONDS:
        time.sleep(POLL_SECONDS)
        check = requests.get(
            f"{MAGIC_API}/v1/video-projects/{project_id}",
            headers=_headers(), timeout=30,
        )
        check.raise_for_status()
        project = check.json()
        status = project.get("status")
        if status == "complete":
            downloads = project.get("downloads") or []
            url = downloads[0].get("url") if downloads else None
            if not url:
                raise RuntimeError("Job selesai tetapi tautan unduhan tidak tersedia.")
            _download_video(url, target)
            return {
                "file": str(target),
                "project_id": project_id,
                "duration_seconds": project.get("end_seconds", CLIP_SECONDS),
                "credits_charged": project.get("credits_charged", charged),
                "prompt": prompt,
            }
        if status in ("error", "canceled"):
            raise RuntimeError(f"Generasi Magic Hour berstatus {status}: {project.get('error')}")
    raise RuntimeError(
        f"Job Magic Hour {project_id} belum selesai setelah 20 menit. "
        "Jangan kirim ulang otomatis; periksa proyek di akun Magic Hour."
    )


def _srt_stamp(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, millis = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _subtitles_from_word_boundaries(boundaries):
    """Build readable two-line captions using the actual TTS word timestamps."""
    if not boundaries:
        raise RuntimeError("TTS tidak mengirim penanda waktu kata; subtitle sinkron tidak dapat dibuat.")

    groups = []
    current = []
    for item in boundaries:
        word = str(item.get("text", "")).strip()
        if not word:
            continue
        candidate = current + [item]
        phrase = " ".join(str(x.get("text", "")).strip() for x in candidate)
        wrapped = textwrap.wrap(phrase, width=30, break_long_words=False, break_on_hyphens=False)
        if current and (len(candidate) > 7 or len(wrapped) > 2):
            groups.append(current)
            current = [item]
        else:
            current = candidate
    if current:
        groups.append(current)

    entries = []
    for index, group in enumerate(groups, 1):
        phrase = " ".join(str(x.get("text", "")).strip() for x in group)
        wrapped = textwrap.wrap(phrase, width=30, break_long_words=False, break_on_hyphens=False)
        start = int(group[0]["offset"]) / 10_000_000
        end = (int(group[-1]["offset"]) + int(group[-1]["duration"])) / 10_000_000
        if end <= start:
            continue
        entries.append(
            f"{index}\\n{_srt_stamp(start)} --> {_srt_stamp(end)}\\n"
            + "\\n".join(wrapped[:2]) + "\\n"
        )
    if not entries:
        raise RuntimeError("Penanda waktu TTS tidak valid; subtitle tidak dibuat.")
    return "\\n".join(entries)


async def build_package(job_id: str, topic: str, style: str, script: str,
                        output_zip: Path,
                        voice: str = "id-ID-ArdiNeural"):
    with TemporaryDirectory(prefix="aivideo_") as tmp:
        folder = Path(tmp)
        clips = []
        warning = None
        for index, prompt in enumerate(_prompts(topic, style), 1):
            target = folder / f"ai_clip_{index:02d}.mp4"
            try:
                clips.append(_create_clip(
                    prompt, f"AI Company - {topic[:55]} - Scene {index}", target
                ))
            except Exception as exc:
                if not clips:
                    raise
                warning = f"Klip kedua tidak dibuat: {str(exc)[:240]}"
                break

        audio = folder / "voice.mp3"
        communicate = edge_tts.Communicate(script, voice, boundary="WordBoundary")
        word_boundaries = []
        with audio.open("wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    word_boundaries.append({
                        "offset": int(chunk["offset"]),
                        "duration": int(chunk["duration"]),
                        "text": chunk["text"],
                    })
        subtitles = _subtitles_from_word_boundaries(word_boundaries)
        (folder / "script.txt").write_text(script, encoding="utf-8")
        (folder / "subtitles.srt").write_text(subtitles, encoding="utf-8")
        metadata = {
            "job_id": job_id,
            "topic": topic,
            "style": style,
            "duration_seconds": 60,
            "resolution": "720x1280",
            "clip_count": len(clips),
            "visual_source": "Magic Hour AI text-to-video",
            "model": "default",
            "clip_resolution": "480p",
            "clip_duration_seconds": CLIP_SECONDS,
            "credits_reserve_target": RESERVE_CREDITS,
            "warning": warning,
            "clips": [
                {key: value for key, value in item.items() if key != "file"}
                for item in clips
            ],
        }
        (folder / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(audio, "voice.mp3")
            archive.write(folder / "script.txt", "script.txt")
            archive.write(folder / "subtitles.srt", "subtitles.srt")
            archive.write(folder / "metadata.json", "metadata.json")
            for item in clips:
                archive.write(item["file"], "clips/" + Path(item["file"]).name)

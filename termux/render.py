#!/usr/bin/env python3
"""Render a 60-second AI Company video locally on Android/Termux."""
import argparse
import array
import html
import math
import re
import shutil
import subprocess
import textwrap
import wave
import zipfile
from pathlib import Path

DURATION = 60.0
SCENE_COUNT = 12
TRANSITION = 0.55
FONT = "/system/fonts/Roboto-Regular.ttf"
LOCAL_AI_NAMES = ("output (1).mp4", "output (2).mp4", "output (3).mp4")


def run(cmd):
    subprocess.run(cmd, check=True)


def timestamp(value):
    h, m, rest = value.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def subtitle_files(srt_path, folder):
    raw = srt_path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", raw.strip())
    cues = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing = next((line for line in lines if "-->" in line), None)
        if not timing:
            continue
        left, right = [part.strip().split()[0] for part in timing.split("-->")]
        caption = html.unescape(
            re.sub(r"<[^>]+>", "", "\n".join(lines[lines.index(timing) + 1:]))
        ).strip()
        if not caption:
            continue
        start, end = timestamp(left), timestamp(right)
        if end <= start:
            continue
        wrapped = textwrap.wrap(
            caption, width=30, break_long_words=False, break_on_hyphens=False
        )
        # The API package builder limits cues to two lines; keep a safe visual cap.
        if len(wrapped) > 2:
            wrapped = wrapped[:2]
        path = folder / ("subtitle_%03d.txt" % len(cues))
        path.write_text("\n".join(wrapped), encoding="utf-8")
        cues.append((start, end, path))
    return cues


def ffmpeg_path(path):
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def write_original_music(path, duration=60):
    """Create a gentle original plucked instrumental; no stock track or pure drone."""
    sample_rate = 22050
    total = int(sample_rate * duration)
    chords = [
        (220.00, 261.63, 329.63, 110.00),   # Am
        (174.61, 220.00, 261.63, 87.31),    # F
        (130.81, 164.81, 196.00, 65.41),    # C
        (196.00, 246.94, 293.66, 98.00),    # G
    ]
    samples = array.array("h")
    for index in range(total):
        t = index / sample_rate
        chord = chords[int(t // 4) % len(chords)]
        beat = int(t / 0.5)
        note = chord[beat % 3]
        local = t - beat * 0.5
        envelope = math.exp(-5.0 * local)
        pluck = (
            math.sin(2 * math.pi * note * t)
            + 0.30 * math.sin(2 * math.pi * note * 2 * t)
            + 0.12 * math.sin(2 * math.pi * note * 3 * t)
        ) * envelope
        pad = sum(math.sin(2 * math.pi * f * t) for f in chord[:3]) / 3
        bass = math.sin(2 * math.pi * chord[3] * t)
        value = max(-0.8, min(0.8, 0.17 * pluck + 0.055 * pad + 0.035 * bass))
        sample = int(value * 32767)
        samples.append(sample)
        samples.append(sample)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


def collect_clips(work):
    packaged = sorted((work / "clips").glob("*.mp4"))
    if not packaged:
        raise SystemExit("Paket tidak berisi klip AI MP4.")
    # Reuse the three AI clips already created on this phone, if they still exist.
    downloads = Path.home() / "storage" / "downloads"
    local = []
    for name in LOCAL_AI_NAMES:
        candidate = downloads / name
        if candidate.is_file() and candidate.stat().st_size > 100_000:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(candidate)],
                capture_output=True, text=True
            )
            try:
                clip_duration = float(probe.stdout.strip())
            except (TypeError, ValueError):
                clip_duration = 0.0
            # Very short legacy clips loop visibly and are not used in the final cut.
            if probe.returncode == 0 and clip_duration >= 4.5:
                local.append(candidate)
    return packaged + local, len(packaged), len(local)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", help="Path to the downloaded .zip package")
    parser.add_argument(
        "--output",
        default=str(Path.home() / "storage" / "downloads" / "AICompanyVideo.mp4"),
    )
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("FFmpeg belum terpasang. Jalankan: pkg install ffmpeg")

    work = Path.home() / ".ai_company_video" / "current"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.package) as archive:
        archive.extractall(work)

    clips, packaged_count, local_count = collect_clips(work)
    voice = work / "voice.mp3"
    srt = work / "subtitles.srt"
    if not voice.exists() or not srt.exists():
        raise SystemExit("Paket harus berisi voice.mp3 dan subtitles.srt.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    subtitle_dir = work / "subtitle_text"
    subtitle_dir.mkdir(exist_ok=True)
    cues = subtitle_files(srt, subtitle_dir)
    music_file = work / "original_music.wav"
    write_original_music(music_file, DURATION)
    outro_text = work / "outro.txt"
    outro_text.write_text("JAGA PRINSIP.\nTERUS BERTUMBUH.", encoding="utf-8")

    # Twelve short scenes cycle through the available AI-generated clips.
    scene_sources = [clips[index % len(clips)] for index in range(SCENE_COUNT)]
    scene = (DURATION + (SCENE_COUNT - 1) * TRANSITION) / SCENE_COUNT
    inputs = []
    for clip in scene_sources:
        inputs += ["-stream_loop", "-1", "-i", str(clip)]
    voice_index = SCENE_COUNT
    music_index = SCENE_COUNT + 1
    inputs += ["-i", str(voice), "-i", str(music_file)]

    filters = []
    for index in range(SCENE_COUNT):
        filters.append(
            f"[{index}:v]scale=720:1280:force_original_aspect_ratio=increase,"
            f"crop=720:1280,setsar=1,fps=25,trim=duration={scene:.4f},"
            f"setpts=PTS-STARTPTS,format=yuv420p[v{index}]"
        )

    current = "[v0]"
    offset = scene - TRANSITION
    for index in range(1, SCENE_COUNT):
        label = f"[xf{index}]"
        filters.append(
            f"{current}[v{index}]xfade=transition=fade:duration={TRANSITION}:"
            f"offset={offset:.4f}{label}"
        )
        current = label
        offset += scene - TRANSITION
    filters.append(f"{current}trim=duration=60,setpts=PTS-STARTPTS[vbase]")
    current = "[vbase]"

    # Captions are centered, limited to two lines, and kept clear of the bottom edge.
    for index, (start, end, path) in enumerate(cues):
        label = f"[sub{index}]"
        filters.append(
            f"{current}drawtext=fontfile={FONT}:textfile='{ffmpeg_path(path)}':"
            f"expansion=none:fontcolor=white:fontsize=38:line_spacing=10:"
            f"borderw=2:bordercolor=black@0.65:"
            f"x=(w-text_w)/2:y=h*0.73-text_h/2:"
            f"box=1:boxcolor=black@0.58:boxborderw=18:"
            f"enable='between(t,{start:.3f},{end:.3f})'{label}"
        )
        current = label

    # Clean animated intro: subtle dark overlay, fade and upward movement.
    filters.append(
        f"{current}drawbox=x=0:y=0:w=iw:h=ih:color=black@0.40:t=fill:"
        "enable='between(t,0,2.6)'[introbg]"
    )
    filters.append(
        "[introbg]drawtext=fontfile=" + FONT +
        ":text='RUANG GAGASAN':fontcolor=white:fontsize=62:"
        "borderw=1:bordercolor=black@0.35:x=(w-text_w)/2:"
        "y=h*0.40+22*(1-t/2.6):"
        "alpha='if(lt(t,0.55),t/0.55,if(lt(t,2.05),1,(2.6-t)/0.55))':"
        "enable='between(t,0,2.6)'[introtitle]"
    )
    filters.append(
        "[introtitle]drawtext=fontfile=" + FONT +
        ":text='BERPIKIR JERNIH  |  BERTINDAK BIJAK':"
        "fontcolor=white@0.92:fontsize=22:x=(w-text_w)/2:y=h*0.48:"
        "alpha='if(lt(t,0.8),(t-0.35)/0.45,if(lt(t,2.0),1,(2.6-t)/0.6))':"
        "enable='between(t,0.35,2.6)'[intro]"
    )

    # Outro uses a soft blur, dark overlay, and a two-line closing statement.
    filters.append(
        "[intro]boxblur=18:2:enable='between(t,57,60)',"
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.52:t=fill:"
        "enable='between(t,57,60)'[outrobg]"
    )
    filters.append(
        "[outrobg]drawtext=fontfile=" + FONT +
        f":textfile='{ffmpeg_path(outro_text)}':expansion=none:"
        "fontcolor=white:fontsize=48:line_spacing=16:"
        "x=(w-text_w)/2:y=h*0.42:"
        "alpha='if(lt(t,57.6),(t-57)/0.6,if(lt(t,59.5),1,(60-t)/0.5))':"
        "enable='between(t,57,60)'[vout]"
    )
    filters.append("[vout]fade=t=out:st=59.2:d=0.8:color=black[vfinal]")

    filters.append(f"[{voice_index}:a]volume=1.0[voice]")
    filters.append(
        f"[{music_index}:a]volume=0.38,afade=t=in:st=0:d=1,"
        "afade=t=out:st=57:d=3[musicfade]"
    )
    filters.append(
        "[voice][musicfade]amix=inputs=2:duration=first:dropout_transition=2,"
        "alimiter=limit=0.95[aout]"
    )

    cmd = [
        "ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[vfinal]", "-map", "[aout]", "-t", "60", "-r", "25",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1800k",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(output),
    ]
    run(cmd)
    print("Selesai:", output)
    print(
        f"Video: 60 detik, 720x1280, {SCENE_COUNT} segmen, "
        f"{len(clips)} sumber AI ({packaged_count} dari paket, {local_count} dari HP), "
        "subtitle tersinkron TTS, musik orisinal lebih jelas, intro dan outro animasi."
    )
    print("Catatan: segmen memakai pengulangan terkontrol jika sumber klip terbatas.")


if __name__ == "__main__":
    main()

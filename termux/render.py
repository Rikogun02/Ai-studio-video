#!/usr/bin/env python3
"""Render a polished 60-second AI Company video locally on Android/Termux."""
import argparse
import html
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

DURATION = 60.0
CLIP_COUNT = 12
TRANSITION = 0.45
FONT = "/system/fonts/Roboto-Regular.ttf"


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
        text_lines = lines[lines.index(timing) + 1:]
        caption = html.unescape(re.sub(r"<[^>]+>", "", "\n".join(text_lines))).strip()
        if not caption:
            continue
        start, end = timestamp(left), timestamp(right)
        if end <= start:
            continue
        path = folder / ("subtitle_%03d.txt" % len(cues))
        path.write_text(caption, encoding="utf-8")
        cues.append((start, end, path))
    return cues


def ffmpeg_path(path):
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", help="Path to the downloaded .zip package")
    parser.add_argument("--output", default=str(Path.home() / "storage" / "downloads" / "AICompanyVideo.mp4"))
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("FFmpeg belum terpasang. Jalankan: pkg install ffmpeg")

    work = Path.home() / ".ai_company_video" / "current"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.package) as archive:
        archive.extractall(work)

    clips = sorted((work / "clips").glob("*"))
    if len(clips) < CLIP_COUNT:
        raise SystemExit(
            "Paket hanya berisi %d klip. Renderer V2 membutuhkan 12 klip berbeda. "
            "Buat ulang paket dari Studio terlebih dahulu." % len(clips)
        )
    clips = clips[:CLIP_COUNT]
    voice = work / "voice.mp3"
    srt = work / "subtitles.srt"
    if not voice.exists() or not srt.exists():
        raise SystemExit("Paket harus berisi voice.mp3 dan subtitles.srt.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    subtitle_dir = work / "subtitle_text"
    subtitle_dir.mkdir(exist_ok=True)
    cues = subtitle_files(srt, subtitle_dir)

    # Twelve distinct clips, with a 0.45-second dissolve at each cut.
    scene = (DURATION + (CLIP_COUNT - 1) * TRANSITION) / CLIP_COUNT
    inputs = []
    for clip in clips:
        inputs += ["-stream_loop", "-1", "-i", str(clip)]
    voice_index = len(clips)
    inputs += ["-i", str(voice)]

    filters = []
    for i in range(CLIP_COUNT):
        filters.append(
            f"[{i}:v]scale=720:1280:force_original_aspect_ratio=increase,"
            f"crop=720:1280,setsar=1,fps=25,trim=duration={scene:.4f},"
            f"setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )

    current = "[v0]"
    offset = scene - TRANSITION
    for i in range(1, CLIP_COUNT):
        label = f"[xf{i}]"
        filters.append(
            f"{current}[v{i}]xfade=transition=fade:duration={TRANSITION}:offset={offset:.4f}{label}"
        )
        current = label
        offset += scene - TRANSITION

    filters.append(f"{current}trim=duration=60,setpts=PTS-STARTPTS[vbase]")
    current = "[vbase]"

    # Burn synchronized Indonesian captions into the picture.
    for index, (start, end, path) in enumerate(cues):
        label = f"[sub{index}]"
        filters.append(
            f"{current}drawtext=fontfile={FONT}:textfile='{ffmpeg_path(path)}':"
            f"expansion=none:fontcolor=white:fontsize=34:line_spacing=8:"
            f"x=(w-text_w)/2:y=h*0.77-text_h/2:box=1:boxcolor=black@0.62:"
            f"boxborderw=16:enable='between(t,{start:.3f},{end:.3f})'{label}"
        )
        current = label

    # One-second animated intro title.
    filters.append(
        f"{current}drawtext=fontfile={FONT}:text='AI COMPANY':fontcolor=white:"
        "fontsize=54:borderw=2:bordercolor=black@0.35:"
        "x=(w-text_w)/2:y=h*0.40+18*(1-t):"
        "alpha='if(lt(t,0.5),t/0.5,if(lt(t,1),(1-t)/0.5,0))':"
        "enable='between(t,0,1)'[intro]"
    )

    # Final two seconds: blur the footage, darken it, then fade fully to black.
    filters.append(
        "[intro]boxblur=18:2:enable='between(t,58,60)',"
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.48:t=fill:"
        "enable='between(t,58,60)'[blurred]"
    )
    filters.append(
        "[blurred]drawtext=fontfile=" + FONT +
        ":text='JAGA PRINSIP. TERUS BERTUMBUH.':fontcolor=white:"
        "fontsize=38:borderw=1:bordercolor=black@0.4:"
        "x=(w-text_w)/2:y=h*0.43:"
        "alpha='if(lt(t,58.4),(t-58)/0.4,if(lt(t,59.6),1,(60-t)/0.4))':"
        "enable='between(t,58,60)'[vout]"
    )
    filters.append("[vout]fade=t=out:st=59.2:d=0.8:color=black[vfinal]")

    # Original ambient instrumental generated locally; no paid or copyrighted music asset.
    music = (
        "aevalsrc=0.055*sin(2*PI*110*t)+0.035*sin(2*PI*164.81*t)+"
        "0.030*sin(2*PI*220*t)+0.020*sin(2*PI*329.63*t)+"
        "0.012*sin(2*PI*55*t):s=44100:d=60,volume=2.8[music]"
    )
    filters.append(music)
    filters.append(f"[{voice_index}:a]volume=1.0[voice]")
    filters.append(
        "[music]afade=t=in:st=0:d=1,afade=t=out:st=58:d=2[musicfade]"
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
        "-movflags", "+faststart", str(output)
    ]
    run(cmd)
    print("Selesai:", output)
    print("Video: 60 detik, 720x1280, 12 klip, subtitle, musik, intro 1 detik, outro 2 detik.")
    print("Lisensi dan atribusi klip ada di metadata.json. Periksa sebelum publikasi.")


if __name__ == "__main__":
    main()

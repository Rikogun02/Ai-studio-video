#!/usr/bin/env python3
"""Render an AI Company Video Studio package locally on Android/Termux."""
import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

def run(cmd):
    subprocess.run(cmd, check=True)

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
    with zipfile.ZipFile(args.package) as z:
        z.extractall(work)
    clips = sorted((work / "clips").glob("*"))
    if not clips:
        raise SystemExit("Paket tidak berisi klip video.")
    voice = work / "voice.mp3"
    meta = json.loads((work / "metadata.json").read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Three cinematic scenes, crossfaded; source clips are looped only when shorter than a scene.
    scene = 20.8
    inputs = []
    for clip in clips[:3]:
        inputs += ["-stream_loop", "-1", "-i", str(clip)]
    voice_index = min(len(clips), 3)
    inputs += ["-i", str(voice)]
    filters = []
    for i in range(len(clips[:3])):
        filters.append(
            f"[{i}:v]scale=720:1280:force_original_aspect_ratio=increase,"
            f"crop=720:1280,setsar=1,fps=25,trim=duration={scene},"
            f"setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )
    if len(clips) == 1:
        filters.append("[v0]null[vbase]")
    else:
        current = "[v0]"
        offset = scene - 0.7
        for i in range(1, len(clips[:3])):
            out_label = f"[xf{i}]"
            filters.append(f"{current}[v{i}]xfade=transition=fade:duration=0.7:offset={offset:.2f}{out_label}")
            current = out_label
            offset += scene - 0.7
        filters.append(f"{current}format=yuv420p[vbase]")

    # Create original ambient music locally; no external music API or paid asset.
    music_expr = "sine=frequency=110:duration=60,volume=0.035"
    filters.append(
        "[vbase]trim=duration=60,setpts=PTS-STARTPTS,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.28:t=fill:enable='between(t,0,2)+between(t,56,60)'[shade]"
    )
    filters.append(
        "[shade]drawtext=text='{}':fontcolor=white:fontsize=42:x=(w-text_w)/2:"
        "y=h*0.40:alpha='if(lt(t,1),t,if(lt(t,2),1,0))':enable='between(t,0,2)'[intro]"
        .format("AI COMPANY")
    )
    filters.append(
        "[intro]drawtext=text='{}':fontcolor=white:fontsize=38:x=(w-text_w)/2:"
        "y=h*0.42:alpha='if(lt(t,57),(t-56),if(lt(t,59),1,1-(t-59)))':"
        "enable='between(t,56,60)'[vout]".format("JAGA PRINSIP. TERUS BERTUMBUH.")
    )
    filters.append(f"aevalsrc={music_expr}[music]")
    filters.append(f"[{voice_index}:a]volume=1.0[voice]")
    filters.append("[voice][music]amix=inputs=2:duration=first:dropout_transition=3,alimiter=limit=0.95[aout]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[vout]", "-map", "[aout]", "-t", "60", "-r", "25",
           "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1800k",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    run(cmd)
    print("Selesai:", output)
    print("Lisensi dan atribusi klip ada di metadata.json. Periksa sebelum publikasi.")

if __name__ == "__main__":
    main()

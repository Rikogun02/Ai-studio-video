import os
import re
import uuid
import json
import shutil
import asyncio
import subprocess
from pathlib import Path
from threading import Lock
from typing import Dict, Any

import requests
import edge_tts
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JOBS = DATA / "jobs"
TMP = DATA / "tmp"
for folder in (JOBS, TMP, DATA / "assets", DATA / "music"):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Company Video Studio", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
STATE: Dict[str, Dict[str, Any]] = {}
LOCK = Lock()
BUSY = False

class CreateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=180)
    style: str = Field("Stoikisme modern", max_length=80)

def auth(token: str = Header(default="")):
    expected = os.getenv("STUDIO_TOKEN", "").strip()
    if not expected:
        raise HTTPException(503, "STUDIO_TOKEN belum dikonfigurasi di server")
    if token != expected:
        raise HTTPException(401, "Token akses tidak valid")

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or "Command failed")[-2500:])

def make_script(topic: str, style: str) -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if key:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer " + key},
                json={"model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
                      "messages":[{"role":"system","content":"Tulis naskah video bahasa Indonesia sekitar 115-130 kata untuk voice over 60 detik. Tanpa judul, tanpa bullet, kalimat natural dan kuat."},
                                 {"role":"user","content":"Topik: "+topic+". Gaya: "+style}],
                      "temperature":0.7},
                timeout=35)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            if len(text.split()) >= 70:
                return text
        except Exception:
            pass
    return (f"{topic}. Dalam {style.lower()}, kita belajar bahwa perubahan besar dimulai dari cara kita memandang keadaan. "
            "Tidak semua hal berjalan sesuai rencana. Tidak semua orang akan memahami pilihan kita. "
            "Namun, kita masih punya kendali atas sikap, keputusan, dan tindakan hari ini. "
            "Berhenti menghabiskan tenaga untuk hal yang tidak bisa kita ubah. "
            "Gunakan energi untuk memperbaiki hal yang berada dalam jangkauan kita. "
            "Ambil satu langkah kecil, lakukan dengan disiplin, lalu ulangi esok hari. "
            "Hidup tidak menuntut kita mengendalikan segalanya. Hidup mengajak kita bertindak bijak di tengah ketidakpastian. "
            "Fokus pada proses. Jaga prinsip. Biarkan hasil mengikuti usaha yang konsisten.")

def make_srt(script: str, duration: int = 60) -> str:
    # Divide narration into readable caption chunks and distribute them across 60 seconds.
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", script) if x.strip()]
    if not sentences:
        sentences = [script.strip()]
    chunks = []
    for sentence in sentences:
        words = sentence.split()
        while len(words) > 12:
            chunks.append(" ".join(words[:12]))
            words = words[12:]
        if words:
            chunks.append(" ".join(words))
    if not chunks:
        chunks = [script.strip()]
    weights = [max(1, len(x.split())) for x in chunks]
    total = sum(weights)
    cursor = 0.0
    entries = []
    for index, (chunk, weight) in enumerate(zip(chunks, weights), 1):
        start = cursor
        cursor += duration * weight / total
        end = min(float(duration), cursor)
        def stamp(value):
            ms = int(round(value * 1000))
            hours, ms = divmod(ms, 3600000)
            minutes, ms = divmod(ms, 60000)
            seconds, millis = divmod(ms, 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
        entries.append(f"{index}\n{stamp(start)} --> {stamp(end)}\n{chunk}\n")
    return "\n".join(entries)

def commons_images(query: str, folder: Path):
    params = {"action":"query","format":"json","generator":"search","gsrsearch":"filetype:bitmap "+query,
              "gsrnamespace":6,"gsrlimit":4,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":900}
    headers = {"User-Agent":"AICompanyVideoStudio/0.1 (personal project)"}
    r = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=headers, timeout=25)
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}
    results = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        try:
            img = requests.get(url, headers=headers, timeout=25)
            img.raise_for_status()
            ext = ".jpg" if "jpeg" in img.headers.get("content-type","") else ".png"
            path = folder / f"visual_{len(results)+1}{ext}"
            path.write_bytes(img.content)
            meta = info.get("extmetadata") or {}
            results.append({"file":str(path),"title":page.get("title",""),
                            "source":info.get("descriptionurl",url),
                            "license":(meta.get("LicenseShortName") or {}).get("value","Check source page"),
                            "artist":(meta.get("Artist") or {}).get("value","")})
            if len(results) == 4:
                break
        except Exception:
            continue
    return results

async def render(job_id: str, topic: str, style: str):
    global BUSY
    folder = JOBS / job_id
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg belum terpasang di server.")
        script = make_script(topic, style)
        (folder/"script.txt").write_text(script, encoding="utf-8")
        (folder/"subtitles.srt").write_text(make_srt(script), encoding="utf-8")
        audio = folder/"voice.mp3"
        await edge_tts.Communicate(script, os.getenv("VOICE","id-ID-ArdiNeural")).save(str(audio))
        visuals = commons_images(topic, folder)
        if not visuals:
            raise RuntimeError("Tidak menemukan visual dari Wikimedia Commons untuk topik ini.")
        # Build a consistent 60-second slideshow from downloaded images.
        inputs = []
        for item in visuals:
            inputs += ["-loop","1","-t",str(60/len(visuals)),"-i",item["file"]]
        inputs += ["-i",str(audio)]
        music_file = Path(os.getenv("MUSIC_FILE", str(DATA / "music" / "background.mp3")))
        has_music = music_file.is_file()
        if has_music:
            inputs += ["-stream_loop","-1","-i",str(music_file)]
        filters = []
        labels = []
        for i in range(len(visuals)):
            filters.append(f"[{i}:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,zoompan=z='min(zoom+0.0008,1.08)':d=1:s=720x1280:fps=25,trim=duration={60/len(visuals):.3f},setpts=PTS-STARTPTS[v{i}]")
            labels.append(f"[v{i}]")
        filters.append("".join(labels)+f"concat=n={len(visuals)}:v=1:a=0,format=yuv420p[vout]")
        if has_music:
            music_index = len(visuals) + 1
            filters.append(f"[{len(visuals)}:a]volume=1.0[voice];[{music_index}:a]volume=0.12[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        else:
            filters.append(f"[{len(visuals)}:a]anull[aout]")
        filter_complex = ";".join(filters)
        out = folder/"video.mp4"
        cmd = ["ffmpeg","-y",*inputs,"-filter_complex",filter_complex,"-map","[vout]","-map","[aout]",
               "-t","60","-r","25","-c:v","libx264","-preset","ultrafast","-b:v","1800k","-c:a","aac","-b:a","128k","-shortest",str(out)]
        run(cmd)
        metadata = {"topic":topic,"style":style,"duration_seconds":60,"resolution":"720x1280",
                    "visuals":[{k:v for k,v in x.items() if k!="file"} for x in visuals]}
        (folder/"metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
        STATE[job_id] = {"status":"completed","message":"Video selesai dibuat","video":f"/download/{job_id}","subtitles":f"/subtitles/{job_id}","metadata":metadata}
    except Exception as e:
        STATE[job_id] = {"status":"failed","message":str(e)}
    finally:
        with LOCK:
            BUSY = False

@app.get("/")
def home():
    return FileResponse(ROOT/"static"/"index.html")

@app.get("/health")
def health():
    return {"status":"ok","ffmpeg":bool(shutil.which("ffmpeg"))}

@app.post("/api/jobs", dependencies=[] )
async def create_job(req: CreateRequest, x_studio_token: str = Header(default="")):
    auth(x_studio_token)
    global BUSY
    with LOCK:
        if BUSY:
            raise HTTPException(429,"Sedang memproses satu video. Tunggu hingga selesai.")
        BUSY = True
    job_id = uuid.uuid4().hex[:12]
    STATE[job_id] = {"status":"processing","message":"Menyiapkan naskah, suara, visual, dan video"}
    asyncio.create_task(render(job_id, req.topic, req.style))
    return {"job_id":job_id,"status":"processing"}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, x_studio_token: str = Header(default="")):
    auth(x_studio_token)
    if not re.fullmatch(r"[a-f0-9]{12}",job_id):
        raise HTTPException(400,"ID job tidak valid")
    return STATE.get(job_id,{"status":"unknown","message":"Job tidak ditemukan di sesi server ini"})

@app.get("/subtitles/{job_id}")
def subtitles(job_id: str, x_studio_token: str = Header(default="")):
    auth(x_studio_token)
    if not re.fullmatch(r"[a-f0-9]{12}",job_id):
        raise HTTPException(400,"ID job tidak valid")
    path = JOBS/job_id/"subtitles.srt"
    if not path.is_file():
        raise HTTPException(404,"Subtitle belum tersedia")
    return FileResponse(path,media_type="application/x-subrip",filename=f"subtitles-{job_id}.srt")

@app.get("/download/{job_id}")
def download(job_id: str, x_studio_token: str = Header(default="")):
    auth(x_studio_token)
    if not re.fullmatch(r"[a-f0-9]{12}",job_id):
        raise HTTPException(400,"ID job tidak valid")
    path = JOBS/job_id/"video.mp4"
    if not path.is_file():
        raise HTTPException(404,"Video belum tersedia")
    return FileResponse(path,media_type="video/mp4",filename=f"video-{job_id}.mp4")

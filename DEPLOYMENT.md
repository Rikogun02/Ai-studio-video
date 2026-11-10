# VPS deployment checklist

This project is not deployed automatically. Review this checklist before installation.

## 1. Inspect first
- Confirm Ubuntu/Python version, free disk, RAM and swap.
- Confirm the existing services and ports.
- Back up any existing project directories before changing them.
- Never stop, restart, edit, or replace `trenches.service`.

## 2. Install system packages
On Ubuntu, install FFmpeg and Python venv support using the package manager. Confirm `ffmpeg -version` and `ffmpeg -encoders` include `libx264`.

## 3. Install application
- Clone this repository into a new, separate directory.
- Create a Python virtual environment and install `requirements.txt`.
- Copy `.env.example` to `.env`, set a long random `STUDIO_TOKEN`, and optionally configure `GROQ_API_KEY`.
- Keep `.env` private with owner-only permissions.
- Do not reuse the existing AI Company V3 directory without reviewing and backing it up first.

## 4. Run privately first
Bind Uvicorn to `127.0.0.1` and test `/health`. Do not expose the service directly to the public internet. If remote access is needed, use an authenticated HTTPS reverse proxy and firewall.

## 5. Validate output
Create a short test job, inspect the MP4 dimensions, duration, narration, SRT timing, visual source metadata and audio mix. Check disk space before increasing concurrency.

## Small VPS limits
Only one render job is allowed at a time. Rendering 720p video is CPU-intensive. This version uses sourced still images with motion effects; it is not a generative text-to-video model.

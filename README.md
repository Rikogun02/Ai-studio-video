# AI Company Video Studio

Browser-based studio that prepares an AI-video production package for local rendering on Android/Termux.

## Production flow
1. Open the private Studio dashboard and enter a topic.
2. Studio creates an Indonesian narration and readable SRT subtitles.
3. Magic Hour generates up to two topic-directed AI video clips at 480p and 9:16.
4. Download the ZIP package to the phone.
5. Render the final 60-second vertical MP4 locally in Termux using FFmpeg.

## Target output
- 60 seconds, vertical 720x1280
- Indonesian Edge TTS voice-over
- Up to two fresh Magic Hour AI video clips
- Optionally reuses the three previously generated AI clips if these exact files exist in Android Downloads:
  - `output (1).mp4`
  - `output (2).mp4`
  - `output (3).mp4`
- Twelve edited scene segments with crossfade transitions. If only a few source clips are available, segments repeat them with controlled cuts; this is not twelve unique generations.
- Original instrumental backing audio synthesized locally (no stock music asset)
- Centered subtitles limited to two lines
- Animated title intro and closing outro
- MP4 saved to `~/storage/downloads/AICompanyVideo.mp4`

## Termux setup
Run once in Termux:

```sh
pkg update -y
pkg install python ffmpeg -y
termux-setup-storage
```

Copy `termux/render.py` from this repository to the phone. Then, from the folder containing the script and downloaded ZIP:

```sh
python render.py ai-company-video-package.zip
```

Optional output path:

```sh
python render.py ai-company-video-package.zip --output ~/storage/downloads/video-saya.mp4
```

## Magic Hour and credit safety
- Set `MAGIC_HOUR_API_KEY` in the server's private `.env` file. Never commit or share the real key.
- The package builder checks the account balance before each request, targets a 72-credit reserve, and creates clips sequentially.
- The estimate is 24 credits per second; actual charges depend on Magic Hour's response and may differ. The reserve is a target, not a guaranteed maximum spend.
- The builder does not automatically retry a timed-out generation request, because the provider may already have accepted and charged it.
- Free-tier resolution and model availability are controlled by Magic Hour and may change.

## Audio and visual notes
The generated backing track is an original local synthesis, not a commercial music recording. The final video uses AI-generated footage only; no Wikimedia or random-photo fallback is included. The three optional phone clips are reused only if their exact filenames are present.

## Server safety
The `/api/packages` endpoint prepares the ZIP package. Final FFmpeg rendering stays on the phone. The legacy `/api/jobs` endpoint is left unchanged.

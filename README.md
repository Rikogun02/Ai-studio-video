# AI Company Video Studio

Browser-based studio that prepares a production package for local rendering on Android/Termux.

## Production flow
1. Open the private Studio dashboard and enter a topic.
2. Studio creates an Indonesian narration, SRT subtitles, and searches Wikimedia Commons for relevant video clips.
3. Download the ZIP package to the phone.
4. Render the final vertical MP4 locally in Termux using FFmpeg.

## Target output
- 60 seconds, vertical 720x1280 (720p)
- Indonesian voice-over
- Three relevant video clips, no random-photo fallback
- Crossfade scene transitions
- Locally synthesized ambient background tone (no paid music API)
- Animated title intro and closing text
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

## Visual source and licensing
Video clips are searched on Wikimedia Commons. The Studio intentionally fails if it cannot find three suitable video clips rather than silently substituting unrelated photos. Each package contains `metadata.json` with source page, creator, and license details. Review those terms and attribution requirements before publishing.

## Free services and limitations
- Uses Wikimedia Commons and Edge TTS; no paid video API is required.
- The ambient backing tone is synthesized locally. It is not a licensed commercial music track.
- This is a stock-footage montage, not guaranteed generative AI video footage.
- Availability and relevance of Commons video clips vary by topic.

## Server safety
The new `/api/packages` endpoint only prepares the ZIP package. Final FFmpeg rendering happens on the phone, reducing load on the VPS. Existing server services should not be modified as part of the rendering workflow.

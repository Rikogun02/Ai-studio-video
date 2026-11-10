# AI Company Video Studio

Browser-based studio for producing 60-second vertical 720p videos with Indonesian narration, sourced visuals, subtitles, and optional background music.

## Initial scope
- FastAPI dashboard
- Topic-to-script workflow
- Indonesian text-to-speech
- Wikimedia Commons visual sourcing with license metadata
- FFmpeg assembly to 720x1280 MP4
- Optional local background music
- Single-job queue for small VPS resources

**Important:** the initial pipeline creates an automated montage from sourced still images. It is not generative text-to-video. Media licensing and attribution must be checked before publication.

## Security
Keep the dashboard private or behind authenticated HTTPS. Never commit API keys, passwords, or tokens. Configure secrets on the VPS, not in Git.

## Status
Project scaffold is being initialized. Deployment will only happen after VPS inspection and backup. The existing `trenches.service` must remain untouched.

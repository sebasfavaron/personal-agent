---
name: karaoke-stem-separation
description: Create a local karaoke or instrumental track from a user-provided audio file
---

# karaoke-stem-separation

## Use When

- the user provides a local audio file they already have
- they want a karaoke, instrumental, or vocal stem
- output quality matters more than speed

## Preferred Workflow

1. Confirm the source file exists and inspect it with `ffprobe`.
2. Prefer real stem separation with Demucs over simple stereo center cancellation.
3. On this server, use `/mnt/rpi/tmp` for temp files and caches and `/mnt/rpi/Music` or a nearby writable path for outputs.
4. If needed, ensure the system packages exist:
   - `sudo apt-get install -y python3-torch python3-torchaudio python3-antlr4`
5. Create a venv that reuses system packages:
   - `python3 -m venv --system-site-packages "/mnt/rpi/tmp/demucs-venv-sys"`
6. Install the lighter Python packages into that venv:
   - `TMPDIR="/mnt/rpi/tmp" PIP_CACHE_DIR="/mnt/rpi/tmp/pip-cache" "/mnt/rpi/tmp/demucs-venv-sys/bin/pip" install --no-deps demucs dora-search einops julius lameenc openunmix omegaconf retrying submitit treetable`
7. Run Demucs on CPU with vocals split out:
   - `TMPDIR="/mnt/rpi/tmp" XDG_CACHE_HOME="/mnt/rpi/tmp/.cache" "/mnt/rpi/tmp/demucs-venv-sys/bin/python" -m demucs -n htdemucs --two-stems vocals --mp3 --mp3-bitrate 320 --mp3-preset 2 -d cpu -o "<output-dir>" "<input-file>"`
8. The instrumental will be `no_vocals.mp3`; copy it to a clearly named final file near the source.
9. Verify the final file with `ffprobe` and share it if requested.

## Fallback

- if Demucs is unavailable, `ffmpeg` center cancellation can be used as a last resort, but call out that quality will often be worse and vocals may remain

## Rules

- never modify the original source file
- create a new output file with a clear suffix like `_karaoke_demucs.mp3`
- prefer CPU mode on this Raspberry Pi unless there is a known accelerator configured
- if root disk space is tight, clear only temporary caches you created and keep heavy caches under `/mnt/rpi/tmp`
- do not claim center cancellation is true stem separation

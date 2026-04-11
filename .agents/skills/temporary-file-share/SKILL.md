---
name: temporary-file-share
description: Expose a local directory or file briefly over HTTP for same-network or Tailscale download
---

# temporary-file-share

## Use When

- you need to fetch a file from a phone or another device quickly
- the file already exists locally and should stay in place
- a short-lived HTTP server is enough

## Workflow

1. Prefer serving the smallest useful directory, not `/`.
2. Verify the parent directory exists and the target file is present.
3. Start a detached HTTP server:
   - `sh -c 'nohup python3 -m http.server 8000 --bind 0.0.0.0 --directory "<directory>" >/tmp/file_share_http.log 2>&1 </dev/null &'`
4. Verify it is listening:
   - `ss -ltnp | rg ":8000"`
5. Give the user one or two direct URLs:
   - `http://100.116.176.16:8000/`
   - `http://100.116.176.16:8000/<filename>`
   - if relevant, also provide `http://ballbox-first.emperor-ratio.ts.net:8000/`
6. When the user confirms the download is done, stop the server:
   - identify the pid from `ss -ltnp | rg ":8000"`
   - `kill <pid>`
7. Verify the port is no longer listening.

## Rules

- default to port `8000` unless it is already in use
- do not move or rename the user's file just to share it
- prefer Tailscale IP or hostname over opening public exposure
- keep the server temporary; close it when the transfer is complete
- if the directory contains unrelated sensitive files, serve a narrower directory instead

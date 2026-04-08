#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run opencode with JSON output, save raw logs, and print only assistant text."
    )
    parser.add_argument("prompt", help="Prompt to send to opencode")
    parser.add_argument(
        "--model",
        default="opencode/minimax-m2.5-free",
        help="Model in provider/model format",
    )
    parser.add_argument(
        "--dir",
        dest="run_dir",
        default=os.getcwd(),
        help="Directory to run opencode in",
    )
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        default=[],
        help="File to attach to the prompt; repeat for multiple files",
    )
    parser.add_argument(
        "--log-dir",
        default=str(Path.home() / "personal-agent" / "agent-harness" / "logs"),
        help="Directory where raw logs and metadata are stored",
    )
    parser.add_argument(
        "--variant",
        help="Optional provider-specific model variant",
    )
    parser.add_argument(
        "--preamble-file",
        help="Optional file whose contents are prepended to the prompt",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def build_command(args: argparse.Namespace) -> list[str]:
    command = [
        "opencode",
        "run",
        "--format",
        "json",
        "--model",
        args.model,
        "--dir",
        args.run_dir,
    ]
    if args.variant:
        command.extend(["--variant", args.variant])
    for file_path in args.files:
        command.extend(["--file", file_path])
    command.append("--")
    prompt = args.prompt
    if args.preamble_file:
        preamble = Path(args.preamble_file).read_text(encoding="utf-8").strip()
        if preamble:
            prompt = f"{preamble}\n\nTask:\n{args.prompt}"
    command.append(prompt)
    return command


def extract_assistant_text(stdout: str) -> str:
    parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "text":
            continue
        part = event.get("part") or {}
        text = part.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts).strip()


def main() -> int:
    args = parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = Path(args.log_dir)
    ensure_dir(log_dir)

    raw_stdout_path = log_dir / f"{timestamp}.stdout.jsonl"
    raw_stderr_path = log_dir / f"{timestamp}.stderr.log"
    meta_path = log_dir / f"{timestamp}.meta.json"

    command = build_command(args)
    proc = subprocess.run(command, capture_output=True, text=True)

    raw_stdout_path.write_text(proc.stdout, encoding="utf-8")
    raw_stderr_path.write_text(proc.stderr, encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "command": command,
                "run_dir": args.run_dir,
                "files": args.files,
                "returncode": proc.returncode,
                "stdout_log": str(raw_stdout_path),
                "stderr_log": str(raw_stderr_path),
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    assistant_text = extract_assistant_text(proc.stdout)
    if assistant_text:
        print(assistant_text)
    else:
        print(
            "No assistant text parsed. Inspect logs:",
            str(meta_path),
            file=sys.stderr,
        )

    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

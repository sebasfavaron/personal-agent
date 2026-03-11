from __future__ import annotations

import json
from typing import Any

from .research_store import get_run


def build_report(run_id: str, fmt: str = "md") -> str:
    payload = get_run(run_id)
    if fmt == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if fmt != "md":
        raise ValueError(f"Unsupported format: {fmt}")

    run = payload["run"]
    lines = [
        f"# Research Report: {run['goal']}",
        "",
        f"- Run ID: `{run['id']}`",
        f"- Status: `{run['status']}`",
        f"- Scope: {run['scope'] or 'not set'}",
        f"- Assumptions: {run['assumptions'] or 'none'}",
        f"- Summary: {run['summary'] or 'not closed yet'}",
        "",
        "## Sources",
    ]

    if payload["sources"]:
        for source in payload["sources"]:
            title = source["title"] or source["url"]
            domain = source["domain"] or "local-or-unknown"
            lines.append(f"- {title} ({domain})")
            lines.append(f"  - URL: {source['url']}")
            if source["notes"]:
                notes = " | ".join(part.strip() for part in source["notes"].splitlines() if part.strip())
                lines.append(f"  - Notes: {notes}")
    else:
        lines.append("- none")

    lines.extend(["", "## Claims"])
    if payload["claims"]:
        for claim in payload["claims"]:
            lines.append(
                f"- [{claim['status']}] {claim['claim']} (confidence {claim['confidence']:.2f})"
            )
            if claim["source_url"]:
                lines.append(f"  - Source: {claim['source_url']}")
    else:
        lines.append("- none")

    lines.extend(["", "## Tasks"])
    if payload["tasks"]:
        for task in payload["tasks"]:
            lines.append(f"- [{task['status']}] {task['task']}")
    else:
        lines.append("- none")

    capture_count = sum(1 for artifact in payload.get("artifacts", []) if artifact["kind"] == "source_capture")
    search_count = sum(1 for artifact in payload.get("artifacts", []) if artifact["kind"] == "search_results")
    lines.extend(["", "## Captures", f"- {capture_count} stored capture(s)"])
    lines.extend(["", "## Searches", f"- {search_count} stored search result set(s)"])

    return "\n".join(lines) + "\n"

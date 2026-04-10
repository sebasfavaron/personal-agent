#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHARED_MEMORY_ROOTS = [
    REPO_ROOT.parent / "agents-database",
    REPO_ROOT.parent / "Code" / "agents-database",
]
SHARED_MEMORY_ROOT = Path(
    os.environ.get(
        "BALLBOX_COMPANY_SHARED_MEMORY_ROOT",
        next((str(path) for path in DEFAULT_SHARED_MEMORY_ROOTS if path.exists()), str(DEFAULT_SHARED_MEMORY_ROOTS[0])),
    )
)
DB_PATH = Path(
    os.environ.get(
        "BALLBOX_COMPANY_SHARED_MEMORY_DB_PATH",
        str(SHARED_MEMORY_ROOT / "data" / "shared-agent-memory.sqlite3"),
    )
)
SHARED_MEMORY_SRC = SHARED_MEMORY_ROOT / "src"
PROJECT_ID = "proj_ballbox"
SOURCE_REF = "ballbox"
AI_DEV_WORKFLOW_ROOT = REPO_ROOT.parent / "ai-dev-workflow"
CODE_HINTS = {
    "repo",
    "repos",
    "branch",
    "commit",
    "pr",
    "pull request",
    "bug",
    "fix",
    "feature",
    "lint",
    "test",
    "build",
    "deploy",
    "refactor",
    "implement",
}


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def connect(readonly: bool = True) -> sqlite3.Connection:
    if readonly:
        return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    return sqlite3.connect(DB_PATH)


def row_to_memory(row: sqlite3.Row) -> dict:
    return dict(row)


def summarize(content: str, limit: int = 180) -> str:
    compact = " ".join(content.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def looks_like_codework(text: str) -> tuple[bool, list[str]]:
    normalized = text.lower()
    hits = sorted({hint for hint in CODE_HINTS if hint in normalized})
    return bool(hits), hits


def lexical_score(query: str, title: str, summary: str, content: str) -> float:
    terms = [term.lower() for term in query.split() if term.strip()]
    if not terms:
        return 1.0
    haystack = " ".join([title, summary, content]).lower()
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(terms)


def load_memory_service():
    if str(SHARED_MEMORY_SRC) not in sys.path:
        sys.path.insert(0, str(SHARED_MEMORY_SRC))
    from shared_agent_memory import MemoryService  # type: ignore

    return MemoryService(str(DB_PATH))


def search_memories_fallback(query: str, limit: int, scope: str | None, memory_type: str | None) -> dict:
    sql = [
        "SELECT id, title, type, scope, project_id, repo_id, summary, content, confidence, freshness, updated_at",
        "FROM memories",
        "WHERE status = 'active'",
    ]
    params: list[str] = []

    if scope:
        sql.append("AND scope = ?")
        params.append(scope)
    if memory_type:
        sql.append("AND type = ?")
        params.append(memory_type)
    sql.append("AND (project_id = ? OR title LIKE ? OR content LIKE ?)")
    params.extend([PROJECT_ID, "%Ballbox%", "%Ballbox%"])

    with connect(readonly=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [row_to_memory(row) for row in conn.execute(" ".join(sql), params)]

    scored = []
    for memory in rows:
        score = lexical_score(query, memory["title"], memory["summary"], memory["content"])
        if query.strip() and score == 0:
            continue
        scored.append(
            {
                "memory": memory,
                "score": round(score * 0.85 + memory["confidence"] * 0.1 + memory["freshness"] * 0.05, 4),
                "explanation": f"lexical={score:.2f} confidence={memory['confidence']:.2f} freshness={memory['freshness']:.2f}",
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return {
        "mode": "sqlite-readonly-fallback",
        "results": scored[:limit],
    }


def search_memories(query: str, limit: int, scope: str | None, memory_type: str | None) -> dict:
    filters = {"project_id": PROJECT_ID}
    if memory_type:
        filters["type"] = memory_type

    try:
        service = load_memory_service()
        payload = service.search(
            query,
            scopes=[scope] if scope else ["global", "project", "repo", "agent", "session"],
            filters=filters,
            limit=limit,
        )
        payload["mode"] = "memory-service"
        return payload
    except sqlite3.OperationalError as exc:
        if "readonly" not in str(exc).lower():
            raise
        payload = search_memories_fallback(query, limit, scope, memory_type)
        payload["fallback_reason"] = str(exc)
        return payload


def cmd_search(args: argparse.Namespace) -> int:
    print(json.dumps(search_memories(args.query, args.limit, args.scope, args.type), ensure_ascii=True, indent=2))
    return 0


def cmd_snapshot(_: argparse.Namespace) -> int:
    payload = search_memories("Ballbox team market thesis ATC", 8, None, None)
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


def cmd_dashboard(_: argparse.Namespace) -> int:
    print((REPO_ROOT / "index.md").read_text())
    return 0


def cmd_add_note(args: argparse.Namespace) -> int:
    try:
        service = load_memory_service()
        memory = service.ingest(
            {
                "id": make_id("mem"),
                "type": args.type,
                "scope": args.scope,
                "project_id": PROJECT_ID if args.scope in {"project", "repo"} else None,
                "repo_id": args.repo_id,
                "title": args.title,
                "content": args.content,
                "summary": summarize(args.content),
                "confidence": args.confidence,
                "freshness": args.freshness,
                "source_ref": SOURCE_REF,
                "evidence_ref": SOURCE_REF,
                "metadata": {"project": "ballbox", "added_by": SOURCE_REF},
            }
        )
    except sqlite3.OperationalError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "note": "Write failed against agents-database from the current environment. Read path still works.",
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 1

    print(json.dumps({"ok": True, "memory_id": memory["id"], "title": memory["title"]}, ensure_ascii=True, indent=2))
    return 0


def cmd_delegate(args: argparse.Namespace) -> int:
    delegated_to_code, code_hits = looks_like_codework(args.input)
    service = load_memory_service()
    memory = service.ingest(
        {
            "id": make_id("mem"),
            "type": "task",
            "scope": "project",
            "project_id": PROJECT_ID,
            "repo_id": None,
            "title": args.title or "Ballbox company handoff",
            "content": args.input,
            "summary": summarize(args.input),
            "confidence": 0.93,
            "freshness": 0.95,
            "source_ref": SOURCE_REF,
            "evidence_ref": SOURCE_REF,
            "metadata": {
                "kind": "company_handoff",
                "delegated_to_code": delegated_to_code,
                "code_hits": code_hits,
            },
        }
    )
    payload: dict[str, object] = {
        "ok": True,
        "memory_id": memory["id"],
        "delegated_to_code": delegated_to_code,
        "code_hits": code_hits,
    }
    if delegated_to_code:
        command = [
            "python3",
            str(AI_DEV_WORKFLOW_ROOT / "scripts" / "ai_dev_workflow_memory.py"),
            "intake-task",
            "--input",
            args.input,
            "--origin",
            SOURCE_REF,
            "--title",
            f"Ballbox code handoff: {args.input[:80]}",
            "--project",
            "ballbox",
        ]
        if args.repo_hint:
            command.extend(["--repo-hint", args.repo_hint])
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload["code_handoff"] = json.loads(result.stdout)
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ballbox company-agent helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    dashboard = sub.add_parser("dashboard")
    dashboard.set_defaults(func=cmd_dashboard)

    search = sub.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--scope", choices=["global", "project", "repo", "agent", "session"], default=None)
    search.add_argument("--type", default=None)
    search.set_defaults(func=cmd_search)

    snapshot = sub.add_parser("snapshot")
    snapshot.set_defaults(func=cmd_snapshot)

    add_note = sub.add_parser("add-note")
    add_note.add_argument("--title", required=True)
    add_note.add_argument("--content", required=True)
    add_note.add_argument("--type", default="profile")
    add_note.add_argument("--scope", default="project", choices=["global", "project", "repo"])
    add_note.add_argument("--repo-id", default=None)
    add_note.add_argument("--confidence", type=float, default=0.9)
    add_note.add_argument("--freshness", type=float, default=0.9)
    add_note.set_defaults(func=cmd_add_note)

    delegate = sub.add_parser("delegate")
    delegate.add_argument("--input", required=True)
    delegate.add_argument("--title", default=None)
    delegate.add_argument("--repo-hint", default=None)
    delegate.set_defaults(func=cmd_delegate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

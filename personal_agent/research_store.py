from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .db import connect
from .source_capture import fetch_url_capture


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_for(url: str) -> str:
    return urlparse(url).netloc


def _log(conn, category: str, ref_id: str | None, message: str) -> None:
    conn.execute(
        "INSERT INTO event_log (category, ref_id, message, created_at) VALUES (?, ?, ?, ?)",
        (category, ref_id, message, _now()),
    )


def start_research(goal: str, scope: str = "", assumptions: str = "") -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO research_runs (id, goal, scope, assumptions, status, summary, created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, 'active', NULL, ?, ?, NULL)
            """,
            (run_id, goal, scope, assumptions, now, now),
        )
        conn.execute(
            """
            INSERT INTO research_steps (run_id, kind, content, status, created_at)
            VALUES (?, 'plan', ?, 'active', ?)
            """,
            (run_id, goal, now),
        )
        _log(conn, "research_run", run_id, f"Started research: {goal}")
    return get_run(run_id)


def add_source(run_id: str, url: str, title: str = "", notes: str = "") -> dict[str, Any]:
    now = _now()
    domain = _domain_for(url)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sources (run_id, url, title, domain, notes, retrieved_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, url, title, domain, notes, now),
        )
        conn.execute(
            "UPDATE research_runs SET updated_at = ? WHERE id = ?",
            (now, run_id),
        )
        _log(conn, "source", run_id, f"Added source {url}")
    return {"run_id": run_id, "url": url, "domain": domain, "title": title, "notes": notes}


def capture_source(run_id: str, url: str, title: str = "", notes: str = "") -> dict[str, Any]:
    now = _now()
    capture = fetch_url_capture(url)
    effective_title = title or capture["title"] or url
    text = capture["text"]
    summary_notes = notes
    if capture["content_type"]:
        summary_notes = f"{notes}\ncontent_type={capture['content_type']}".strip()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sources (run_id, url, title, domain, notes, retrieved_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, url, effective_title, _domain_for(url), summary_notes, now),
        )
        conn.execute(
            """
            INSERT INTO artifacts (run_id, kind, content, created_at)
            VALUES (?, 'source_capture', ?, ?)
            """,
            (
                run_id,
                json.dumps(
                    {
                        "url": url,
                        "title": effective_title,
                        "content_type": capture["content_type"],
                        "text": text[:20000],
                    },
                    sort_keys=True,
                ),
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO research_steps (run_id, kind, content, status, created_at)
            VALUES (?, 'capture', ?, 'completed', ?)
            """,
            (run_id, f"Captured {url}", now),
        )
        conn.execute(
            "UPDATE research_runs SET updated_at = ? WHERE id = ?",
            (now, run_id),
        )
        _log(conn, "source_capture", run_id, f"Captured source {url}")

    return {
        "run_id": run_id,
        "url": url,
        "title": effective_title,
        "domain": _domain_for(url),
        "notes": summary_notes,
        "content_type": capture["content_type"],
        "text_preview": text[:280],
        "captured_chars": len(text),
    }


def add_claim(
    run_id: str,
    claim: str,
    confidence: float,
    status: str = "tentative",
    source_url: str = "",
) -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO claims (run_id, claim, confidence, status, source_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, claim, confidence, status, source_url or None, now),
        )
        conn.execute(
            "UPDATE research_runs SET updated_at = ? WHERE id = ?",
            (now, run_id),
        )
        _log(conn, "claim", run_id, f"Added claim: {claim[:120]}")
    return {
        "run_id": run_id,
        "claim": claim,
        "confidence": confidence,
        "status": status,
        "source_url": source_url,
    }


def add_task(run_id: str | None, task: str, status: str = "open", due_at: str | None = None) -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (run_id, task, status, due_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, task, status, due_at, now),
        )
        ref_id = str(run_id) if run_id else None
        _log(conn, "task", ref_id, f"Added task: {task[:120]}")
    return {
        "id": cur.lastrowid,
        "run_id": run_id,
        "task": task,
        "status": status,
        "due_at": due_at,
    }


def request_approval(kind: str, payload: dict[str, Any], risk_level: str = "high") -> dict[str, Any]:
    now = _now()
    serialized = json.dumps(payload, sort_keys=True)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO approvals (kind, payload, risk_level, status, requested_at, resolved_at)
            VALUES (?, ?, ?, 'pending', ?, NULL)
            """,
            (kind, serialized, risk_level, now),
        )
        approval_id = cur.lastrowid
        _log(conn, "approval", str(approval_id), f"Requested approval for {kind}")
    return {
        "id": approval_id,
        "kind": kind,
        "payload": payload,
        "risk_level": risk_level,
        "status": "pending",
        "requested_at": now,
    }


def close_research(run_id: str, summary: str) -> dict[str, Any]:
    now = _now()
    with connect() as conn:
        conn.execute(
            """
            UPDATE research_steps
            SET status = 'completed'
            WHERE run_id = ? AND status != 'completed'
            """,
            (run_id,),
        )
        conn.execute(
            """
            UPDATE research_runs
            SET status = 'completed', summary = ?, updated_at = ?, completed_at = ?
            WHERE id = ?
            """,
            (summary, now, now, run_id),
        )
        conn.execute(
            """
            INSERT INTO artifacts (run_id, kind, content, created_at)
            VALUES (?, 'report_summary', ?, ?)
            """,
            (run_id, summary, now),
        )
        _log(conn, "research_run", run_id, "Closed research run")
    return get_run(run_id)


def get_run(run_id: str) -> dict[str, Any]:
    with connect() as conn:
        run = conn.execute("SELECT * FROM research_runs WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise ValueError(f"Unknown research run: {run_id}")
        steps = [dict(row) for row in conn.execute("SELECT * FROM research_steps WHERE run_id = ? ORDER BY id", (run_id,))]
        sources = [dict(row) for row in conn.execute("SELECT * FROM sources WHERE run_id = ? ORDER BY id", (run_id,))]
        claims = [dict(row) for row in conn.execute("SELECT * FROM claims WHERE run_id = ? ORDER BY id", (run_id,))]
        tasks = [dict(row) for row in conn.execute("SELECT * FROM tasks WHERE run_id = ? ORDER BY id", (run_id,))]
        artifacts = [dict(row) for row in conn.execute("SELECT * FROM artifacts WHERE run_id = ? ORDER BY id", (run_id,))]
    return {
        "run": dict(run),
        "steps": steps,
        "sources": sources,
        "claims": claims,
        "tasks": tasks,
        "artifacts": artifacts,
    }


def list_approvals(status: str = "pending") -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM approvals WHERE status = ? ORDER BY requested_at DESC",
            (status,),
        ).fetchall()
    approvals = [dict(row) for row in rows]
    for approval in approvals:
        approval["payload"] = json.loads(approval["payload"])
    return approvals


def search_memory(query: str) -> dict[str, Any]:
    like = f"%{query.lower()}%"
    with connect() as conn:
        runs = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, goal, status, summary, created_at, updated_at
                FROM research_runs
                WHERE lower(goal) LIKE ? OR lower(coalesce(summary, '')) LIKE ?
                ORDER BY updated_at DESC
                """,
                (like, like),
            )
        ]
        claims = [
            dict(row)
            for row in conn.execute(
                """
                SELECT run_id, claim, confidence, status, source_url, created_at
                FROM claims
                WHERE lower(claim) LIKE ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (like,),
            )
        ]
        tasks = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, run_id, task, status, due_at, created_at
                FROM tasks
                WHERE lower(task) LIKE ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (like,),
            )
        ]
    return {"query": query, "runs": runs, "claims": claims, "tasks": tasks}

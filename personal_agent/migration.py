from __future__ import annotations

from typing import Any

from .db import connect
from .research_store import get_run
from .shared_memory import get_memory_service, mirror_claim, mirror_run_summary, mirror_source


def migrate_legacy_memory() -> dict[str, Any]:
    service = get_memory_service()
    if service is None:
        raise RuntimeError("shared-agent-memory is not available; cannot migrate legacy memory")

    migrated = {"runs": 0, "claims": 0, "sources": 0, "tasks": 0}

    with connect() as conn:
        run_ids = [row["id"] for row in conn.execute("SELECT id FROM research_runs ORDER BY created_at ASC").fetchall()]
        sources = [dict(row) for row in conn.execute("SELECT * FROM sources ORDER BY id ASC").fetchall()]
        claims = [dict(row) for row in conn.execute("SELECT * FROM claims ORDER BY id ASC").fetchall()]
        tasks = [dict(row) for row in conn.execute("SELECT * FROM tasks ORDER BY id ASC").fetchall()]

    for run_id in run_ids:
        mirror_run_summary(get_run(run_id))
        migrated["runs"] += 1

    for source in sources:
        mirror_source(source["run_id"], source["url"], source.get("title") or "", source.get("notes") or "", source.get("domain") or "")
        migrated["sources"] += 1

    for claim in claims:
        mirror_claim(
            claim["run_id"],
            claim["claim"],
            float(claim["confidence"]),
            claim["status"],
            claim.get("source_url") or "",
        )
        migrated["claims"] += 1

    for task in tasks:
        content = "\n".join(
            part
            for part in [
                task["task"],
                f"kind={task['kind']}",
                f"status={task['status']}",
                f"notes={task.get('notes') or ''}".strip(),
            ]
            if part
        )
        service.ingest(
            {
                "id": f"legacy_task_{task['id']}",
                "type": "task_hint",
                "scope": "global",
                "status": "active",
                "source_kind": "manual",
                "title": f"Legacy task: {task['task'][:80]}",
                "content": content,
                "summary": task["task"][:180],
                "confidence": 0.65,
                "freshness": 0.6,
                "source_ref": f"personal-agent:task:{task['id']}",
                "evidence_ref": f"personal-agent:task:{task['id']}",
                "embedding": service._text_embedding(content),
                "metadata": {
                    "legacy_system": "personal-agent",
                    "legacy_kind": "task",
                    "legacy_task_id": task["id"],
                    "legacy_run_id": task.get("run_id"),
                    "task_kind": task["kind"],
                    "task_status": task["status"],
                },
            }
        )
        migrated["tasks"] += 1

    return {
        "shared_db_path": service.store.db_path,
        "migrated": migrated,
    }

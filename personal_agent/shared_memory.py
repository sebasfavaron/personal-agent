from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .config import SHARED_MEMORY_DB_PATH, SHARED_MEMORY_SRC_DIR


def _load_memory_service_class():
    src_dir = Path(SHARED_MEMORY_SRC_DIR)
    if not src_dir.exists():
        return None
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    try:
        from shared_agent_memory import MemoryService  # type: ignore
    except ModuleNotFoundError:
        return None
    return MemoryService


def get_memory_service():
    memory_service_cls = _load_memory_service_class()
    if memory_service_cls is None:
        return None
    SHARED_MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return memory_service_cls(str(SHARED_MEMORY_DB_PATH))


def _stable_suffix(*parts: str) -> str:
    joined = "::".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def shared_memory_status() -> dict[str, Any]:
    available = _load_memory_service_class() is not None
    return {
        "available": available,
        "db_path": str(SHARED_MEMORY_DB_PATH),
        "src_dir": str(SHARED_MEMORY_SRC_DIR),
    }


def _shared_memory_exact_match(query: str) -> dict[str, Any] | None:
    normalized = query.strip().lower()
    if not normalized or not re.fullmatch(r"^[a-z0-9_\-:]+$", normalized):
        return None
    if not SHARED_MEMORY_DB_PATH.exists():
        return None
    with sqlite3.connect(SHARED_MEMORY_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (query.strip(),)).fetchone()
    if row is None:
        return None
    memory = dict(row)
    memory["metadata"] = json.loads(memory.pop("metadata_json"))
    embedding_json = memory.pop("embedding_json", None)
    memory["embedding"] = json.loads(embedding_json) if embedding_json else None
    return {"memory": memory, "matched_scope": memory["scope"], "explanation": "Exact memory id match"}


def search_shared_memory(query: str, limit: int = 10) -> dict[str, Any]:
    service = get_memory_service()
    exact = _shared_memory_exact_match(query)
    if service is None:
        status = shared_memory_status()
        return {
            "enabled": False,
            "results": [exact] if exact else [],
            "db_path": status["db_path"],
            "reason": f"shared-agent-memory package not found at {status['src_dir']}",
        }
    payload = service.search(query, scopes=["global", "project", "repo", "agent", "session"], limit=limit)
    results = payload["results"]
    if exact is not None and all(item.get("memory", {}).get("id") != exact["memory"]["id"] for item in results):
        results = [exact, *results]
    if len(results) > limit:
        results = results[:limit]
    return {
        "enabled": True,
        "db_path": str(SHARED_MEMORY_DB_PATH),
        "retrieval_id": payload["retrieval_id"],
        "results": results,
    }


def mirror_claim(run_id: str, claim: str, confidence: float, status: str, source_url: str) -> dict[str, Any] | None:
    service = get_memory_service()
    if service is None:
        return None
    return service.ingest(
        {
            "id": f"legacy_claim_{run_id}_{_stable_suffix(claim, source_url, status)}",
            "type": "artifact",
            "scope": "global",
            "status": "active",
            "source_kind": "manual",
            "title": f"Research claim: {claim[:80]}",
            "content": claim,
            "summary": claim[:180],
            "confidence": confidence,
            "freshness": 0.7,
            "source_ref": f"personal-agent:run:{run_id}",
            "evidence_ref": source_url or None,
            "embedding": service._text_embedding(claim),
            "metadata": {
                "legacy_system": "personal-agent",
                "legacy_kind": "claim",
                "legacy_run_id": run_id,
                "claim_status": status,
                "source_url": source_url,
            },
        }
    )


def mirror_run_summary(run: dict[str, Any]) -> dict[str, Any] | None:
    service = get_memory_service()
    if service is None:
        return None
    record = run["run"]
    summary = record.get("summary") or record["goal"]
    content = "\n".join(
        [
            f"Goal: {record['goal']}",
            f"Scope: {record.get('scope') or ''}".strip(),
            f"Assumptions: {record.get('assumptions') or ''}".strip(),
            f"Summary: {summary}",
        ]
    ).strip()
    return service.ingest(
        {
            "id": f"legacy_run_{record['id']}",
            "type": "episode",
            "scope": "global",
            "status": "active",
            "source_kind": "run",
            "title": f"Research run: {record['goal']}",
            "content": content,
            "summary": summary,
            "confidence": 0.85,
            "freshness": 0.8,
            "observed_at": record["updated_at"],
            "source_ref": f"personal-agent:run:{record['id']}",
            "evidence_ref": f"personal-agent:run:{record['id']}",
            "embedding": service._text_embedding(content),
            "metadata": {
                "legacy_system": "personal-agent",
                "legacy_kind": "research_run",
                "legacy_run_id": record["id"],
                "run_status": record["status"],
            },
        }
    )


def mirror_source(run_id: str, url: str, title: str, notes: str, domain: str) -> dict[str, Any] | None:
    service = get_memory_service()
    if service is None:
        return None
    content = "\n".join(part for part in [title, notes, url] if part).strip() or url
    return service.ingest(
        {
            "id": f"legacy_source_{run_id}_{_stable_suffix(url, title)}",
            "type": "artifact",
            "scope": "global",
            "status": "active",
            "source_kind": "document",
            "title": title or url,
            "content": content,
            "summary": notes[:180] if notes else (title or url)[:180],
            "confidence": 0.75,
            "freshness": 0.7,
            "source_ref": f"personal-agent:run:{run_id}",
            "evidence_ref": url,
            "embedding": service._text_embedding(content),
            "metadata": {
                "legacy_system": "personal-agent",
                "legacy_kind": "source",
                "legacy_run_id": run_id,
                "url": url,
                "domain": domain,
                "notes": notes,
            },
        }
    )


def get_legacy_run_from_shared_memory(run_id: str) -> dict[str, Any] | None:
    service = get_memory_service()
    if service is None or not hasattr(service, "list_memories"):
        return None

    source_ref = f"personal-agent:run:{run_id}"
    run_records = service.list_memories(
        source_ref=source_ref,
        metadata={"legacy_kind": "research_run", "legacy_run_id": run_id},
        limit=1,
    )
    if not run_records:
        return None

    related = service.list_memories(source_ref=source_ref, limit=200)
    run_memory = run_records[0]
    claims = [memory for memory in related if memory["metadata"].get("legacy_kind") == "claim"]
    sources = [memory for memory in related if memory["metadata"].get("legacy_kind") == "source"]
    tasks = service.list_memories(metadata={"legacy_kind": "task", "legacy_run_id": run_id}, limit=200)

    goal = _extract_line_value(run_memory["content"], "Goal") or run_memory["title"].removeprefix("Research run: ").strip()
    scope = _extract_line_value(run_memory["content"], "Scope")
    assumptions = _extract_line_value(run_memory["content"], "Assumptions")
    summary = _extract_line_value(run_memory["content"], "Summary") or run_memory["summary"]

    return {
        "run": {
            "id": run_id,
            "goal": goal,
            "scope": scope,
            "assumptions": assumptions,
            "status": run_memory["metadata"].get("run_status", "archived"),
            "summary": summary,
            "created_at": run_memory["created_at"],
            "updated_at": run_memory["updated_at"],
            "completed_at": run_memory["observed_at"] if run_memory["metadata"].get("run_status") == "completed" else None,
            "transition_source": "shared-memory-legacy-bridge",
        },
        "steps": [],
        "sources": [_legacy_source_record(memory) for memory in sorted(sources, key=lambda item: item["created_at"])],
        "claims": [_legacy_claim_record(memory) for memory in sorted(claims, key=lambda item: item["created_at"])],
        "tasks": [_legacy_task_record(memory) for memory in sorted(tasks, key=lambda item: item["created_at"])],
        "artifacts": [],
    }


def _extract_line_value(content: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.*)$", content, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _legacy_source_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": metadata.get("legacy_run_id"),
        "url": metadata.get("url", ""),
        "title": memory["title"],
        "domain": metadata.get("domain"),
        "notes": metadata.get("notes", ""),
        "retrieved_at": memory["created_at"],
    }


def _legacy_claim_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": metadata.get("legacy_run_id"),
        "claim": memory["content"],
        "confidence": memory["confidence"],
        "status": metadata.get("claim_status", "tentative"),
        "source_url": metadata.get("source_url", ""),
        "created_at": memory["created_at"],
    }


def _legacy_task_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    task_text = memory["content"].splitlines()[0].strip() if memory["content"] else memory["summary"]
    return {
        "id": metadata.get("legacy_task_id", memory["id"]),
        "run_id": metadata.get("legacy_run_id"),
        "task": task_text,
        "kind": metadata.get("task_kind", "task"),
        "status": metadata.get("task_status", "open"),
        "parent_task_id": None,
        "notes": "",
        "due_at": None,
        "created_at": memory["created_at"],
    }

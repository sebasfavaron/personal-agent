from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .config import SHARED_MEMORY_DB_PATH, SHARED_MEMORY_SRC_DIR


PERSONAL_AGENT_ID = "personal-agent"
PERSONAL_PROJECT_ID = "proj_personal_agent"

PERSONAL_MEMORY_SCHEMA = "personal-agent-memory-v1"
PERSONAL_TASK_SCHEMA = "personal-agent-task-v1"

LEGACY_MEMORY_KIND_MAP = {
    "research_run": "research_run",
    "research_step": "research_step",
    "source": "research_source",
    "claim": "research_claim",
    "artifact": "research_artifact",
    "leisure_item": "leisure_item",
    "approval_request": "approval_request",
}


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


def personal_memory_metadata(record_kind: str, **extra: Any) -> dict[str, Any]:
    metadata = {"schema": PERSONAL_MEMORY_SCHEMA, "record_kind": record_kind}
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def personal_task_metadata(run_id: str | None = None, **extra: Any) -> dict[str, Any]:
    metadata = {"schema": PERSONAL_TASK_SCHEMA}
    if run_id is not None:
        metadata["run_id"] = run_id
    metadata.update({key: value for key, value in extra.items() if value is not None})
    return metadata


def memory_kind(memory: dict[str, Any]) -> str | None:
    metadata = memory.get("metadata", {})
    return metadata.get("record_kind") or LEGACY_MEMORY_KIND_MAP.get(metadata.get("legacy_kind"))


def is_personal_memory(memory: dict[str, Any], *, record_kind: str | None = None) -> bool:
    metadata = memory.get("metadata", {})
    canonical_kind = memory_kind(memory)
    if canonical_kind is None:
        return False
    if metadata.get("schema") != PERSONAL_MEMORY_SCHEMA and metadata.get("legacy_system") != PERSONAL_AGENT_ID:
        return False
    return record_kind is None or canonical_kind == record_kind


def is_personal_task(task: dict[str, Any]) -> bool:
    metadata = task.get("metadata", {})
    if metadata.get("schema") == PERSONAL_TASK_SCHEMA:
        return True
    return metadata.get("legacy_kind") == "task"


def task_run_id(task: dict[str, Any]) -> str | None:
    metadata = task.get("metadata", {})
    return metadata.get("run_id") or metadata.get("legacy_run_id")


def _canonicalize_memory_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    canonical = dict(metadata)
    record_kind = canonical.get("record_kind") or LEGACY_MEMORY_KIND_MAP.get(canonical.get("legacy_kind"))
    if record_kind is None:
        return None
    run_id = canonical.pop("run_id", None) or canonical.pop("legacy_run_id", None)
    canonical.pop("legacy_kind", None)
    canonical.pop("legacy_system", None)
    canonical["schema"] = PERSONAL_MEMORY_SCHEMA
    canonical["record_kind"] = record_kind
    if run_id is not None:
        canonical["run_id"] = run_id
    return canonical


def _canonicalize_task_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    canonical = dict(metadata)
    if canonical.get("schema") == PERSONAL_TASK_SCHEMA:
        return canonical
    if canonical.get("legacy_kind") != "task":
        return None
    run_id = canonical.pop("run_id", None) or canonical.pop("legacy_run_id", None)
    canonical.pop("legacy_kind", None)
    canonical.pop("legacy_system", None)
    canonical["schema"] = PERSONAL_TASK_SCHEMA
    if run_id is not None:
        canonical["run_id"] = run_id
    return canonical


def _upsert_memory(service, memory: dict[str, Any], metadata: dict[str, Any], *, status: str | None = None) -> dict[str, Any]:
    return service.ingest(
        {
            "id": memory["id"],
            "type": memory["type"],
            "scope": memory["scope"],
            "status": status or memory["status"],
            "project_id": memory.get("project_id"),
            "repo_id": memory.get("repo_id"),
            "agent_id": memory.get("agent_id"),
            "source_kind": memory["source_kind"],
            "title": memory["title"],
            "content": memory["content"],
            "summary": memory["summary"],
            "confidence": memory["confidence"],
            "freshness": memory["freshness"],
            "created_at": memory["created_at"],
            "observed_at": memory["observed_at"],
            "source_ref": memory.get("source_ref"),
            "evidence_ref": memory.get("evidence_ref"),
            "embedding": memory.get("embedding"),
            "metadata": metadata,
        }
    )


def _migrate_legacy_approval_memory(service, memory: dict[str, Any], metadata: dict[str, Any]) -> dict[str, str]:
    task_id = f"task_{memory['id']}"
    payload = metadata.get("payload", {})
    kind = metadata.get("approval_kind", "external_action")
    risk_level = metadata.get("risk_level", "high")
    approval_status = metadata.get("approval_status", "pending")

    try:
        task = service.get_task(task_id)
    except KeyError:
        task = service.create_task(
            task_id=task_id,
            title=f"Approval request: {kind}",
            intent=json.dumps(payload, sort_keys=True),
            kind="approval_request",
            status="blocked" if approval_status == "pending" else "completed",
            project_id=PERSONAL_PROJECT_ID,
            owner_agent=PERSONAL_AGENT_ID,
            blocked_reason="Pending human approval" if approval_status == "pending" else None,
            requires_human_input=approval_status == "pending",
            metadata=personal_task_metadata(
                approval_kind=kind,
                approval_status=approval_status,
                approval_memory_id=memory["id"],
                payload=payload,
                risk_level=risk_level,
            ),
        )

    bundle = service.task_bundle(task["id"])
    approvals = bundle.get("approvals") or []
    approval = approvals[0] if approvals else service.create_approval(
        task_id=task["id"],
        kind=kind,
        risk_level=risk_level,
        payload=payload,
        status=approval_status,
    )

    archived_metadata = dict(metadata)
    archived_metadata["migrated_to_approval_id"] = approval["id"]
    archived_metadata["migrated_to_task_id"] = task["id"]
    _upsert_memory(service, memory, archived_metadata, status="archived")
    return {"approval_id": approval["id"], "task_id": task["id"]}


def migrate_legacy_shared_memory(service=None) -> dict[str, Any]:
    service = service or get_memory_service()
    if service is None:
        raise RuntimeError("shared-agent-memory is not available; cannot migrate legacy memory")

    migrated = {
        "runs": 0,
        "steps": 0,
        "sources": 0,
        "claims": 0,
        "artifacts": 0,
        "leisure_items": 0,
        "tasks": 0,
        "approvals": 0,
    }

    for memory in service.list_memories(status=None, limit=2000):
        metadata = memory.get("metadata", {})
        if metadata.get("schema") == PERSONAL_MEMORY_SCHEMA:
            continue
        canonical = _canonicalize_memory_metadata(metadata)
        if canonical is None:
            continue
        kind = canonical["record_kind"]
        if kind == "approval_request":
            _migrate_legacy_approval_memory(service, memory, canonical)
            migrated["approvals"] += 1
            continue
        _upsert_memory(service, memory, canonical)
        if kind == "research_run":
            migrated["runs"] += 1
        elif kind == "research_step":
            migrated["steps"] += 1
        elif kind == "research_source":
            migrated["sources"] += 1
        elif kind == "research_claim":
            migrated["claims"] += 1
        elif kind == "research_artifact":
            migrated["artifacts"] += 1
        elif kind == "leisure_item":
            migrated["leisure_items"] += 1

    for task in service.list_tasks(limit=2000):
        metadata = task.get("metadata", {})
        canonical = _canonicalize_task_metadata(metadata)
        if canonical is None:
            continue
        service.update_task(
            task["id"],
            status=task["status"],
            owner_agent=task.get("owner_agent"),
            blocked_reason=task.get("blocked_reason"),
            requires_human_input=task.get("requires_human_input"),
            metadata=canonical,
        )
        migrated["tasks"] += 1

    return {
        "status": "migrated",
        "shared_db_path": service.store.db_path,
        "migrated": migrated,
    }

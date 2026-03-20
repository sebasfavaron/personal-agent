from __future__ import annotations

from typing import Any

from .config import SHARED_MEMORY_DB_PATH


PERSONAL_AGENT_ID = "personal-agent"
PERSONAL_PROJECT_ID = "proj_personal_agent"
SHARED_MEMORY_SCHEMA = "shared-agent-memory-v2"


def _memory_service_class():
    try:
        from shared_agent_memory import MemoryService
    except ModuleNotFoundError:
        return None
    return MemoryService


def get_memory_service():
    memory_service_cls = _memory_service_class()
    if memory_service_cls is None:
        return None
    SHARED_MEMORY_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return memory_service_cls(str(SHARED_MEMORY_DB_PATH))


def shared_memory_status() -> dict[str, Any]:
    available = _memory_service_class() is not None
    reason = None
    if not available:
        reason = "shared_agent_memory import failed; install with `pip install -e ~/agents-database`"
    return {
        "available": available,
        "db_path": str(SHARED_MEMORY_DB_PATH),
        "reason": reason,
    }


def search_shared_memory(query: str, limit: int = 10, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    service = get_memory_service()
    if service is None:
        status = shared_memory_status()
        return {
            "enabled": False,
            "results": [],
            "db_path": status["db_path"],
            "reason": status["reason"],
        }
    payload = service.search(
        query,
        scopes=["global", "project", "repo", "agent", "session"],
        filters=filters or {},
        limit=limit,
    )
    return {
        "enabled": True,
        "db_path": str(SHARED_MEMORY_DB_PATH),
        "retrieval_id": payload["retrieval_id"],
        "results": payload["results"],
    }


def memory_subtype(memory: dict[str, Any]) -> str | None:
    return memory.get("subtype") or memory.get("metadata", {}).get("subtype")


def is_personal_memory(memory: dict[str, Any], *, subtype: str | None = None) -> bool:
    if memory.get("schema_version") != SHARED_MEMORY_SCHEMA:
        return False
    if memory.get("origin_agent") != PERSONAL_AGENT_ID:
        return False
    return subtype is None or memory_subtype(memory) == subtype


def is_personal_task(task: dict[str, Any]) -> bool:
    if task.get("schema_version") != SHARED_MEMORY_SCHEMA:
        return False
    return task.get("owner_agent") == PERSONAL_AGENT_ID or task.get("origin") == PERSONAL_AGENT_ID


def task_run_id(task: dict[str, Any]) -> str | None:
    return task.get("run_id")


def migrate_shared_memory(service=None) -> dict[str, Any]:
    service = service or get_memory_service()
    if service is None:
        raise RuntimeError("shared-agent-memory import failed; install with `pip install -e ~/agents-database`")
    return service.migrate_v2()

from __future__ import annotations

from typing import Any

from .shared_memory import get_memory_service


def migrate_legacy_memory() -> dict[str, Any]:
    service = get_memory_service()
    if service is None:
        raise RuntimeError("shared-agent-memory is not available; cannot migrate legacy memory")

    return {
        "status": "noop",
        "message": "personal-agent now writes directly to shared-agent-memory; no local SQLite data remains to migrate",
        "shared_db_path": service.store.db_path,
        "migrated": {"runs": 0, "claims": 0, "sources": 0, "tasks": 0},
    }

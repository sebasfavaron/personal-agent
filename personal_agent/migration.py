from __future__ import annotations

from typing import Any

from .shared_memory import migrate_legacy_shared_memory


def migrate_legacy_memory() -> dict[str, Any]:
    return migrate_legacy_shared_memory()

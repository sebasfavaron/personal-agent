from __future__ import annotations

import hashlib
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


def search_shared_memory(query: str, limit: int = 10) -> dict[str, Any]:
    service = get_memory_service()
    if service is None:
        status = shared_memory_status()
        return {
            "enabled": False,
            "results": [],
            "db_path": status["db_path"],
            "reason": f"shared-agent-memory package not found at {status['src_dir']}",
        }
    payload = service.search(query, scopes=["global", "project", "repo", "agent", "session"], limit=limit)
    return {
        "enabled": True,
        "db_path": str(SHARED_MEMORY_DB_PATH),
        "retrieval_id": payload["retrieval_id"],
        "results": payload["results"],
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

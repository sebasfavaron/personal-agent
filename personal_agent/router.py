from __future__ import annotations

import hashlib
import re
from typing import Any

from .research_store import add_structured_task
from .shared_memory import get_memory_service


COMPANY_HINTS = {
    "ballbox",
    "volvox",
    "empresa",
    "company",
    "operativo",
    "operativa",
    "ventas",
    "sales",
    "cliente",
    "clientes",
    "padel",
}
CODE_HINTS = {
    "repo",
    "repositorio",
    "bug",
    "fix",
    "feature",
    "pr",
    "pull request",
    "branch",
    "code",
    "codigo",
    "tests",
    "lint",
    "build",
    "refactor",
    "implement",
}


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9-]+", text.lower()) if token}


def classify_request(text: str) -> dict[str, Any]:
    tokens = _tokenize(text)
    company_hits = sorted(tokens & COMPANY_HINTS)
    code_hits = sorted(tokens & CODE_HINTS)
    if company_hits and code_hits:
        return {
            "primary_agent": "company",
            "secondary_agent": "code",
            "reason": f"company context ({', '.join(company_hits)}) plus code work ({', '.join(code_hits)})",
        }
    if company_hits:
        return {
            "primary_agent": "company",
            "secondary_agent": None,
            "reason": f"company context ({', '.join(company_hits)})",
        }
    if code_hits:
        return {
            "primary_agent": "code",
            "secondary_agent": None,
            "reason": f"code work ({', '.join(code_hits)})",
        }
    return {
        "primary_agent": "personal",
        "secondary_agent": None,
        "reason": "default personal route",
    }


def _mirror_route(text: str, route: dict[str, Any]) -> dict[str, Any] | None:
    service = get_memory_service()
    if service is None:
        return None
    stable_id = hashlib.sha256(
        f"{text}::{route['primary_agent']}::{route.get('secondary_agent') or ''}".encode("utf-8")
    ).hexdigest()[:16]
    content = "\n".join(
        [
            f"Request: {text}",
            f"Primary agent: {route['primary_agent']}",
            f"Secondary agent: {route.get('secondary_agent') or 'none'}",
            f"Reason: {route['reason']}",
        ]
    )
    return service.ingest(
        {
            "id": f"router_{stable_id}",
            "type": "task",
            "scope": "agent",
            "status": "active",
            "source_kind": "manual",
            "title": f"Router handoff: {route['primary_agent']}",
            "content": content,
            "summary": content[:180],
            "confidence": 0.82,
            "freshness": 0.9,
            "source_ref": "personal-agent:router",
            "evidence_ref": "personal-agent:router",
            "embedding": service._text_embedding(content),
            "metadata": {
                "primary_agent": route["primary_agent"],
                "secondary_agent": route.get("secondary_agent"),
                "kind": "router_handoff",
            },
        }
    )


def route_request(text: str, execute: bool = False) -> dict[str, Any]:
    route = classify_request(text)
    payload: dict[str, Any] = {
        "input": text,
        **route,
        "executed": execute,
    }
    if not execute:
        return payload

    task = add_structured_task(
        None,
        f"[{route['primary_agent']}] {text}",
        kind=f"{route['primary_agent']}_handoff",
        status="open",
        notes=route["reason"],
    )
    mirrored = _mirror_route(text, route)
    payload["task"] = task
    payload["shared_memory"] = {"enabled": mirrored is not None, "memory_id": mirrored["id"] if mirrored else None}
    return payload

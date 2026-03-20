from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .planner import build_route_payload, classify_request
from .research_store import add_structured_task
from .shared_memory import PERSONAL_AGENT_ID, get_memory_service

PERSONAL_ROOT = Path(__file__).resolve().parent.parent
BALLBOX_COMPANY_ROOT = PERSONAL_ROOT.parent / "ballbox-company-agent"
AI_DEV_WORKFLOW_ROOT = PERSONAL_ROOT.parent / "ai-dev-workflow"


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
            "type": "episode",
            "subtype": "router_handoff",
            "scope": "agent",
            "status": "active",
            "origin_agent": PERSONAL_AGENT_ID,
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
                "reason": route["reason"],
            },
        }
    )


def _delegate(route: dict[str, Any], text: str) -> dict[str, Any] | None:
    if route["primary_agent"] == "company":
        command = [
            "python3",
            str(BALLBOX_COMPANY_ROOT / "scripts" / "ballbox_company_agent.py"),
            "delegate",
            "--input",
            text,
            "--title",
            f"Personal handoff: {text[:80]}",
        ]
    elif route["primary_agent"] == "code":
        command = [
            "python3",
            str(AI_DEV_WORKFLOW_ROOT / "scripts" / "ai_dev_workflow_memory.py"),
            "intake-task",
            "--input",
            text,
            "--origin",
            "personal-agent",
            "--title",
            f"Personal code handoff: {text[:80]}",
        ]
    else:
        return None
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def route_request(text: str, execute: bool = False) -> dict[str, Any]:
    route = build_route_payload(text)
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
        status="draft",
        notes=route["reason"],
    )
    mirrored = _mirror_route(text, route)
    delegated = _delegate(route, text)
    payload["task"] = task
    payload["shared_memory"] = {"enabled": mirrored is not None, "memory_id": mirrored["id"] if mirrored else None}
    payload["delegation"] = delegated
    return payload

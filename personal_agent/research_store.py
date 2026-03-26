from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from . import shared_memory
from .repo_targets import default_code_repo, infer_target_repo
from .source_capture import fetch_url_capture
from .web_search import search_web


PERSONAL_AGENT_ID = "personal-agent"
PERSONAL_PROJECT_ID = "proj_personal_agent"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_for(url: str) -> str:
    return urlparse(url).netloc


def _run_source_ref(run_id: str) -> str:
    return f"personal-agent:run:{run_id}"


def _require_service():
    service = shared_memory.get_memory_service()
    if service is None:
        raise RuntimeError("shared-agent-memory is not available; personal-agent now requires the shared DB")
    return service


def _matches_query(query: str, *values: str | None) -> bool:
    normalized = query.strip().lower()
    haystack = " ".join((value or "") for value in values).lower()
    return normalized in haystack


def _run_content(goal: str, scope: str, assumptions: str, summary: str) -> str:
    return "\n".join(
        [
            f"Goal: {goal}",
            f"Scope: {scope}".rstrip(),
            f"Assumptions: {assumptions}".rstrip(),
            f"Summary: {summary}".rstrip(),
        ]
    ).strip()


def _extract_line_value(content: str, label: str) -> str:
    prefix = f"{label}:"
    for line in content.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _get_run_memory(service, run_id: str) -> dict[str, Any]:
    related = service.list_memories(source_ref=_run_source_ref(run_id), limit=200)
    runs = [memory for memory in related if shared_memory.is_personal_memory(memory, record_kind="research_run")]
    if not runs:
        raise ValueError(f"Unknown research run: {run_id}")
    exact = next((memory for memory in runs if memory["id"] == run_id), None)
    return exact or sorted(runs, key=lambda item: (item["updated_at"], item["id"]), reverse=True)[0]


def _upsert_run(
    service,
    run_id: str,
    *,
    goal: str,
    scope: str,
    assumptions: str,
    status: str,
    summary: str | None,
    created_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    existing = None
    try:
        existing = _get_run_memory(service, run_id)
    except ValueError:
        pass
    effective_summary = summary if summary is not None else (existing["summary"] if existing else goal)
    effective_created_at = created_at or (existing["created_at"] if existing else _now())
    effective_completed_at = completed_at or (existing.get("metadata", {}).get("completed_at") if existing else None)
    return service.ingest(
        {
            "id": run_id,
            "type": "episode",
            "scope": "global",
            "status": "active",
            "source_kind": "run",
            "title": f"Research run: {goal}",
            "content": _run_content(goal, scope, assumptions, effective_summary),
            "summary": effective_summary,
            "confidence": 0.9,
            "freshness": 0.85,
            "created_at": effective_created_at,
            "observed_at": effective_completed_at or _now(),
            "source_ref": _run_source_ref(run_id),
            "evidence_ref": _run_source_ref(run_id),
            "embedding": service._text_embedding(f"{goal}\n{scope}\n{assumptions}\n{effective_summary}"),
            "metadata": shared_memory.personal_memory_metadata(
                "research_run",
                run_id=run_id,
                run_status=status,
                completed_at=effective_completed_at,
            ),
        }
    )


def _record_memory(
    service,
    *,
    title: str,
    content: str,
    summary: str,
    source_ref: str,
    evidence_ref: str | None,
    metadata: dict[str, Any],
    memory_type: str = "artifact",
    source_kind: str = "manual",
    confidence: float = 0.75,
    freshness: float = 0.75,
) -> dict[str, Any]:
    return service.ingest(
        {
            "id": f"mem_{uuid.uuid4().hex}",
            "type": memory_type,
            "scope": "global",
            "status": "active",
            "source_kind": source_kind,
            "title": title,
            "content": content,
            "summary": summary,
            "confidence": confidence,
            "freshness": freshness,
            "source_ref": source_ref,
            "evidence_ref": evidence_ref,
            "embedding": service._text_embedding(content),
            "metadata": metadata,
        }
    )


def _run_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": metadata.get("run_id") or memory["id"],
        "goal": _extract_line_value(memory["content"], "Goal") or memory["title"].removeprefix("Research run: ").strip(),
        "scope": _extract_line_value(memory["content"], "Scope"),
        "assumptions": _extract_line_value(memory["content"], "Assumptions"),
        "status": metadata.get("run_status", "active"),
        "summary": _extract_line_value(memory["content"], "Summary") or memory["summary"],
        "created_at": memory["created_at"],
        "updated_at": memory["updated_at"],
        "completed_at": metadata.get("completed_at"),
    }


def _step_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": metadata.get("run_id"),
        "kind": metadata.get("step_kind", "note"),
        "content": memory["content"],
        "status": metadata.get("step_status", "completed"),
        "created_at": memory["created_at"],
    }


def _source_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": metadata.get("run_id"),
        "url": metadata.get("url", ""),
        "title": memory["title"],
        "domain": metadata.get("domain"),
        "notes": metadata.get("notes", ""),
        "retrieved_at": memory["created_at"],
    }


def _claim_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": metadata.get("run_id"),
        "claim": memory["content"],
        "confidence": memory["confidence"],
        "status": metadata.get("claim_status", "tentative"),
        "source_url": metadata.get("source_url", ""),
        "created_at": memory["created_at"],
    }


def _artifact_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": metadata.get("run_id"),
        "kind": metadata.get("artifact_kind", "artifact"),
        "content": memory["content"],
        "created_at": memory["created_at"],
    }


def _task_execution_defaults(task: str) -> dict[str, Any]:
    target_repo = infer_target_repo(task, primary_agent="code") or default_code_repo()
    suggested_cwd = str(target_repo["path"])
    return {
        "project_id": PERSONAL_PROJECT_ID,
        "repo_id": str(target_repo["id"]),
        "owner_agent": PERSONAL_AGENT_ID,
        "execution": {
            "suggested_repo_id": target_repo["id"],
            "suggested_repo_name": target_repo["name"],
            "suggested_cwd": suggested_cwd,
            "cwd": suggested_cwd,
            "permission_mode": "danger-full-access",
            "prompt_preview": task,
        },
    }


def _task_record(task: dict[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata", {})
    return {
        "id": task["id"],
        "run_id": shared_memory.task_run_id(task),
        "task": task["title"],
        "kind": task["kind"],
        "status": task["status"],
        "parent_task_id": task.get("parent_task_id"),
        "notes": metadata.get("notes"),
        "due_at": task.get("due_at"),
        "created_at": task["created_at"],
    }


def _leisure_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "title": memory["title"],
        "media_type": metadata.get("media_type"),
        "status": metadata.get("item_status", "to_consume"),
        "notes": metadata.get("notes"),
        "created_at": memory["created_at"],
        "updated_at": memory["updated_at"],
    }


def start_research(goal: str, scope: str = "", assumptions: str = "") -> dict[str, Any]:
    service = _require_service()
    run_id = str(uuid.uuid4())
    _upsert_run(
        service,
        run_id,
        goal=goal,
        scope=scope,
        assumptions=assumptions,
        status="active",
        summary=goal,
    )
    _record_memory(
        service,
        title=f"Research step: {goal[:80]}",
        content=goal,
        summary=goal[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=_run_source_ref(run_id),
        memory_type="episode",
        metadata=shared_memory.personal_memory_metadata(
            "research_step",
            run_id=run_id,
            step_kind="plan",
            step_status="active",
        ),
    )
    return get_run(run_id)


def add_source(run_id: str, url: str, title: str = "", notes: str = "") -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_get_run_memory(service, run_id))
    domain = _domain_for(url)
    _record_memory(
        service,
        title=title or url,
        content="\n".join(part for part in [title, notes, url] if part).strip() or url,
        summary=notes[:180] if notes else (title or url)[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=url,
        source_kind="document",
        metadata=shared_memory.personal_memory_metadata(
            "research_source",
            run_id=run_id,
            url=url,
            domain=domain,
            notes=notes,
        ),
    )
    _upsert_run(
        service,
        run_id,
        goal=run["goal"],
        scope=run["scope"],
        assumptions=run["assumptions"],
        status=run["status"],
        summary=run["summary"],
        created_at=run["created_at"],
        completed_at=run["completed_at"],
    )
    return {"run_id": run_id, "url": url, "domain": domain, "title": title, "notes": notes}


def capture_source(run_id: str, url: str, title: str = "", notes: str = "") -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_get_run_memory(service, run_id))
    capture = fetch_url_capture(url)
    effective_title = title or capture["title"] or url
    text = capture["text"]
    summary_notes = notes
    if capture["content_type"]:
        summary_notes = f"{notes}\ncontent_type={capture['content_type']}".strip()

    add_source(run_id, url, effective_title, summary_notes)
    _record_memory(
        service,
        title=f"Capture: {effective_title[:80]}",
        content=json.dumps(
            {
                "url": url,
                "title": effective_title,
                "content_type": capture["content_type"],
                "text": text[:20000],
            },
            sort_keys=True,
        ),
        summary=effective_title[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=url,
        metadata=shared_memory.personal_memory_metadata(
            "research_artifact",
            run_id=run_id,
            artifact_kind="source_capture",
        ),
    )
    _record_memory(
        service,
        title=f"Research step: capture {url[:80]}",
        content=f"Captured {url}",
        summary=f"Captured {url}"[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=url,
        memory_type="episode",
        metadata=shared_memory.personal_memory_metadata(
            "research_step",
            run_id=run_id,
            step_kind="capture",
            step_status="completed",
        ),
    )
    _upsert_run(
        service,
        run_id,
        goal=run["goal"],
        scope=run["scope"],
        assumptions=run["assumptions"],
        status=run["status"],
        summary=run["summary"],
        created_at=run["created_at"],
        completed_at=run["completed_at"],
    )
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


def search_and_store_web_results(run_id: str, query: str, max_results: int = 5) -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_get_run_memory(service, run_id))
    payload = search_web(query, max_results=max_results)
    results = payload["results"]
    _record_memory(
        service,
        title=f"Search results: {query[:80]}",
        content=json.dumps(
            {
                "query": query,
                "engine": payload["engine"],
                "results": results,
                "request_url": payload["request_url"],
            },
            sort_keys=True,
        ),
        summary=query[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=payload["request_url"],
        metadata=shared_memory.personal_memory_metadata(
            "research_artifact",
            run_id=run_id,
            artifact_kind="search_results",
        ),
    )
    _record_memory(
        service,
        title=f"Research step: search {query[:80]}",
        content=f"Searched web for: {query}",
        summary=query[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=payload["request_url"],
        memory_type="episode",
        metadata=shared_memory.personal_memory_metadata(
            "research_step",
            run_id=run_id,
            step_kind="search",
            step_status="completed",
        ),
    )
    _upsert_run(
        service,
        run_id,
        goal=run["goal"],
        scope=run["scope"],
        assumptions=run["assumptions"],
        status=run["status"],
        summary=run["summary"],
        created_at=run["created_at"],
        completed_at=run["completed_at"],
    )
    return {
        "run_id": run_id,
        "query": query,
        "engine": payload["engine"],
        "request_url": payload["request_url"],
        "results": results,
    }


def add_claim(
    run_id: str,
    claim: str,
    confidence: float,
    status: str = "tentative",
    source_url: str = "",
) -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_get_run_memory(service, run_id))
    _record_memory(
        service,
        title=f"Research claim: {claim[:80]}",
        content=claim,
        summary=claim[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=source_url or None,
        confidence=confidence,
        metadata=shared_memory.personal_memory_metadata(
            "research_claim",
            run_id=run_id,
            claim_status=status,
            source_url=source_url,
        ),
    )
    _upsert_run(
        service,
        run_id,
        goal=run["goal"],
        scope=run["scope"],
        assumptions=run["assumptions"],
        status=run["status"],
        summary=run["summary"],
        created_at=run["created_at"],
        completed_at=run["completed_at"],
    )
    return {
        "run_id": run_id,
        "claim": claim,
        "confidence": confidence,
        "status": status,
        "source_url": source_url,
    }


def add_task(run_id: str | None, task: str, status: str = "draft", due_at: str | None = None) -> dict[str, Any]:
    return add_structured_task(run_id, task, kind="task", status=status, due_at=due_at)


def add_structured_task(
    run_id: str | None,
    task: str,
    *,
    kind: str = "task",
    status: str = "draft",
    parent_task_id: str | None = None,
    notes: str | None = None,
    due_at: str | None = None,
) -> dict[str, Any]:
    service = _require_service()
    defaults = _task_execution_defaults(task)
    created = service.create_task(
        title=task,
        intent=notes or task,
        kind=kind,
        status=status,
        project_id=defaults["project_id"],
        repo_id=defaults["repo_id"],
        parent_task_id=parent_task_id,
        due_at=due_at,
        owner_agent=defaults["owner_agent"],
        metadata=shared_memory.personal_task_metadata(
            run_id,
            notes=notes,
            execution=defaults["execution"],
        ),
    )
    return _task_record(created)


def add_leisure_item(
    title: str,
    media_type: str,
    *,
    status: str = "to_consume",
    notes: str | None = None,
) -> dict[str, Any]:
    service = _require_service()
    created = _record_memory(
        service,
        title=title,
        content="\n".join(part for part in [title, notes or "", media_type] if part).strip(),
        summary=(notes or title)[:180],
        source_ref="personal-agent:leisure",
        evidence_ref=None,
        metadata=shared_memory.personal_memory_metadata(
            "leisure_item",
            media_type=media_type,
            item_status=status,
            notes=notes,
        ),
    )
    return _leisure_record(created)


def list_leisure_items(
    media_type: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    service = _require_service()
    rows = service.list_memories(source_ref="personal-agent:leisure", limit=200)
    items = [_leisure_record(row) for row in rows if shared_memory.is_personal_memory(row, record_kind="leisure_item")]
    if media_type is not None:
        items = [item for item in items if item["media_type"] == media_type]
    if status is not None:
        items = [item for item in items if item["status"] == status]
    return sorted(items, key=lambda item: (item["updated_at"], item["id"]), reverse=True)


def close_task(task_id: str, status: str = "done") -> dict[str, Any]:
    service = _require_service()
    task = service.get_task(task_id)
    updated = service.update_task(task_id, status=status, metadata=task["metadata"])
    return _task_record(updated)


def list_tasks(status: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
    service = _require_service()
    tasks = [_task_record(task) for task in service.list_tasks(limit=500) if shared_memory.is_personal_task(task)]
    if status is not None:
        tasks = [task for task in tasks if task["status"] == status]
    if run_id is not None:
        tasks = [task for task in tasks if task["run_id"] == run_id]
    return sorted(tasks, key=lambda item: (item["created_at"], item["id"]), reverse=True)


def next_tasks(limit: int = 10) -> list[dict[str, Any]]:
    tasks = [task for task in list_tasks(status="draft") if task["kind"] in {"task", "subtask", "clarification", "research_note"}]
    tasks.sort(key=lambda item: (0 if item["kind"] == "subtask" else 1, item["created_at"], item["id"]))
    return tasks[:limit]


def create_task_intake(
    goal: str,
    scope: str,
    assumptions: str,
    clarification_notes: list[str],
    research_notes: list[str],
    parent_task: str,
    subtasks: list[str],
) -> dict[str, Any]:
    run = start_research(goal, scope, assumptions)
    run_id = run["run"]["id"]

    for note in clarification_notes:
        add_structured_task(run_id, note, kind="clarification", status="noted")
    for note in research_notes:
        add_structured_task(run_id, note, kind="research_note", status="noted")

    parent = add_structured_task(run_id, parent_task, kind="task", status="draft")
    created_subtasks = [
        add_structured_task(run_id, subtask, kind="subtask", status="draft", parent_task_id=parent["id"])
        for subtask in subtasks
    ]

    return {
        "run_id": run_id,
        "parent_task": parent,
        "subtasks": created_subtasks,
    }


def request_approval(kind: str, payload: dict[str, Any], risk_level: str = "high") -> dict[str, Any]:
    service = _require_service()
    task = service.create_task(
        title=f"Approval request: {kind}",
        intent=json.dumps(payload, sort_keys=True),
        kind="approval_request",
        status="blocked",
        project_id=PERSONAL_PROJECT_ID,
        owner_agent=PERSONAL_AGENT_ID,
        blocked_reason="Pending human approval",
        requires_human_input=True,
        metadata=shared_memory.personal_task_metadata(
            approval_kind=kind,
            approval_status="pending",
            payload=payload,
            risk_level=risk_level,
        ),
    )
    created = service.create_approval(task_id=task["id"], kind=kind, risk_level=risk_level, payload=payload, status="pending")
    return {
        "id": created["id"],
        "task_id": task["id"],
        "kind": kind,
        "payload": payload,
        "risk_level": risk_level,
        "status": "pending",
        "requested_at": created["requested_at"],
    }


def resolve_approval(approval_id: str, status: str, note: str = "") -> dict[str, Any]:
    service = _require_service()
    approval = service.resolve_approval(approval_id, status=status, resolution_note=note or None)
    task = service.get_task(approval["task_id"])
    task_metadata = dict(task.get("metadata", {}))
    task_metadata["approval_status"] = status
    if note:
        task_metadata["resolution_note"] = note
    updated_task = service.update_task(
        task["id"],
        status="completed",
        blocked_reason=None,
        requires_human_input=False,
        metadata=shared_memory.personal_task_metadata(**task_metadata),
    )
    return {
        "id": approval["id"],
        "task_id": updated_task["id"],
        "kind": approval["kind"],
        "payload": approval["payload"],
        "risk_level": approval["risk_level"],
        "status": approval["status"],
        "requested_at": approval["requested_at"],
        "resolved_at": approval["resolved_at"],
        "note": approval["resolution_note"],
    }


def close_research(run_id: str, summary: str) -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_get_run_memory(service, run_id))
    _record_memory(
        service,
        title=f"Research summary: {run['goal'][:80]}",
        content=summary,
        summary=summary[:180],
        source_ref=_run_source_ref(run_id),
        evidence_ref=_run_source_ref(run_id),
        metadata=shared_memory.personal_memory_metadata(
            "research_artifact",
            run_id=run_id,
            artifact_kind="report_summary",
        ),
    )
    _upsert_run(
        service,
        run_id,
        goal=run["goal"],
        scope=run["scope"],
        assumptions=run["assumptions"],
        status="completed",
        summary=summary,
        created_at=run["created_at"],
        completed_at=_now(),
    )
    return get_run(run_id)


def get_run(run_id: str) -> dict[str, Any]:
    service = _require_service()
    run_memory = _get_run_memory(service, run_id)
    related = service.list_memories(source_ref=_run_source_ref(run_id), limit=500)
    steps = [_step_record(row) for row in related if shared_memory.is_personal_memory(row, record_kind="research_step")]
    sources = [_source_record(row) for row in related if shared_memory.is_personal_memory(row, record_kind="research_source")]
    claims = [_claim_record(row) for row in related if shared_memory.is_personal_memory(row, record_kind="research_claim")]
    artifacts = [_artifact_record(row) for row in related if shared_memory.is_personal_memory(row, record_kind="research_artifact")]
    tasks = [
        _task_record(task)
        for task in service.list_tasks(limit=500)
        if shared_memory.is_personal_task(task) and shared_memory.task_run_id(task) == run_id
    ]
    return {
        "run": _run_record(run_memory),
        "steps": sorted(steps, key=lambda item: item["created_at"]),
        "sources": sorted(sources, key=lambda item: item["retrieved_at"]),
        "claims": sorted(claims, key=lambda item: item["created_at"]),
        "tasks": sorted(tasks, key=lambda item: item["created_at"]),
        "artifacts": sorted(artifacts, key=lambda item: item["created_at"]),
    }


def list_approvals(status: str | None = "pending") -> list[dict[str, Any]]:
    service = _require_service()
    if not hasattr(service, "list_approvals"):
        tasks = [task for task in service.list_tasks(limit=500) if shared_memory.is_personal_task(task)]
        approvals = []
        for task in tasks:
            metadata = task.get("metadata", {})
            if task.get("kind") != "approval_request" and "approval" not in metadata and "approval_kind" not in metadata:
                continue
            approval_meta = metadata.get("approval") or {}
            approval_status = approval_meta.get("status") or metadata.get("approval_status")
            if status is not None and approval_status != status:
                continue
            approval_kind = approval_meta.get("kind") or metadata.get("approval_kind") or "external_action"
            approval_payload = approval_meta.get("payload") or metadata.get("payload") or {}
            approval_risk = approval_meta.get("risk_level") or metadata.get("risk_level") or "high"
            requested_at = approval_meta.get("requested_at") or task.get("created_at")
            resolved_at = approval_meta.get("resolved_at")
            note = approval_meta.get("resolution_note") or metadata.get("resolution_note")
            approvals.append(
                {
                    "id": metadata.get("approval_id") or metadata.get("approval_memory_id") or task["id"],
                    "task_id": task["id"],
                    "kind": approval_kind,
                    "payload": approval_payload,
                    "risk_level": approval_risk,
                    "status": approval_status or "pending",
                    "requested_at": requested_at,
                    "resolved_at": resolved_at,
                    "note": note,
                }
            )
        return sorted(approvals, key=lambda item: item["requested_at"] or "", reverse=True)
    approvals = []
    for approval in service.list_approvals(status=status, limit=200):
        task = service.get_task(approval["task_id"])
        if not shared_memory.is_personal_task(task):
            continue
        approvals.append(
            {
                "id": approval["id"],
                "task_id": approval["task_id"],
                "kind": approval["kind"],
                "payload": approval["payload"],
                "risk_level": approval["risk_level"],
                "status": approval["status"],
                "requested_at": approval["requested_at"],
                "resolved_at": approval["resolved_at"],
                "note": approval["resolution_note"],
            }
        )
    return sorted(approvals, key=lambda item: item["requested_at"], reverse=True)


def search_memory(query: str) -> dict[str, Any]:
    service = _require_service()
    shared = shared_memory.search_shared_memory(query)
    runs = []
    claims = []
    leisure_items = []
    for result in shared["results"]:
        memory = result["memory"]
        if not shared_memory.is_personal_memory(memory):
            continue
        kind = shared_memory.memory_kind(memory)
        if kind == "research_run":
            runs.append(_run_record(memory))
        elif kind == "research_claim":
            claims.append(_claim_record(memory))
        elif kind == "leisure_item":
            leisure_items.append(_leisure_record(memory))
    tasks = [
        _task_record(task)
        for task in service.list_tasks(limit=500)
        if shared_memory.is_personal_task(task)
        and _matches_query(query, task["title"], task["intent"], task.get("metadata", {}).get("notes"))
    ][:20]
    approvals = [
        approval
        for approval in list_approvals(status=None)
        if _matches_query(query, approval["kind"], json.dumps(approval["payload"], sort_keys=True), approval.get("note"))
    ][:20]
    leisure_matches = [
        item
        for item in list_leisure_items()
        if _matches_query(query, item["title"], item["media_type"], item.get("notes"))
    ][:20]
    return {
        "query": query,
        "results": shared["results"],
        "shared_memory": shared,
        "runs": runs,
        "claims": claims,
        "tasks": tasks,
        "approvals": approvals,
        "leisure_items": leisure_matches or leisure_items,
    }

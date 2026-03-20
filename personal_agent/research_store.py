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
        raise RuntimeError("shared_agent_memory import failed; install with `pip install -e ~/agents-database`")
    return service


def _matches_query(query: str, *values: str | None) -> bool:
    normalized = query.strip().lower()
    haystack = " ".join((value or "") for value in values).lower()
    return normalized in haystack


def _run_memory(service, run_id: str) -> dict[str, Any]:
    runs = service.list_memories(
        origin_agent=PERSONAL_AGENT_ID,
        subtype="research_run",
        run_id=run_id,
        limit=2,
    )
    if not runs:
        raise ValueError(f"Unknown research run: {run_id}")
    return runs[0]


def _run_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata", {})
    return {
        "id": memory["run_id"] or memory["id"],
        "goal": metadata.get("goal", memory["title"].removeprefix("Research run: ").strip()),
        "scope": metadata.get("scope", ""),
        "assumptions": metadata.get("assumptions", ""),
        "status": metadata.get("run_status", "active"),
        "summary": metadata.get("summary", memory["summary"]),
        "created_at": memory["created_at"],
        "updated_at": memory["updated_at"],
        "completed_at": metadata.get("completed_at"),
    }


def _record_memory(
    service,
    *,
    title: str,
    content: str,
    summary: str,
    subtype: str,
    source_ref: str,
    evidence_ref: str | None,
    run_id: str | None = None,
    task_id: str | None = None,
    url: str | None = None,
    domain: str | None = None,
    metadata: dict[str, Any] | None = None,
    memory_type: str = "artifact",
    source_kind: str = "manual",
    confidence: float = 0.75,
    freshness: float = 0.75,
) -> dict[str, Any]:
    return service.create_memory(
        {
            "id": f"mem_{uuid.uuid4().hex}",
            "type": memory_type,
            "subtype": subtype,
            "scope": "global",
            "status": "active",
            "origin_agent": PERSONAL_AGENT_ID,
            "source_kind": source_kind,
            "title": title,
            "content": content,
            "summary": summary,
            "confidence": confidence,
            "freshness": freshness,
            "source_ref": source_ref,
            "evidence_ref": evidence_ref,
            "run_id": run_id,
            "task_id": task_id,
            "url": url,
            "domain": domain,
            "embedding": service._text_embedding(content),
            "metadata": metadata or {},
        }
    )


def _upsert_run(
    service,
    run_id: str,
    *,
    goal: str,
    scope: str,
    assumptions: str,
    status: str,
    summary: str,
    created_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    existing = None
    try:
        existing = _run_memory(service, run_id)
    except ValueError:
        pass
    return service.create_memory(
        {
            "id": run_id,
            "type": "episode",
            "subtype": "research_run",
            "scope": "global",
            "status": "active",
            "origin_agent": PERSONAL_AGENT_ID,
            "source_kind": "run",
            "title": f"Research run: {goal}",
            "content": summary or goal,
            "summary": summary or goal,
            "confidence": 0.9,
            "freshness": 0.85,
            "created_at": created_at or (existing["created_at"] if existing else _now()),
            "observed_at": completed_at or _now(),
            "source_ref": _run_source_ref(run_id),
            "evidence_ref": _run_source_ref(run_id),
            "run_id": run_id,
            "embedding": service._text_embedding("\n".join([goal, scope, assumptions, summary])),
            "metadata": {
                "goal": goal,
                "scope": scope,
                "assumptions": assumptions,
                "run_status": status,
                "summary": summary,
                "completed_at": completed_at,
            },
        }
    )


def _step_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": memory["run_id"],
        "kind": metadata.get("step_kind", "note"),
        "content": memory["content"],
        "status": metadata.get("step_status", "completed"),
        "created_at": memory["created_at"],
    }


def _source_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": memory["run_id"],
        "url": memory.get("url", ""),
        "title": memory["title"],
        "domain": memory.get("domain"),
        "notes": metadata.get("notes", ""),
        "retrieved_at": memory["created_at"],
    }


def _claim_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": memory["run_id"],
        "claim": memory["content"],
        "confidence": memory["confidence"],
        "status": metadata.get("claim_status", "tentative"),
        "source_url": memory.get("url") or metadata.get("source_url", ""),
        "created_at": memory["created_at"],
    }


def _artifact_record(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory["metadata"]
    return {
        "id": memory["id"],
        "run_id": memory["run_id"],
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
        "run_id": task.get("run_id"),
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
    _upsert_run(service, run_id, goal=goal, scope=scope, assumptions=assumptions, status="active", summary=goal)
    _record_memory(
        service,
        title=f"Research step: {goal[:80]}",
        content=goal,
        summary=goal[:180],
        subtype="research_step",
        source_ref=_run_source_ref(run_id),
        evidence_ref=_run_source_ref(run_id),
        run_id=run_id,
        memory_type="episode",
        metadata={"step_kind": "plan", "step_status": "active"},
    )
    return get_run(run_id)


def add_source(run_id: str, url: str, title: str = "", notes: str = "") -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_run_memory(service, run_id))
    domain = _domain_for(url)
    _record_memory(
        service,
        title=title or url,
        content="\n".join(part for part in [title, notes, url] if part).strip() or url,
        summary=notes[:180] if notes else (title or url)[:180],
        subtype="research_source",
        source_ref=_run_source_ref(run_id),
        evidence_ref=url,
        run_id=run_id,
        url=url,
        domain=domain,
        source_kind="document",
        metadata={"notes": notes},
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
    run = _run_record(_run_memory(service, run_id))
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
        subtype="research_artifact",
        source_ref=_run_source_ref(run_id),
        evidence_ref=url,
        run_id=run_id,
        url=url,
        domain=_domain_for(url),
        metadata={"artifact_kind": "source_capture"},
    )
    _record_memory(
        service,
        title=f"Research step: capture {url[:80]}",
        content=f"Captured {url}",
        summary=f"Captured {url}"[:180],
        subtype="research_step",
        source_ref=_run_source_ref(run_id),
        evidence_ref=url,
        run_id=run_id,
        memory_type="episode",
        metadata={"step_kind": "capture", "step_status": "completed"},
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
    run = _run_record(_run_memory(service, run_id))
    payload = search_web(query, max_results=max_results)
    results = payload["results"]
    request_url = payload["request_url"]
    _record_memory(
        service,
        title=f"Search results: {query[:80]}",
        content=json.dumps(
            {
                "query": query,
                "engine": payload["engine"],
                "results": results,
                "request_url": request_url,
            },
            sort_keys=True,
        ),
        summary=query[:180],
        subtype="research_artifact",
        source_ref=_run_source_ref(run_id),
        evidence_ref=request_url,
        run_id=run_id,
        url=request_url,
        domain=_domain_for(request_url),
        metadata={"artifact_kind": "search_results"},
    )
    _record_memory(
        service,
        title=f"Research step: search {query[:80]}",
        content=f"Searched web for: {query}",
        summary=query[:180],
        subtype="research_step",
        source_ref=_run_source_ref(run_id),
        evidence_ref=request_url,
        run_id=run_id,
        memory_type="episode",
        metadata={"step_kind": "search", "step_status": "completed"},
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
    return {"run_id": run_id, "query": query, "engine": payload["engine"], "request_url": request_url, "results": results}


def add_claim(
    run_id: str,
    claim: str,
    confidence: float,
    status: str = "tentative",
    source_url: str = "",
) -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_run_memory(service, run_id))
    _record_memory(
        service,
        title=f"Research claim: {claim[:80]}",
        content=claim,
        summary=claim[:180],
        subtype="research_claim",
        source_ref=_run_source_ref(run_id),
        evidence_ref=source_url or None,
        run_id=run_id,
        url=source_url or None,
        domain=_domain_for(source_url) if source_url else None,
        confidence=confidence,
        metadata={"claim_status": status, "source_url": source_url},
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
    return {"run_id": run_id, "claim": claim, "confidence": confidence, "status": status, "source_url": source_url}


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
        origin=PERSONAL_AGENT_ID,
        run_id=run_id,
        metadata={"schema": shared_memory.SHARED_MEMORY_SCHEMA, "notes": notes, "execution": defaults["execution"]},
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
        subtype="leisure_item",
        source_ref="personal-agent:leisure",
        evidence_ref=None,
        metadata={"media_type": media_type, "item_status": status, "notes": notes},
    )
    return _leisure_record(created)


def list_leisure_items(media_type: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    service = _require_service()
    rows = service.list_memories(origin_agent=PERSONAL_AGENT_ID, subtype="leisure_item", limit=200)
    items = [_leisure_record(row) for row in rows]
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
    tasks = [_task_record(task) for task in service.list_tasks(limit=500, run_id=run_id) if shared_memory.is_personal_task(task)]
    if status is not None:
        tasks = [task for task in tasks if task["status"] == status]
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
    created_subtasks = [add_structured_task(run_id, subtask, kind="subtask", status="draft", parent_task_id=parent["id"]) for subtask in subtasks]
    return {"run_id": run_id, "parent_task": parent, "subtasks": created_subtasks}


def close_research(run_id: str, summary: str) -> dict[str, Any]:
    service = _require_service()
    run = _run_record(_run_memory(service, run_id))
    _record_memory(
        service,
        title=f"Research summary: {run['goal'][:80]}",
        content=summary,
        summary=summary[:180],
        subtype="research_artifact",
        source_ref=_run_source_ref(run_id),
        evidence_ref=_run_source_ref(run_id),
        run_id=run_id,
        metadata={"artifact_kind": "report_summary"},
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
    run_memory = _run_memory(service, run_id)
    related = service.list_memories(origin_agent=PERSONAL_AGENT_ID, run_id=run_id, limit=500)
    steps = [_step_record(row) for row in related if row["subtype"] == "research_step"]
    sources = [_source_record(row) for row in related if row["subtype"] == "research_source"]
    claims = [_claim_record(row) for row in related if row["subtype"] == "research_claim"]
    artifacts = [_artifact_record(row) for row in related if row["subtype"] == "research_artifact"]
    tasks = [_task_record(task) for task in service.list_tasks(limit=500, run_id=run_id) if shared_memory.is_personal_task(task)]
    return {
        "run": _run_record(run_memory),
        "steps": sorted(steps, key=lambda item: item["created_at"]),
        "sources": sorted(sources, key=lambda item: item["retrieved_at"]),
        "claims": sorted(claims, key=lambda item: item["created_at"]),
        "tasks": sorted(tasks, key=lambda item: item["created_at"]),
        "artifacts": sorted(artifacts, key=lambda item: item["created_at"]),
    }


def search_memory(query: str) -> dict[str, Any]:
    service = _require_service()
    shared = shared_memory.search_shared_memory(query, filters={"origin_agent": PERSONAL_AGENT_ID})
    runs = []
    claims = []
    leisure_items = []
    for result in shared["results"]:
        memory = result["memory"]
        subtype = shared_memory.memory_subtype(memory)
        if subtype == "research_run":
            runs.append(_run_record(memory))
        elif subtype == "research_claim":
            claims.append(_claim_record(memory))
        elif subtype == "leisure_item":
            leisure_items.append(_leisure_record(memory))
    tasks = [
        _task_record(task)
        for task in service.list_tasks(limit=500)
        if shared_memory.is_personal_task(task)
        and _matches_query(query, task["title"], task["intent"], task.get("metadata", {}).get("notes"))
    ][:20]
    leisure_matches = [item for item in list_leisure_items() if _matches_query(query, item["title"], item["media_type"], item.get("notes"))][:20]
    return {
        "query": query,
        "results": shared["results"],
        "shared_memory": shared,
        "runs": runs,
        "claims": claims,
        "tasks": tasks,
        "leisure_items": leisure_matches or leisure_items,
    }

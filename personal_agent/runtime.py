from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CODEX_ADD_DIRS, CODEX_BIN
from .planner import build_intake_plan
from .shared_memory import get_memory_service


PERSONAL_AGENT_ID = "personal-agent"
PERSONAL_PROJECT_ID = "proj_personal_agent"
SYSTEM_REPO_ID = "repo_personal_agent"
PERSONAL_ROOT = Path(__file__).resolve().parent.parent
AI_DEV_WORKFLOW_ROOT = PERSONAL_ROOT.parent / "ai-dev-workflow"
BALLBOX_COMPANY_ROOT = PERSONAL_ROOT.parent / "ballbox-company-agent"


@dataclass(slots=True)
class IntakeResult:
    task: dict[str, Any]
    subtasks: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    handoff: dict[str, Any] | None
    memory_context: list[dict[str, Any]]


class PersonalAgentRuntime:
    def __init__(self) -> None:
        service = get_memory_service()
        if service is None:
            raise RuntimeError("shared memory service unavailable")
        self.service = service
        self._ensure_entities()
        self._stop = threading.Event()

    def _ensure_entities(self) -> None:
        self.service.create_project(PERSONAL_PROJECT_ID, "Personal Agent", "Front door and orchestration runtime")
        self.service.create_repo(SYSTEM_REPO_ID, "personal-agent", project_id=PERSONAL_PROJECT_ID, path=str(PERSONAL_ROOT))

    def intake(self, text: str, origin: str = "human") -> IntakeResult:
        memory_context = self.service.search(text, scopes=["global", "project", "repo", "agent"], limit=5)["results"]
        plan = build_intake_plan(text, memory_context)
        route = {
            "primary_agent": plan["primary_agent"],
            "secondary_agent": plan["secondary_agent"],
            "reason": plan["reason"],
            "delegation_target": plan["delegation_target"],
            "planning_source": plan["planning_source"],
            "codex_instruction": plan["codex_instruction"],
        }
        task = self.service.create_task(
            title=self._task_title(text),
            intent=text,
            kind="task",
            status="open",
            project_id=PERSONAL_PROJECT_ID,
            repo_id=SYSTEM_REPO_ID,
            origin=origin,
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": route, "stage": "intake"},
        )
        subtasks = [
            self.service.create_task(
                title=subtask["title"],
                intent=subtask["detail"],
                kind="subtask",
                status="open",
                priority=index + 1,
                project_id=PERSONAL_PROJECT_ID,
                repo_id=SYSTEM_REPO_ID,
                parent_task_id=task["id"],
                origin=origin,
                owner_agent=PERSONAL_AGENT_ID,
                metadata={"route": route, "stage": "subtask"},
            )
            for index, subtask in enumerate(plan["subtasks"])
        ]
        artifacts = [
            self.service.create_artifact(
                task_id=task["id"],
                artifact_type="normalized_intent",
                title="Normalized Intent",
                content=self._normalized_intent(text, route, memory_context),
                source_ref=PERSONAL_AGENT_ID,
                metadata={"route": route},
            ),
            self.service.create_artifact(
                task_id=task["id"],
                artifact_type="plan",
                title="Execution Plan",
                content=self._plan_artifact(text, route, subtasks),
                source_ref=PERSONAL_AGENT_ID,
                metadata={"route": route},
            ),
        ]
        handoff = None
        if route["delegation_target"] is not None:
            handoff = self.service.create_handoff(
                task_id=task["id"],
                from_agent=PERSONAL_AGENT_ID,
                to_agent=route["delegation_target"],
                reason=route["reason"],
                payload={
                    "task_id": task["id"],
                    "intent": text,
                    "route": route,
                    "expected_artifacts": ["report"],
                    "idempotency_key": task["id"],
                },
            )
            self.service.update_task(task["id"], status="in_progress", metadata={"route": route, "stage": "delegated"})
        return IntakeResult(task=task, subtasks=subtasks, artifacts=artifacts, handoff=handoff, memory_context=memory_context)

    def dashboard_snapshot(self) -> dict[str, Any]:
        snapshot = self.service.dashboard_snapshot(owner_agent=PERSONAL_AGENT_ID)
        snapshot["active_tasks"] = [task for task in snapshot.get("active_tasks", []) if task.get("parent_task_id") is None]
        snapshot["blocked_tasks"] = [task for task in snapshot.get("blocked_tasks", []) if task.get("parent_task_id") is None]
        task_ids = [task["id"] for key in ("active_tasks", "blocked_tasks") for task in snapshot.get(key, [])]
        latest_runs = {
            task_id: runs[0] if runs else None for task_id in task_ids for runs in [self.service.list_task_runs(task_id=task_id, limit=1)]
        }
        pending_approvals = self.service.list_approvals(status="pending", limit=100)
        approvals_by_task = {approval["task_id"]: approval for approval in pending_approvals}
        task_counts: dict[str, int] = {}
        for subtask in self.service.list_tasks(owner_agent=PERSONAL_AGENT_ID, limit=200):
            parent_id = subtask.get("parent_task_id")
            if parent_id:
                task_counts[parent_id] = task_counts.get(parent_id, 0) + 1
        for key in ("active_tasks", "blocked_tasks"):
            snapshot[key] = [
                self._decorate_task_snapshot(
                    task,
                    latest_run=latest_runs.get(task["id"]),
                    pending_approval=approvals_by_task.get(task["id"]),
                    open_subtask_count=task_counts.get(task["id"], 0),
                )
                for task in snapshot.get(key, [])
            ]
        snapshot["active_tasks"].sort(key=self._task_sort_key)
        snapshot["blocked_tasks"].sort(key=self._task_sort_key)
        snapshot["summary"] = {
            "active_task_count": len(snapshot.get("active_tasks", [])),
            "blocked_task_count": len(snapshot.get("blocked_tasks", [])),
            "pending_approval_count": len(snapshot.get("pending_approvals", [])),
            "pending_handoff_count": len(snapshot.get("pending_handoffs", [])),
            "running_task_count": sum(1 for task in snapshot.get("active_tasks", []) if task["execution_state"] == "running"),
            "started_task_count": sum(1 for task in snapshot.get("active_tasks", []) if task["has_started"]),
            "queued_task_count": sum(1 for task in snapshot.get("active_tasks", []) if not task["has_started"]),
        }
        snapshot["recent_deliverables"] = self._recent_deliverables(limit=8)
        snapshot["memory_context"] = self.service.context_for(
            project=PERSONAL_PROJECT_ID, repo=SYSTEM_REPO_ID, agent=PERSONAL_AGENT_ID, task="personal front door"
        )
        return snapshot

    def respond_to_blocker(self, task_id: str, response: str) -> dict[str, Any]:
        artifact = self.service.create_artifact(
            task_id=task_id,
            artifact_type="blocker_response",
            title="Human blocker response",
            content=response,
            source_ref=PERSONAL_AGENT_ID,
        )
        task = self.service.update_task(
            task_id,
            status="open",
            blocked_reason=None,
            requires_human_input=False,
            metadata={"resolved_by": "human", "response_artifact_id": artifact["id"]},
        )
        return {"task": task, "artifact": artifact}

    def resolve_approval(self, approval_id: str, status: str, resolution_note: str = "") -> dict[str, Any]:
        normalized = status.strip().lower()
        if normalized not in {"approved", "rejected"}:
            raise ValueError(f"Unsupported approval status: {status}")
        approval = self.service.resolve_approval(approval_id, status=normalized, resolution_note=resolution_note or None)
        artifact = self.service.create_artifact(
            task_id=approval["task_id"],
            artifact_type="approval_resolution",
            title=f"Approval {normalized}",
            content=resolution_note.strip() or f"Approval {normalized}.",
            source_ref=PERSONAL_AGENT_ID,
            metadata={"approval_id": approval_id, "status": normalized},
        )
        task_metadata = {
            "approval_id": approval_id,
            "approval_resolution_artifact_id": artifact["id"],
            "approval_status": normalized,
        }
        if normalized == "rejected":
            task = self.service.update_task(
                approval["task_id"],
                status="blocked",
                blocked_reason=resolution_note.strip() or "Approval rejected",
                requires_human_input=False,
                metadata=task_metadata,
            )
            return {"approval": approval, "artifact": artifact, "task": task, "resume": None}
        task = self.service.update_task(
            approval["task_id"],
            status="open",
            blocked_reason=None,
            requires_human_input=False,
            metadata=task_metadata,
        )
        resume = self._run_task_with_codex(task)
        return {"approval": approval, "artifact": artifact, "task": self.service.get_task(task["id"]), "resume": resume}

    def process_once(self) -> dict[str, Any]:
        processed: list[dict[str, Any]] = []
        for handoff in self.service.list_handoffs(status="pending", limit=20):
            processed.append(self._dispatch_handoff(handoff))
        for task in self.service.list_tasks(status="open", owner_agent=PERSONAL_AGENT_ID, requires_human_input=False, limit=20):
            if task["parent_task_id"] is not None:
                continue
            route = task["metadata"].get("route", {})
            if route.get("primary_agent") in {"company", "code"}:
                continue
            processed.append(self._run_task_with_codex(task))
        return {"processed": processed}

    def serve_forever(self, interval_seconds: float = 5.0) -> None:
        while not self._stop.is_set():
            self.process_once()
            self._stop.wait(interval_seconds)

    def stop(self) -> None:
        self._stop.set()

    def resolve_preference_blocker(self, task_id: str, query: str, reason: str) -> dict[str, Any]:
        results = self.service.search(query, scopes=["global", "project", "repo"], limit=3)["results"]
        if not results:
            return self.service.update_task(
                task_id,
                status="blocked",
                blocked_reason=reason,
                requires_human_input=True,
                metadata={"blocker_query": query},
            )
        chosen = results[0]["memory"]
        self.service.create_artifact(
            task_id=task_id,
            artifact_type="memory_resolution",
            title="Resolved from memory",
            content=f"Resolved blocker using memory {chosen['id']}: {chosen['summary']}",
            source_ref=PERSONAL_AGENT_ID,
            metadata={"memory_id": chosen["id"]},
        )
        return self.service.update_task(
            task_id,
            status="open",
            blocked_reason=None,
            requires_human_input=False,
            metadata={"resolved_by_memory_id": chosen["id"]},
        )

    def _dispatch_handoff(self, handoff: dict[str, Any]) -> dict[str, Any]:
        payload = handoff["payload"]
        if handoff["to_agent"] == "ai-dev-workflow":
            command = [
                "python3",
                str(AI_DEV_WORKFLOW_ROOT / "scripts" / "ai_dev_workflow_memory.py"),
                "run-task",
                "--task-id",
                payload["task_id"],
                "--origin",
                PERSONAL_AGENT_ID,
                "--reason",
                handoff["reason"],
                "--payload-json",
                json.dumps(payload),
            ]
        elif handoff["to_agent"] == "ballbox-company-agent":
            command = [
                "python3",
                str(BALLBOX_COMPANY_ROOT / "scripts" / "ballbox_company_agent.py"),
                "run-task",
                "--task-id",
                payload["task_id"],
                "--origin",
                PERSONAL_AGENT_ID,
                "--reason",
                handoff["reason"],
                "--payload-json",
                json.dumps(payload),
            ]
        else:
            raise ValueError(f"Unknown handoff target: {handoff['to_agent']}")
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        parsed = json.loads(result.stdout)
        status = parsed.get("status", "accepted")
        self.service.complete_handoff(handoff["id"], status=status, result_summary=parsed.get("summary"))
        self.service.create_artifact(
            task_id=handoff["task_id"],
            artifact_type="handoff_result",
            title=f"Handoff result from {handoff['to_agent']}",
            content=result.stdout.strip(),
            fmt="json",
            source_ref=handoff["to_agent"],
            metadata={"handoff_id": handoff["id"]},
        )
        return {"kind": "handoff", "handoff_id": handoff["id"], "status": status}

    def _run_task_with_codex(self, task: dict[str, Any]) -> dict[str, Any]:
        run = self.service.start_task_run(task["id"], PERSONAL_AGENT_ID, input_payload={"mode": "codex-agentic"})
        with tempfile.NamedTemporaryFile(prefix="personal-agent-task-", suffix=".json", delete=False) as handle:
            output_path = Path(handle.name)
        prompt = self._task_execution_prompt(task)
        command = [
            CODEX_BIN,
            "exec",
            "--sandbox",
            "read-only",
            "-C",
            str(PERSONAL_ROOT),
            "-o",
            str(output_path),
        ]
        for writable_dir in CODEX_ADD_DIRS:
            command.extend(["--add-dir", str(writable_dir)])
        command.append(prompt)
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            raw_output = output_path.read_text(encoding="utf-8").strip() or result.stdout.strip()
            decision = self._parse_task_decision(raw_output)
            return self._apply_task_decision(task, run, decision)
        except (ValueError, json.JSONDecodeError) as exc:
            self.service.finish_task_run(run["id"], status="failed", error_message=str(exc))
            self.service.update_task(
                task["id"],
                status="blocked",
                blocked_reason=str(exc),
                requires_human_input=True,
                metadata={"task_run_id": run["id"]},
            )
            return {"kind": "task", "task_id": task["id"], "status": "blocked"}
        except subprocess.CalledProcessError as exc:
            self.service.finish_task_run(run["id"], status="failed", error_message=exc.stderr.strip() or exc.stdout.strip())
            self.service.update_task(
                task["id"],
                status="blocked",
                blocked_reason=exc.stderr.strip() or "codex execution failed",
                requires_human_input=True,
                metadata={"task_run_id": run["id"]},
            )
            return {"kind": "task", "task_id": task["id"], "status": "blocked"}
        finally:
            output_path.unlink(missing_ok=True)

    def _task_execution_prompt(self, task: dict[str, Any]) -> str:
        route = task.get("metadata", {}).get("route", {})
        subtasks = self.service.list_tasks(status="open", owner_agent=PERSONAL_AGENT_ID, limit=100)
        child_subtasks = [item for item in subtasks if item.get("parent_task_id") == task["id"]]
        prior_artifacts = self.service.list_artifacts(task_id=task["id"], limit=20)
        subtask_lines = [f"- {item['title']}: {item['intent']}" for item in child_subtasks[:6]] or ["- none"]
        artifact_lines = [f"- {item['artifact_type']}: {item['title']}" for item in prior_artifacts[:8]] or ["- none"]
        return "\n".join(
            [
                "You are the acting executor for a personal-agent task.",
                "Do not perform external side effects directly.",
                "Python will enforce persistence, approvals, blocking, and audit logs.",
                "Return JSON only with this exact shape:",
                "{",
                '  "outcome": "complete|blocked|needs_approval",',
                '  "summary": "short summary",',
                '  "report_title": "short title",',
                '  "report_markdown": "markdown report",',
                '  "blocker_reason": "required when outcome is blocked",',
                '  "approval": {',
                '    "kind": "required when outcome is needs_approval",',
                '    "risk_level": "low|medium|high",',
                '    "payload": {"summary": "what needs approval"}',
                "  },",
                '  "actions": [',
                '    {',
                '      "type": "create_followup_task|create_handoff|record_artifact",',
                '      "title": "short title",',
                '      "intent": "required for create_followup_task",',
                '      "priority": 0,',
                '      "to_agent": "ai-dev-workflow|ballbox-company-agent",',
                '      "reason": "required for create_handoff",',
                '      "artifact_type": "note",',
                '      "content": "required for record_artifact",',
                '      "payload": {}',
                "    }",
                "  ]",
                "}",
                "Rules:",
                "- Use complete when the task can be closed with a report.",
                "- Use blocked when more context is required before safe progress.",
                "- Use needs_approval when the next meaningful step has external side effects or irreversible risk.",
                "- Use actions when Python should queue durable operational steps before the terminal outcome.",
                "- create_handoff is for specialist repo work; keep payload small and explicit.",
                "- create_followup_task is for durable next steps that should survive this run.",
                "- record_artifact is for structured notes worth preserving in shared memory.",
                "- Always include report_markdown with findings, risks, and recommended next actions.",
                "",
                f"Task title: {task['title']}",
                f"Task intent: {task['intent']}",
                f"Route: {route.get('primary_agent', 'personal')}",
                f"Reason: {route.get('reason', 'n/a')}",
                "Open subtasks:",
                *subtask_lines,
                "Existing artifacts:",
                *artifact_lines,
            ]
        )

    def _parse_task_decision(self, raw_output: str) -> dict[str, Any]:
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
            if match:
                cleaned = match.group(1)
        if not cleaned.startswith("{"):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("No JSON object found in task output")
            cleaned = cleaned[start : end + 1]
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("Task output must be a JSON object")
        return payload

    def _apply_task_decision(self, task: dict[str, Any], run: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        outcome = decision.get("outcome")
        if outcome not in {"complete", "blocked", "needs_approval"}:
            raise ValueError(f"Unsupported outcome: {outcome}")
        report = str(decision.get("report_markdown") or "").strip()
        if not report:
            raise ValueError("Task decision missing report_markdown")
        summary = str(decision.get("summary") or "").strip() or "Codex task decision"
        title = str(decision.get("report_title") or "Worker report").strip()
        artifact = self.service.create_artifact(
            task_id=task["id"],
            artifact_type="report" if outcome == "complete" else "decision",
            title=title,
            content=report,
            source_ref=PERSONAL_AGENT_ID,
            metadata={"task_run_id": run["id"], "outcome": outcome},
        )
        action_results = self._apply_actions(task, run, decision.get("actions"))
        self.service.create_artifact(
            task_id=task["id"],
            artifact_type="execution_state",
            title="Execution state snapshot",
            content=json.dumps(
                {
                    "run_id": run["id"],
                    "outcome": outcome,
                    "summary": summary,
                    "action_results": action_results,
                },
                indent=2,
                sort_keys=True,
            ),
            fmt="json",
            source_ref=PERSONAL_AGENT_ID,
            metadata={"task_run_id": run["id"], "outcome": outcome},
        )
        if outcome == "complete":
            self.service.finish_task_run(run["id"], status="completed", result_summary=summary)
            self.service.update_task(
                task["id"],
                status="completed",
                metadata={"report_artifact_id": artifact["id"], "task_run_id": run["id"], "action_results": action_results},
            )
            self.service.ingest(
                {
                    "type": "episode",
                    "scope": "agent",
                    "project_id": PERSONAL_PROJECT_ID,
                    "repo_id": SYSTEM_REPO_ID,
                    "title": f"Task completed: {task['title']}",
                    "content": report,
                    "summary": report[:180],
                    "source_ref": PERSONAL_AGENT_ID,
                    "evidence_ref": artifact["id"],
                    "embedding": self.service._text_embedding(report),
                    "metadata": {"task_id": task["id"], "task_run_id": run["id"]},
                }
            )
            return {"kind": "task", "task_id": task["id"], "status": "completed", "actions": action_results}
        if outcome == "blocked":
            blocker_reason = str(decision.get("blocker_reason") or summary).strip()
            self.service.finish_task_run(run["id"], status="blocked", result_summary=summary)
            self.service.update_task(
                task["id"],
                status="blocked",
                blocked_reason=blocker_reason,
                requires_human_input=True,
                metadata={"task_run_id": run["id"], "decision_artifact_id": artifact["id"], "action_results": action_results},
            )
            return {"kind": "task", "task_id": task["id"], "status": "blocked", "actions": action_results}
        approval = decision.get("approval")
        if not isinstance(approval, dict) or not approval.get("kind") or not isinstance(approval.get("payload"), dict):
            raise ValueError("Approval decision missing approval payload")
        approval_record = self.service.create_approval(
            task_id=task["id"],
            kind=str(approval["kind"]),
            risk_level=str(approval.get("risk_level") or "high"),
            payload=approval["payload"],
        )
        self.service.finish_task_run(run["id"], status="awaiting_approval", result_summary=summary)
        self.service.update_task(
            task["id"],
            status="blocked",
            blocked_reason="Awaiting approval",
            requires_human_input=True,
            metadata={
                "task_run_id": run["id"],
                "decision_artifact_id": artifact["id"],
                "approval_id": approval_record["id"],
                "action_results": action_results,
            },
        )
        return {
            "kind": "task",
            "task_id": task["id"],
            "status": "awaiting_approval",
            "approval_id": approval_record["id"],
            "actions": action_results,
        }

    def _apply_actions(self, task: dict[str, Any], run: dict[str, Any], actions: Any) -> list[dict[str, Any]]:
        if actions is None:
            return []
        if not isinstance(actions, list):
            raise ValueError("Task decision actions must be a list")
        results: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError("Each task action must be an object")
            action_type = str(action.get("type") or "").strip()
            if action_type == "create_followup_task":
                title = str(action.get("title") or "").strip()
                intent = str(action.get("intent") or "").strip()
                if not title or not intent:
                    raise ValueError("create_followup_task requires title and intent")
                followup = self.service.create_task(
                    title=title,
                    intent=intent,
                    kind="subtask",
                    status="open",
                    priority=int(action.get("priority") or 0),
                    project_id=task.get("project_id") or PERSONAL_PROJECT_ID,
                    repo_id=task.get("repo_id") or SYSTEM_REPO_ID,
                    parent_task_id=task["id"],
                    origin="runtime_action",
                    owner_agent=PERSONAL_AGENT_ID,
                    metadata={"created_by_run_id": run["id"]},
                )
                results.append({"type": action_type, "task_id": followup["id"]})
                continue
            if action_type == "create_handoff":
                to_agent = str(action.get("to_agent") or "").strip()
                reason = str(action.get("reason") or "").strip()
                payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
                if to_agent not in {"ai-dev-workflow", "ballbox-company-agent"} or not reason:
                    raise ValueError("create_handoff requires supported to_agent and reason")
                handoff = self.service.create_handoff(
                    task_id=task["id"],
                    from_agent=PERSONAL_AGENT_ID,
                    to_agent=to_agent,
                    reason=reason,
                    payload={"task_id": task["id"], **payload},
                    metadata={"created_by_run_id": run["id"]},
                )
                results.append({"type": action_type, "handoff_id": handoff["id"], "to_agent": to_agent})
                continue
            if action_type == "record_artifact":
                title = str(action.get("title") or "").strip()
                content = str(action.get("content") or "").strip()
                artifact_type = str(action.get("artifact_type") or "note").strip()
                if not title or not content:
                    raise ValueError("record_artifact requires title and content")
                created = self.service.create_artifact(
                    task_id=task["id"],
                    artifact_type=artifact_type,
                    title=title,
                    content=content,
                    source_ref=PERSONAL_AGENT_ID,
                    metadata={"created_by_run_id": run["id"]},
                )
                results.append({"type": action_type, "artifact_id": created["id"], "artifact_type": artifact_type})
                continue
            raise ValueError(f"Unsupported action type: {action_type}")
        return results

    def _task_title(self, text: str) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= 100 else compact[:97] + "..."

    def _decorate_task_snapshot(
        self,
        task: dict[str, Any],
        *,
        latest_run: dict[str, Any] | None,
        pending_approval: dict[str, Any] | None,
        open_subtask_count: int,
    ) -> dict[str, Any]:
        metadata = task.get("metadata", {})
        route = metadata.get("route", {})
        decorated = dict(task)
        execution_state = self._execution_state_for_task(latest_run)
        decorated["open_subtask_count"] = open_subtask_count
        decorated["latest_run"] = latest_run
        decorated["execution_state"] = execution_state
        decorated["has_started"] = latest_run is not None
        decorated["last_run_started_at"] = latest_run.get("started_at") if latest_run else None
        decorated["pending_approval"] = pending_approval
        decorated["next_action"] = self._next_action_for_task(task, latest_run, pending_approval)
        decorated["route_summary"] = {
            "primary_agent": route.get("primary_agent", "personal"),
            "secondary_agent": route.get("secondary_agent"),
            "planning_source": route.get("planning_source"),
        }
        return decorated

    def _execution_state_for_task(self, latest_run: dict[str, Any] | None) -> str:
        if latest_run is None:
            return "not_started"
        if latest_run.get("status") == "running":
            return "running"
        return "ran_before"

    def _task_sort_key(self, task: dict[str, Any]) -> tuple[int, str]:
        order = {"running": 0, "ran_before": 1, "not_started": 2}
        return (order.get(task.get("execution_state", "not_started"), 9), str(task.get("updated_at", "")))

    def _recent_deliverables(self, limit: int = 8) -> list[dict[str, Any]]:
        deliverables: list[dict[str, Any]] = []
        for artifact in self.service.list_artifacts(limit=50):
            if artifact.get("artifact_type") != "report":
                continue
            task = self.service.get_task(artifact["task_id"])
            if task.get("parent_task_id") is not None:
                continue
            item = dict(artifact)
            item["task_title"] = task["title"]
            item["task_status"] = task["status"]
            deliverables.append(item)
            if len(deliverables) >= limit:
                break
        return deliverables

    def _next_action_for_task(
        self,
        task: dict[str, Any],
        latest_run: dict[str, Any] | None,
        pending_approval: dict[str, Any] | None,
    ) -> str:
        if pending_approval is not None:
            return f"Resolve approval {pending_approval['id']}"
        if task["status"] == "blocked":
            if task.get("requires_human_input"):
                return "Provide blocker response"
            return "Unblock task"
        if latest_run and latest_run.get("status") == "running":
            return "Worker running"
        route = task.get("metadata", {}).get("route", {})
        if route.get("delegation_target"):
            return f"Await handoff to {route['delegation_target']}"
        if task["status"] == "in_progress":
            return "Review in-progress state"
        return "Ready for worker"

    def _normalized_intent(self, text: str, route: dict[str, Any], memory_context: list[dict[str, Any]]) -> str:
        lines = [
            f"Request: {text}",
            f"Primary route: {route['primary_agent']}",
            f"Secondary route: {route.get('secondary_agent') or 'none'}",
            f"Reason: {route['reason']}",
            f"Planning source: {route.get('planning_source', 'unknown')}",
        ]
        if route.get("codex_instruction"):
            lines.append(f"Codex instruction: {route['codex_instruction']}")
        if memory_context:
            lines.append("Relevant memory:")
            for match in memory_context[:3]:
                memory = match["memory"]
                lines.append(f"- {memory['title']} [{memory['id']}]")
        return "\n".join(lines)

    def _plan_artifact(self, text: str, route: dict[str, Any], subtasks: list[dict[str, Any]]) -> str:
        lines = [f"# Plan for {self._task_title(text)}", "", f"- Route: {route['primary_agent']}"]
        if route.get("secondary_agent"):
            lines.append(f"- Secondary route: {route['secondary_agent']}")
        lines.append(f"- Planning source: {route.get('planning_source', 'unknown')}")
        if route.get("delegation_target"):
            lines.append(f"- Delegation target: {route['delegation_target']}")
        if route.get("codex_instruction"):
            lines.append(f"- Codex instruction: {route['codex_instruction']}")
        lines.extend(["", "## Subtasks"])
        for task in subtasks:
            lines.append(f"- {task['title']}")
        return "\n".join(lines)

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CODEX_ADD_DIRS
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
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--ask-for-approval",
            "never",
            "--search",
            "--cd",
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
                "  }",
                "}",
                "Rules:",
                "- Use complete when the task can be closed with a report.",
                "- Use blocked when more context is required before safe progress.",
                "- Use needs_approval when the next meaningful step has external side effects or irreversible risk.",
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
        if outcome == "complete":
            self.service.finish_task_run(run["id"], status="completed", result_summary=summary)
            self.service.update_task(task["id"], status="completed", metadata={"report_artifact_id": artifact["id"]})
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
            return {"kind": "task", "task_id": task["id"], "status": "completed"}
        if outcome == "blocked":
            blocker_reason = str(decision.get("blocker_reason") or summary).strip()
            self.service.finish_task_run(run["id"], status="blocked", result_summary=summary)
            self.service.update_task(
                task["id"],
                status="blocked",
                blocked_reason=blocker_reason,
                requires_human_input=True,
                metadata={"task_run_id": run["id"], "decision_artifact_id": artifact["id"]},
            )
            return {"kind": "task", "task_id": task["id"], "status": "blocked"}
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
            },
        )
        return {"kind": "task", "task_id": task["id"], "status": "awaiting_approval", "approval_id": approval_record["id"]}

    def _task_title(self, text: str) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= 100 else compact[:97] + "..."

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

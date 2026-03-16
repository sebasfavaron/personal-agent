from __future__ import annotations

import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BASE_DIR, CODEX_ADD_DIRS, CODEX_BIN
from .repo_targets import default_code_repo, infer_target_repo, repo_catalog, repo_target_by_id
from .shared_memory import get_memory_service


PERSONAL_AGENT_ID = "personal-agent"
PERSONAL_PROJECT_ID = "proj_personal_agent"
RUNS_DIR = BASE_DIR / "data" / "runs"


@dataclass(slots=True)
class IntakeResult:
    task: dict[str, Any]
    memory_context: list[dict[str, Any]]


@dataclass(slots=True)
class ProcessState:
    run_id: str
    task_id: str
    process: subprocess.Popen[str]
    stdout_path: Path
    stderr_path: Path
    output_path: Path
    command: list[str]


class PersonalAgentRuntime:
    def __init__(self) -> None:
        service = get_memory_service()
        if service is None:
            raise RuntimeError("shared memory service unavailable")
        self.service = service
        self._processes: dict[str, ProcessState] = {}
        self._process_lock = threading.Lock()
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_entities()
        self._recover_interrupted_runs()

    def _ensure_entities(self) -> None:
        self.service.create_project(PERSONAL_PROJECT_ID, "Personal Agent", "Direct Codex runner")
        for repo in repo_catalog().values():
            self.service.create_repo(str(repo["id"]), str(repo["name"]), project_id=PERSONAL_PROJECT_ID, path=str(repo["path"]))

    def intake(self, text: str, origin: str = "human") -> IntakeResult:
        memory_context = self.service.search(text, scopes=["global", "project", "repo", "agent"], limit=5)["results"]
        target_repo = infer_target_repo(text, primary_agent="code") or default_code_repo()
        suggested_cwd = str(target_repo["path"])
        prompt_preview = self._build_prompt(text, suggested_cwd, memory_context)
        task = self.service.create_task(
            title=self._task_title(text),
            intent=text,
            kind="task",
            status="draft",
            project_id=PERSONAL_PROJECT_ID,
            repo_id=str(target_repo["id"]),
            origin=origin,
            owner_agent=PERSONAL_AGENT_ID,
            metadata={
                "execution": {
                    "suggested_repo_id": target_repo["id"],
                    "suggested_repo_name": target_repo["name"],
                    "suggested_cwd": suggested_cwd,
                    "cwd": suggested_cwd,
                    "permission_mode": "danger-full-access",
                    "prompt_preview": prompt_preview,
                }
            },
        )
        return IntakeResult(task=task, memory_context=memory_context)

    def start_task(self, task_id: str, cwd: str, prompt_override: str | None = None) -> dict[str, Any]:
        task = self.service.get_task(task_id)
        if task.get("status") != "draft":
            raise ValueError(f"Task {task_id} is not in draft state")
        final_cwd = Path(cwd).expanduser().resolve()
        if not final_cwd.exists() or not final_cwd.is_dir():
            raise ValueError(f"Invalid cwd: {cwd}")

        prompt = (prompt_override or "").strip() or self._build_prompt(task["intent"], str(final_cwd))
        run = self.service.start_task_run(
            task_id,
            PERSONAL_AGENT_ID,
            input_payload={"cwd": str(final_cwd), "permission_mode": "danger-full-access"},
            metadata={"cwd": str(final_cwd), "permission_mode": "danger-full-access"},
        )
        stdout_path = RUNS_DIR / f"{run['id']}.stdout.log"
        stderr_path = RUNS_DIR / f"{run['id']}.stderr.log"
        output_path = RUNS_DIR / f"{run['id']}.md"
        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        command = [
            CODEX_BIN,
            "exec",
            "--sandbox",
            "danger-full-access",
            "-C",
            str(final_cwd),
            "-o",
            str(output_path),
        ]
        for writable_dir in CODEX_ADD_DIRS:
            command.extend(["--add-dir", str(writable_dir)])
        command.append(prompt)
        process = subprocess.Popen(command, stdout=stdout_handle, stderr=stderr_handle, text=True)
        state = ProcessState(
            run_id=run["id"],
            task_id=task_id,
            process=process,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            output_path=output_path,
            command=command,
        )
        with self._process_lock:
            self._processes[run["id"]] = state
        self.service.update_task(
            task_id,
            status="in_progress",
            blocked_reason=None,
            requires_human_input=False,
            metadata=self._merged_task_metadata(
                task,
                {
                    "execution": {
                        **dict(task.get("metadata", {}).get("execution") or {}),
                        "cwd": str(final_cwd),
                        "prompt_preview": prompt,
                        "run_id": run["id"],
                        "pid": process.pid,
                        "command": command,
                        "stdout_path": str(stdout_path),
                        "stderr_path": str(stderr_path),
                        "output_path": str(output_path),
                        "permission_mode": "danger-full-access",
                    }
                },
            ),
        )
        watcher = threading.Thread(target=self._watch_run, args=(run["id"], stdout_handle, stderr_handle), daemon=True)
        watcher.start()
        return {"task": self.service.get_task(task_id), "run": self.service.get_task_run(run["id"])}

    def dashboard_snapshot(self) -> dict[str, Any]:
        tasks = self.service.list_tasks(owner_agent=PERSONAL_AGENT_ID, limit=200)
        top_level = [task for task in tasks if task.get("parent_task_id") is None]
        latest_runs = {
            task["id"]: (self.service.list_task_runs(task_id=task["id"], limit=1) or [None])[0] for task in top_level
        }
        recent_results = []
        for artifact in self.service.list_artifacts(limit=50):
            if artifact.get("artifact_type") != "report":
                continue
            task = self.service.get_task(artifact["task_id"])
            if task.get("parent_task_id") is not None:
                continue
            item = dict(artifact)
            item["task_title"] = task["title"]
            item["task_status"] = task["status"]
            recent_results.append(item)
            if len(recent_results) >= 12:
                break
        draft_tasks = [self._decorate_task(task, latest_runs.get(task["id"])) for task in top_level if task["status"] == "draft"]
        active_runs = [self._decorate_task(task, latest_runs.get(task["id"])) for task in top_level if task["status"] == "in_progress"]
        failed_tasks = [self._decorate_task(task, latest_runs.get(task["id"])) for task in top_level if task["status"] == "failed"]
        return {
            "draft_tasks": draft_tasks,
            "active_runs": active_runs,
            "failed_tasks": failed_tasks,
            "recent_results": recent_results,
            "summary": {
                "draft_count": len(draft_tasks),
                "running_count": len(active_runs),
                "failed_count": len(failed_tasks),
                "result_count": len(recent_results),
            },
        }

    def task_bundle(self, task_id: str) -> dict[str, Any]:
        bundle = self.service.task_bundle(task_id)
        runs = bundle.get("runs") or []
        latest_run = runs[0] if runs else None
        artifacts = bundle.get("artifacts") or []
        latest_artifact = artifacts[0] if artifacts else None
        bundle["task"] = self._decorate_task(bundle["task"], latest_run)
        bundle["latest_run"] = latest_run
        bundle["latest_artifact"] = latest_artifact
        return bundle

    def stop(self) -> None:
        with self._process_lock:
            active = list(self._processes.values())
        for state in active:
            if state.process.poll() is None:
                state.process.terminate()

    def _watch_run(self, run_id: str, stdout_handle: Any, stderr_handle: Any) -> None:
        try:
            with self._process_lock:
                state = self._processes.get(run_id)
            if state is None:
                return
            exit_code = state.process.wait()
        finally:
            stdout_handle.close()
            stderr_handle.close()
        task = self.service.get_task(state.task_id)
        markdown = self._read_file(state.output_path)
        stdout_text = self._read_file(state.stdout_path)
        stderr_text = self._read_file(state.stderr_path)
        report_body = markdown.strip() or stdout_text.strip()
        if exit_code == 0 and report_body:
            artifact = self.service.create_artifact(
                task_id=task["id"],
                artifact_type="report",
                title=f"Codex result for {task['title']}",
                content=report_body,
                source_ref=PERSONAL_AGENT_ID,
                metadata={
                    "classification": "deliverable",
                    "run_id": run_id,
                    "cwd": task.get("metadata", {}).get("execution", {}).get("cwd"),
                    "output_refs": self._extract_output_refs(report_body),
                },
            )
            self.service.finish_task_run(run_id, status="succeeded", result_summary="Codex run completed")
            self.service.update_task(
                task["id"],
                status="completed",
                blocked_reason=None,
                requires_human_input=False,
                metadata=self._merged_task_metadata(
                    task,
                    {"execution": {**dict(task.get("metadata", {}).get("execution") or {}), "result_artifact_id": artifact["id"]}},
                ),
            )
        else:
            failure_report = "\n\n".join(
                section
                for section in [
                    "# Codex run failed",
                    f"- Exit code: {exit_code}",
                    "## Stdout\n" + stdout_text.strip() if stdout_text.strip() else "",
                    "## Stderr\n" + stderr_text.strip() if stderr_text.strip() else "",
                ]
                if section
            )
            artifact = self.service.create_artifact(
                task_id=task["id"],
                artifact_type="run_failure",
                title=f"Codex failure for {task['title']}",
                content=failure_report,
                source_ref=PERSONAL_AGENT_ID,
                metadata={"classification": "intermediate", "run_id": run_id},
            )
            self.service.finish_task_run(
                run_id,
                status="failed",
                result_summary="Codex run failed",
                error_message=(stderr_text.strip() or stdout_text.strip() or "codex execution failed")[:500],
            )
            self.service.update_task(
                task["id"],
                status="failed",
                blocked_reason=None,
                requires_human_input=False,
                metadata=self._merged_task_metadata(
                    task,
                    {"execution": {**dict(task.get("metadata", {}).get("execution") or {}), "failure_artifact_id": artifact["id"]}},
                ),
            )
        with self._process_lock:
            self._processes.pop(run_id, None)

    def _recover_interrupted_runs(self) -> None:
        running_runs = self.service.list_task_runs(status="running", limit=200)
        for run in running_runs:
            self.service.finish_task_run(
                run["id"],
                status="failed",
                result_summary="Recovered interrupted run after daemon restart",
                error_message="Daemon restarted before Codex finished",
            )
            task = self.service.get_task(run["task_id"])
            if task.get("status") == "in_progress":
                self.service.update_task(
                    task["id"],
                    status="failed",
                    blocked_reason=None,
                    requires_human_input=False,
                    metadata=self._merged_task_metadata(task, {"execution": {**dict(task.get("metadata", {}).get("execution") or {}), "recovered_run_id": run["id"]}}),
                )

    def _decorate_task(self, task: dict[str, Any], latest_run: dict[str, Any] | None) -> dict[str, Any]:
        decorated = dict(task)
        execution = dict(task.get("metadata", {}).get("execution") or {})
        decorated["execution"] = execution
        decorated["latest_run"] = latest_run
        decorated["cwd"] = execution.get("cwd") or execution.get("suggested_cwd")
        decorated["suggested_cwd"] = execution.get("suggested_cwd")
        decorated["permission_mode"] = execution.get("permission_mode", "danger-full-access")
        return decorated

    def _build_prompt(self, intent: str, cwd: str, memory_context: list[dict[str, Any]] | None = None) -> str:
        memory_lines = []
        for match in memory_context or []:
            memory = match.get("memory", {})
            title = memory.get("title", "Untitled memory")
            summary = memory.get("summary") or memory.get("content", "")
            memory_lines.append(f"- {title}: {summary}")
        memory_block = "\n".join(memory_lines[:3]) if memory_lines else "- none"
        return "\n".join(
            [
                "You are running as a direct Codex execution for personal-agent.",
                f"Work from this repository root: {cwd}",
                "Use the repository's local rules and skills.",
                "Implement directly when needed.",
                "Return markdown only.",
                "Include these sections:",
                "- Summary",
                "- Changes",
                "- Verification",
                "- Outputs",
                "In Outputs, list any branch, PR, file paths, or artifacts created.",
                "",
                f"Task: {intent}",
                "Relevant memory:",
                memory_block,
            ]
        )

    def _extract_output_refs(self, text: str) -> dict[str, list[str]]:
        refs = {
            "pull_requests": sorted(set(re.findall(r"\bPR\s*[#:]\s*([0-9]+)\b", text, flags=re.IGNORECASE))),
            "branches": sorted(set(re.findall(r"\bbranch:\s*([A-Za-z0-9._/-]+)", text, flags=re.IGNORECASE))),
            "paths": sorted(
                {
                    match
                    for match in re.findall(r"`([^`\n]+/[^\n`]+)`", text)
                    if not match.startswith("http") and not match.startswith("https")
                }
            ),
        }
        return {key: value for key, value in refs.items() if value}

    def _task_title(self, text: str) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= 100 else compact[:97] + "..."

    def _merged_task_metadata(self, task: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(task.get("metadata") or {})
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                nested = dict(merged[key])
                nested.update(value)
                merged[key] = nested
            else:
                merged[key] = value
        return merged

    def _read_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

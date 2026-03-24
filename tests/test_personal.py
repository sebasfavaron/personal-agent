from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


class FakeOperationalMemoryService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.store = type("Store", (), {"db_path": db_path})()
        self.memories: dict[str, dict] = {}
        self.projects: dict[str, dict] = {}
        self.repos: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.task_runs: dict[str, dict] = {}
        self.artifacts: dict[str, dict] = {}
        self.approvals: dict[str, dict] = {}
        self._counters = {
            "mem": 0,
            "task": 0,
            "run": 0,
            "artifact": 0,
            "approval": 0,
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{prefix}_{self._counters[prefix]:04d}"

    def create_project(self, project_id: str, name: str, description: str) -> dict:
        project = self.projects.get(project_id)
        if project is None:
            project = {"id": project_id, "name": name, "description": description}
            self.projects[project_id] = project
        return dict(project)

    def create_repo(self, repo_id: str, name: str, project_id: str, path: str) -> dict:
        repo = self.repos.get(repo_id)
        if repo is None:
            repo = {"id": repo_id, "name": name, "project_id": project_id, "path": path}
            self.repos[repo_id] = repo
        return dict(repo)

    def _text_embedding(self, text: str) -> list[float]:
        return [float(len(text))]

    def ingest(self, memory_input: dict) -> dict:
        memory_id = memory_input.get("id", self._next_id("mem"))
        now = self._now()
        existing = self.memories.get(memory_id)
        memory = {
            "id": memory_id,
            "type": memory_input["type"],
            "scope": memory_input["scope"],
            "status": memory_input.get("status", "active"),
            "project_id": memory_input.get("project_id"),
            "repo_id": memory_input.get("repo_id"),
            "agent_id": memory_input.get("agent_id"),
            "source_kind": memory_input.get("source_kind", "manual"),
            "title": memory_input["title"],
            "content": memory_input["content"],
            "summary": memory_input.get("summary") or memory_input["content"][:180],
            "confidence": float(memory_input.get("confidence", 1.0)),
            "freshness": float(memory_input.get("freshness", 1.0)),
            "created_at": memory_input.get("created_at", existing["created_at"] if existing else now),
            "updated_at": now,
            "observed_at": memory_input.get("observed_at", now),
            "source_ref": memory_input.get("source_ref"),
            "evidence_ref": memory_input.get("evidence_ref"),
            "embedding": memory_input.get("embedding"),
            "metadata": dict(memory_input.get("metadata") or {}),
        }
        self.memories[memory_id] = memory
        return dict(memory)

    def get_memory(self, memory_id: str) -> dict:
        return dict(self.memories[memory_id])

    def list_memories(
        self,
        *,
        status="active",
        scope=None,
        memory_type=None,
        project_id=None,
        repo_id=None,
        source_ref=None,
        evidence_ref=None,
        metadata=None,
        limit=50,
    ) -> list[dict]:
        items = list(self.memories.values())
        if status is not None:
            items = [item for item in items if item["status"] == status]
        if scope is not None:
            items = [item for item in items if item["scope"] == scope]
        if memory_type is not None:
            items = [item for item in items if item["type"] == memory_type]
        if project_id is not None:
            items = [item for item in items if item.get("project_id") == project_id]
        if repo_id is not None:
            items = [item for item in items if item.get("repo_id") == repo_id]
        if source_ref is not None:
            items = [item for item in items if item.get("source_ref") == source_ref]
        if evidence_ref is not None:
            items = [item for item in items if item.get("evidence_ref") == evidence_ref]
        for key, value in (metadata or {}).items():
            items = [item for item in items if item.get("metadata", {}).get(key) == value]
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return [dict(item) for item in items[:limit]]

    def search(self, query: str, scopes: list[str] | None = None, limit: int = 10) -> dict:
        normalized = query.lower()
        items = list(self.memories.values())
        if scopes is not None:
            items = [item for item in items if item["scope"] in scopes]
        matches = []
        for item in items:
            haystack = " ".join([item["title"], item["summary"], item["content"]]).lower()
            if normalized and normalized not in haystack:
                continue
            matches.append(
                {
                    "memory": dict(item),
                    "matched_scope": item["scope"],
                    "explanation": "fake lexical match",
                }
            )
        return {"retrieval_id": "fake", "results": matches[:limit]}

    def create_task(self, title: str, intent: str, **kwargs) -> dict:
        task_id = kwargs.get("task_id") or self._next_id("task")
        now = self._now()
        task = {
            "id": task_id,
            "title": title,
            "intent": intent,
            "kind": kwargs.get("kind", "task"),
            "status": kwargs.get("status", "open"),
            "priority": kwargs.get("priority", 0),
            "project_id": kwargs.get("project_id"),
            "repo_id": kwargs.get("repo_id"),
            "parent_task_id": kwargs.get("parent_task_id"),
            "origin": kwargs.get("origin", "test"),
            "owner_agent": kwargs.get("owner_agent"),
            "metadata": dict(kwargs.get("metadata") or {}),
            "blocked_reason": kwargs.get("blocked_reason"),
            "requires_human_input": kwargs.get("requires_human_input", False),
            "due_at": kwargs.get("due_at"),
            "created_at": now,
            "updated_at": now,
        }
        self.tasks[task_id] = task
        return dict(task)

    def update_task(self, task_id: str, **changes) -> dict:
        task = self.tasks[task_id]
        metadata = changes.pop("metadata", None)
        for key, value in changes.items():
            task[key] = value
        if metadata is not None:
            merged = dict(task.get("metadata") or {})
            merged.update(metadata)
            task["metadata"] = merged
        task["updated_at"] = self._now()
        return dict(task)

    def get_task(self, task_id: str) -> dict:
        return dict(self.tasks[task_id])

    def list_tasks(self, *, owner_agent=None, limit=50, **kwargs) -> list[dict]:
        items = list(self.tasks.values())
        if owner_agent is not None:
            items = [item for item in items if item.get("owner_agent") == owner_agent]
        if "status" in kwargs and kwargs["status"] is not None:
            items = [item for item in items if item["status"] == kwargs["status"]]
        return [dict(item) for item in items[:limit]]

    def start_task_run(self, task_id: str, agent_id: str, input_payload: dict | None = None, metadata: dict | None = None) -> dict:
        run_id = self._next_id("run")
        now = self._now()
        run = {
            "id": run_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "running",
            "input_payload": dict(input_payload or {}),
            "metadata": dict(metadata or {}),
            "result_summary": None,
            "error_message": None,
            "started_at": now,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.task_runs[run_id] = run
        return dict(run)

    def get_task_run(self, run_id: str) -> dict:
        return dict(self.task_runs[run_id])

    def finish_task_run(self, run_id: str, *, status: str, result_summary: str | None = None, error_message: str | None = None) -> dict:
        run = self.task_runs[run_id]
        run["status"] = status
        run["result_summary"] = result_summary
        run["error_message"] = error_message
        run["completed_at"] = self._now()
        run["updated_at"] = self._now()
        return dict(run)

    def list_task_runs(self, *, task_id=None, status=None, limit=50) -> list[dict]:
        items = list(self.task_runs.values())
        if task_id is not None:
            items = [item for item in items if item["task_id"] == task_id]
        if status is not None:
            items = [item for item in items if item["status"] == status]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return [dict(item) for item in items[:limit]]

    def create_artifact(self, task_id: str, artifact_type: str, title: str, content: str, source_ref: str, **kwargs) -> dict:
        artifact_id = self._next_id("artifact")
        now = self._now()
        artifact = {
            "id": artifact_id,
            "task_id": task_id,
            "artifact_type": artifact_type,
            "title": title,
            "content": content,
            "format": kwargs.get("fmt", "md"),
            "source_ref": source_ref,
            "metadata": dict(kwargs.get("metadata") or {}),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        self.artifacts[artifact_id] = artifact
        return dict(artifact)

    def list_artifacts(self, *, task_id=None, limit=50) -> list[dict]:
        items = list(self.artifacts.values())
        if task_id is not None:
            items = [item for item in items if item["task_id"] == task_id]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return [dict(item) for item in items[:limit]]

    def get_artifact(self, artifact_id: str) -> dict:
        return dict(self.artifacts[artifact_id])

    def task_bundle(self, task_id: str) -> dict:
        return {
            "task": self.get_task(task_id),
            "children": [],
            "runs": self.list_task_runs(task_id=task_id, limit=100),
            "artifacts": self.list_artifacts(task_id=task_id, limit=100),
            "handoffs": [],
            "approvals": [dict(item) for item in self.list_approvals(limit=100) if item["task_id"] == task_id],
        }

    def create_approval(self, *, task_id: str, kind: str, risk_level: str, payload: dict, status: str = "pending") -> dict:
        approval_id = self._next_id("approval")
        now = self._now()
        approval = {
            "id": approval_id,
            "task_id": task_id,
            "kind": kind,
            "status": status,
            "risk_level": risk_level,
            "payload": dict(payload),
            "resolution_note": None,
            "requested_at": now,
            "resolved_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.approvals[approval_id] = approval
        return dict(approval)

    def get_approval(self, approval_id: str) -> dict:
        return dict(self.approvals[approval_id])

    def list_approvals(self, *, status=None, limit=50) -> list[dict]:
        items = list(self.approvals.values())
        if status is not None:
            items = [item for item in items if item["status"] == status]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return [dict(item) for item in items[:limit]]

    def resolve_approval(self, approval_id: str, *, status: str, resolution_note: str | None = None) -> dict:
        approval = self.approvals[approval_id]
        approval["status"] = status
        approval["resolution_note"] = resolution_note
        approval["resolved_at"] = self._now()
        approval["updated_at"] = self._now()
        return dict(approval)


class PersonalAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.agents_db_dir = Path(self.tmp.name) / "agents-database"
        self.agents_db_dir.mkdir()
        self._original_env = {
            "PERSONAL_AGENT_DATA_DIR": os.environ.get("PERSONAL_AGENT_DATA_DIR"),
            "PERSONAL_AGENT_SHARED_MEMORY_ROOT": os.environ.get("PERSONAL_AGENT_SHARED_MEMORY_ROOT"),
            "PERSONAL_AGENT_SHARED_MEMORY_DB_PATH": os.environ.get("PERSONAL_AGENT_SHARED_MEMORY_DB_PATH"),
        }
        os.environ["PERSONAL_AGENT_DATA_DIR"] = self.tmp.name
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_ROOT"] = str(self.agents_db_dir)
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_DB_PATH"] = str(Path(self.tmp.name) / "shared-agent-memory.sqlite3")

        from personal_agent import config
        from personal_agent import shared_memory

        self._original_config = {
            "BASE_DIR": config.BASE_DIR,
            "SHARED_MEMORY_ROOT": config.SHARED_MEMORY_ROOT,
            "SHARED_MEMORY_SRC_DIR": config.SHARED_MEMORY_SRC_DIR,
            "SHARED_MEMORY_DB_PATH": config.SHARED_MEMORY_DB_PATH,
        }
        self._original_shared_memory = {
            "SHARED_MEMORY_SRC_DIR": shared_memory.SHARED_MEMORY_SRC_DIR,
            "SHARED_MEMORY_DB_PATH": shared_memory.SHARED_MEMORY_DB_PATH,
        }
        config.BASE_DIR = Path(self.tmp.name)
        config.SHARED_MEMORY_ROOT = self.agents_db_dir
        config.SHARED_MEMORY_SRC_DIR = self.agents_db_dir / "src"
        config.SHARED_MEMORY_DB_PATH = Path(self.tmp.name) / "shared-agent-memory.sqlite3"
        shared_memory.SHARED_MEMORY_SRC_DIR = config.SHARED_MEMORY_SRC_DIR
        shared_memory.SHARED_MEMORY_DB_PATH = config.SHARED_MEMORY_DB_PATH

        self.fake_operational_memory = FakeOperationalMemoryService(str(config.SHARED_MEMORY_DB_PATH))
        self.runtime_memory_patcher = patch("personal_agent.runtime.get_memory_service", return_value=self.fake_operational_memory)
        self.research_store_memory_patcher = patch(
            "personal_agent.research_store.shared_memory.get_memory_service",
            return_value=self.fake_operational_memory,
        )
        self.runtime_memory_patcher.start()
        self.research_store_memory_patcher.start()

    def tearDown(self) -> None:
        from personal_agent import config
        from personal_agent import shared_memory

        self.runtime_memory_patcher.stop()
        self.research_store_memory_patcher.stop()
        config.BASE_DIR = self._original_config["BASE_DIR"]
        config.SHARED_MEMORY_ROOT = self._original_config["SHARED_MEMORY_ROOT"]
        config.SHARED_MEMORY_SRC_DIR = self._original_config["SHARED_MEMORY_SRC_DIR"]
        config.SHARED_MEMORY_DB_PATH = self._original_config["SHARED_MEMORY_DB_PATH"]
        shared_memory.SHARED_MEMORY_SRC_DIR = self._original_shared_memory["SHARED_MEMORY_SRC_DIR"]
        shared_memory.SHARED_MEMORY_DB_PATH = self._original_shared_memory["SHARED_MEMORY_DB_PATH"]
        self.tmp.cleanup()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _wait_for_task_status(self, runtime, task_id: str, expected: str, timeout: float = 1.5) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = runtime.service.get_task(task_id)
            if task["status"] == expected:
                return task
            time.sleep(0.01)
        self.fail(f"task {task_id} did not reach status {expected}")

    def _fake_repo_dir(self) -> str:
        repo_dir = Path(self.tmp.name) / "repo-under-test"
        repo_dir.mkdir(exist_ok=True)
        return str(repo_dir)

    def test_runtime_intake_creates_draft_task_with_suggested_cwd(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        result = runtime.intake("Implement the fix in ai-dev-workflow")

        self.assertEqual(result.task["status"], "draft")
        self.assertEqual(result.task["repo_id"], "repo_ai_dev_workflow")
        execution = result.task["metadata"]["execution"]
        self.assertIn("ai-dev-workflow", execution["suggested_cwd"])
        self.assertEqual(execution["permission_mode"], "danger-full-access")
        self.assertIn("Outputs", execution["prompt_preview"])

    def test_available_cwd_options_prefers_known_repos_and_reads_workspace_dirs(self) -> None:
        from personal_agent import repo_targets

        workspace_root = Path(self.tmp.name) / "Code"
        workspace_root.mkdir()
        (workspace_root / "street-cast-pwa").mkdir()
        (workspace_root / "zeta-tool").mkdir()
        (workspace_root / "node_modules").mkdir()
        hidden_dir = workspace_root / ".cache"
        hidden_dir.mkdir()

        known_repo = Path(self.tmp.name) / "personal-agent"
        known_repo.mkdir()

        with patch.object(repo_targets, "PERSONAL_ROOT", known_repo), patch.object(repo_targets, "WORKSPACE_ROOT", workspace_root):
            options = repo_targets.available_cwd_options()

        option_paths = [item["path"] for item in options]
        option_names = [item["name"] for item in options]

        self.assertIn(str(known_repo.resolve()), option_paths)
        self.assertIn(str((workspace_root / "street-cast-pwa").resolve()), option_paths)
        self.assertIn("street-cast-pwa", option_names)
        self.assertNotIn(str((workspace_root / "node_modules").resolve()), option_paths)
        self.assertNotIn(str(hidden_dir.resolve()), option_paths)

    def test_add_structured_task_creates_runtime_visible_draft(self) -> None:
        from personal_agent.research_store import add_structured_task

        parent_payload = add_structured_task(None, "Unify open and draft into one backlog state", kind="task")
        child_payload = add_structured_task(None, "Update task creation defaults", kind="subtask", parent_task_id=parent_payload["id"])

        parent = self.fake_operational_memory.get_task(parent_payload["id"])
        child = self.fake_operational_memory.get_task(child_payload["id"])

        self.assertEqual(parent["status"], "draft")
        self.assertEqual(parent["owner_agent"], "personal-agent")
        self.assertEqual(parent["project_id"], "proj_personal_agent")
        self.assertEqual(parent["repo_id"], "repo_ai_dev_workflow")
        self.assertIn("execution", parent["metadata"])
        self.assertEqual(child["status"], "draft")
        self.assertEqual(child["parent_task_id"], parent["id"])

    def test_runtime_start_task_launches_codex_with_confirmed_cwd(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        intake = runtime.intake("Implement the fix in ai-dev-workflow")
        fake_repo_dir = self._fake_repo_dir()
        seen: list[list[str]] = []

        class FakePopen:
            def __init__(self, command, stdout, stderr, text):
                del text
                seen.append(command)
                self.pid = 4321
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text("# Summary\n\nDone.\n\n## Outputs\n- branch: feat/test\n", encoding="utf-8")
                stdout.write("stdout ok\n")
                stdout.flush()
                stderr.flush()
                self._returncode = 0

            def wait(self):
                return self._returncode

            def poll(self):
                return self._returncode

            def terminate(self):
                self._returncode = -15

        with patch("personal_agent.runtime.subprocess.Popen", FakePopen):
            payload = runtime.start_task(intake.task["id"], fake_repo_dir)

        task = self._wait_for_task_status(runtime, intake.task["id"], "completed")
        self.assertEqual(payload["run"]["task_id"], intake.task["id"])
        self.assertTrue(seen)
        self.assertIn("danger-full-access", seen[0])
        self.assertEqual(seen[0][seen[0].index("-C") + 1], str(Path(fake_repo_dir).resolve()))
        artifacts = runtime.service.list_artifacts(task_id=intake.task["id"], limit=5)
        self.assertEqual(artifacts[0]["artifact_type"], "report")
        self.assertEqual(task["metadata"]["execution"]["result_artifact_id"], artifacts[0]["id"])

    def test_runtime_start_task_marks_failure_and_persists_logs(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        intake = runtime.intake("Implement the fix in ai-dev-workflow")
        fake_repo_dir = self._fake_repo_dir()

        class FakePopen:
            def __init__(self, command, stdout, stderr, text):
                del command, text
                self.pid = 7654
                stdout.write("partial stdout\n")
                stderr.write("boom stderr\n")
                stdout.flush()
                stderr.flush()
                self._returncode = 1

            def wait(self):
                return self._returncode

            def poll(self):
                return self._returncode

            def terminate(self):
                self._returncode = -15

        with patch("personal_agent.runtime.subprocess.Popen", FakePopen):
            runtime.start_task(intake.task["id"], fake_repo_dir)

        task = self._wait_for_task_status(runtime, intake.task["id"], "failed")
        run = runtime.service.list_task_runs(task_id=intake.task["id"], limit=1)[0]
        artifact = runtime.service.list_artifacts(task_id=intake.task["id"], limit=1)[0]
        self.assertEqual(run["status"], "failed")
        self.assertEqual(artifact["artifact_type"], "run_failure")
        self.assertIn("boom stderr", artifact["content"])
        self.assertEqual(task["metadata"]["execution"]["failure_artifact_id"], artifact["id"])

    def test_runtime_rejects_invalid_cwd_on_start(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        intake = runtime.intake("Implement the fix in ai-dev-workflow")

        with self.assertRaisesRegex(ValueError, "Invalid cwd"):
            runtime.start_task(intake.task["id"], "/path/does/not/exist")

    def test_runtime_recovers_interrupted_runs_and_restarts_them(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        fake_repo_dir = self._fake_repo_dir()
        task = runtime.service.create_task(
            title="Interrupted work",
            intent="Resume after restart",
            kind="task",
            status="in_progress",
            project_id="proj_personal_agent",
            repo_id="repo_ai_dev_workflow",
            owner_agent="personal-agent",
            metadata={"execution": {"cwd": fake_repo_dir, "prompt_preview": "Resume after restart"}},
        )
        run = runtime.service.start_task_run(task["id"], "personal-agent", input_payload={"cwd": fake_repo_dir})

        class FakePopen:
            def __init__(self, command, stdout, stderr, text):
                del text
                self.pid = 2468
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text("# Summary\n\nRecovered.\n", encoding="utf-8")
                stdout.write("stdout ok\n")
                stdout.flush()
                stderr.flush()
                self._returncode = 0

            def wait(self):
                return self._returncode

            def poll(self):
                return self._returncode

            def terminate(self):
                self._returncode = -15

        with patch("personal_agent.runtime.subprocess.Popen", FakePopen):
            recovered = PersonalAgentRuntime()

        updated_task = self._wait_for_task_status(recovered, task["id"], "completed")
        runs = recovered.service.list_task_runs(task_id=task["id"], limit=5)
        updated_run = recovered.service.get_task_run(run["id"])

        self.assertEqual(updated_run["status"], "paused")
        self.assertEqual(updated_task["status"], "completed")
        self.assertEqual(updated_task["metadata"]["execution"]["recovered_run_id"], run["id"])
        self.assertEqual(updated_task["metadata"]["execution"]["resumed_from_run_id"], run["id"])
        self.assertEqual(runs[0]["status"], "succeeded")

    def test_pause_running_tasks_leaves_restartable_draft_and_watcher_does_not_fail_it(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        intake = runtime.intake("Implement the fix in ai-dev-workflow")
        fake_repo_dir = self._fake_repo_dir()
        terminated = threading.Event()

        class FakePopen:
            def __init__(self, command, stdout, stderr, text):
                del command, text
                self.pid = 8642
                self._returncode = None
                stdout.write("working\n")
                stdout.flush()
                stderr.flush()

            def wait(self):
                terminated.wait(timeout=1.0)
                return -15 if self._returncode is None else self._returncode

            def poll(self):
                return self._returncode

            def terminate(self):
                self._returncode = -15
                terminated.set()

        with patch("personal_agent.runtime.subprocess.Popen", FakePopen):
            payload = runtime.start_task(intake.task["id"], fake_repo_dir)
            pause_payload = runtime.pause_running_tasks("test restart")
            runtime.stop()

        time.sleep(0.05)
        task = runtime.service.get_task(intake.task["id"])
        run = runtime.service.get_task_run(payload["run"]["id"])

        self.assertEqual(pause_payload["count"], 1)
        self.assertEqual(run["status"], "paused")
        self.assertEqual(task["status"], "draft")
        self.assertTrue(task["metadata"]["execution"]["auto_restart_on_daemon_start"])
        self.assertEqual(runtime.service.list_artifacts(task_id=intake.task["id"], limit=5), [])

    def test_dashboard_snapshot_groups_drafts_running_failed_and_results(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        draft = runtime.intake("Implement the fix in ai-dev-workflow").task
        running = runtime.service.create_task(
            title="Running work",
            intent="Run codex",
            kind="task",
            status="in_progress",
            project_id="proj_personal_agent",
            repo_id="repo_ai_dev_workflow",
            owner_agent="personal-agent",
            metadata={"execution": {"cwd": "/Users/sebas/Code/ai-dev-workflow", "permission_mode": "danger-full-access"}},
        )
        runtime.service.start_task_run(running["id"], "personal-agent", input_payload={"cwd": "/Users/sebas/Code/ai-dev-workflow"})
        failed = runtime.service.create_task(
            title="Failed work",
            intent="Bad run",
            kind="task",
            status="failed",
            project_id="proj_personal_agent",
            repo_id="repo_ai_dev_workflow",
            owner_agent="personal-agent",
            metadata={"execution": {"cwd": "/Users/sebas/Code/ai-dev-workflow"}},
        )
        done = runtime.service.create_task(
            title="Completed work",
            intent="Done",
            kind="task",
            status="completed",
            project_id="proj_personal_agent",
            repo_id="repo_ai_dev_workflow",
            owner_agent="personal-agent",
            metadata={"execution": {"cwd": "/Users/sebas/Code/ai-dev-workflow"}},
        )
        runtime.service.create_artifact(
            task_id=done["id"],
            artifact_type="report",
            title="Run result",
            content="# Summary\n\nDone.",
            source_ref="personal-agent",
            metadata={"classification": "deliverable"},
        )

        payload = runtime.dashboard_snapshot()

        self.assertEqual(payload["summary"]["draft_count"], 1)
        self.assertEqual(payload["summary"]["running_count"], 1)
        self.assertEqual(payload["summary"]["failed_count"], 1)
        self.assertEqual(payload["summary"]["result_count"], 1)
        self.assertEqual(payload["draft_tasks"][0]["id"], draft["id"])
        self.assertEqual(payload["active_runs"][0]["id"], running["id"])
        self.assertEqual(payload["failed_tasks"][0]["id"], failed["id"])
        self.assertEqual(payload["recent_results"][0]["task_title"], done["title"])
        self.assertTrue(payload["cwd_options"])

    def test_next_tasks_prefers_draft_tasks(self) -> None:
        from personal_agent.research_store import next_tasks

        self.fake_operational_memory.create_task(
            title="Open legacy",
            intent="old",
            kind="task",
            status="open",
            metadata={"legacy_kind": "task"},
        )
        draft = self.fake_operational_memory.create_task(
            title="Draft task",
            intent="new",
            kind="task",
            status="draft",
            metadata={"legacy_kind": "task"},
        )

        payload = next_tasks(limit=5)

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], draft["id"])

    def test_research_run_uses_canonical_memory_schema(self) -> None:
        from personal_agent.research_store import add_claim, add_source, get_run, start_research
        from personal_agent.shared_memory import PERSONAL_MEMORY_SCHEMA

        payload = start_research("Map remaining memory surfaces", "repo cleanup", "shared db present")
        run_id = payload["run"]["id"]
        add_source(run_id, "https://example.com/spec", "Spec", "canonical metadata")
        add_claim(run_id, "legacy tags should disappear from reads", 0.9, source_url="https://example.com/spec")

        run = get_run(run_id)
        related = self.fake_operational_memory.list_memories(source_ref=f"personal-agent:run:{run_id}", limit=20)

        self.assertEqual(run["run"]["id"], run_id)
        self.assertEqual(len(run["sources"]), 1)
        self.assertEqual(len(run["claims"]), 1)
        self.assertTrue(related)
        self.assertTrue(all(memory["metadata"].get("schema") == PERSONAL_MEMORY_SCHEMA for memory in related))
        self.assertTrue(all("legacy_kind" not in memory["metadata"] for memory in related))

    def test_request_and_resolve_approval_use_native_approval_records(self) -> None:
        from personal_agent.research_store import list_approvals, request_approval, resolve_approval

        created = request_approval("external_action", {"target": "email draft"}, "high")
        pending = list_approvals()
        resolved = resolve_approval(created["id"], "approved", "ship it")
        task = self.fake_operational_memory.get_task(created["task_id"])

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], created["id"])
        self.assertEqual(resolved["status"], "approved")
        self.assertEqual(task["status"], "completed")
        self.assertFalse(task["requires_human_input"])
        self.assertEqual(task["metadata"]["approval_status"], "approved")

    def test_migration_rewrites_legacy_records_and_archives_legacy_approval_memory(self) -> None:
        from personal_agent.migration import migrate_legacy_memory
        from personal_agent.research_store import get_run, list_approvals

        self.fake_operational_memory.ingest(
            {
                "id": "legacy_run_run-123",
                "type": "episode",
                "scope": "global",
                "status": "active",
                "source_kind": "run",
                "title": "Research run: Legacy cleanup",
                "content": "Goal: Legacy cleanup\nScope: Repo\nAssumptions: None\nSummary: Pending",
                "summary": "Pending",
                "source_ref": "personal-agent:run:run-123",
                "evidence_ref": "personal-agent:run:run-123",
                "metadata": {"legacy_system": "personal-agent", "legacy_kind": "research_run", "legacy_run_id": "run-123", "run_status": "active"},
            }
        )
        self.fake_operational_memory.ingest(
            {
                "id": "legacy_claim_run-123",
                "type": "artifact",
                "scope": "global",
                "status": "active",
                "source_kind": "manual",
                "title": "Research claim: Old claim",
                "content": "Old claim",
                "summary": "Old claim",
                "source_ref": "personal-agent:run:run-123",
                "metadata": {"legacy_system": "personal-agent", "legacy_kind": "claim", "legacy_run_id": "run-123", "claim_status": "tentative"},
            }
        )
        approval_memory = self.fake_operational_memory.ingest(
            {
                "id": "mem_legacy_approval",
                "type": "artifact",
                "scope": "global",
                "status": "active",
                "source_kind": "manual",
                "title": "Approval request: outreach",
                "content": '{"target":"vendor"}',
                "summary": "outreach",
                "source_ref": "personal-agent:approval",
                "metadata": {
                    "legacy_system": "personal-agent",
                    "legacy_kind": "approval_request",
                    "approval_kind": "outreach",
                    "approval_status": "pending",
                    "risk_level": "high",
                    "payload": {"target": "vendor"},
                },
            }
        )

        migrated = migrate_legacy_memory()
        run = get_run("run-123")
        approvals = list_approvals()
        archived = self.fake_operational_memory.get_memory(approval_memory["id"])

        self.assertEqual(migrated["status"], "migrated")
        self.assertEqual(migrated["migrated"]["runs"], 1)
        self.assertEqual(migrated["migrated"]["claims"], 1)
        self.assertEqual(migrated["migrated"]["approvals"], 1)
        self.assertEqual(run["run"]["id"], "run-123")
        self.assertEqual(len(run["claims"]), 1)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(archived["metadata"]["schema"], "personal-agent-memory-v1")

    def test_daemon_http_api_covers_status_intake_and_start(self) -> None:
        from personal_agent.daemon import PersonalAgentHandler
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        server = type("Server", (), {"runtime": runtime})()
        fake_repo_dir = self._fake_repo_dir()

        class FakePopen:
            def __init__(self, command, stdout, stderr, text):
                del text
                self.pid = 9988
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text("# Summary\n\nDone from API.\n", encoding="utf-8")
                stdout.write("ok\n")
                stdout.flush()
                stderr.flush()
                self._returncode = 0

            def wait(self):
                return self._returncode

            def poll(self):
                return self._returncode

            def terminate(self):
                self._returncode = -15

        class TestHandler(PersonalAgentHandler):
            def __init__(self, method: str, path: str, body: dict | None = None):
                payload = json.dumps(body or {}).encode("utf-8")
                request = (
                    f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n".encode(
                        "utf-8"
                    )
                    + payload
                )
                self.rfile = BytesIO(request)
                self.wfile = BytesIO()
                self.raw_requestline = self.rfile.readline()
                self.error_code = None
                self.error_message = None
                self.server = server
                self.client_address = ("127.0.0.1", 12345)
                self.setup()
                if self.parse_request():
                    getattr(self, f"do_{method}")()
                self.finish()

            def setup(self) -> None:
                return

            def finish(self) -> None:
                return

        with patch("personal_agent.runtime.subprocess.Popen", FakePopen):
            intake_handler = TestHandler("POST", "/api/intake", {"input": "Implement the fix in ai-dev-workflow"})
            intake_handler.wfile.seek(0)
            intake_response = intake_handler.wfile.getvalue()
            intake_task_id = json.loads(intake_response.split(b"\r\n\r\n", 1)[1])["task"]["id"]

            start_handler = TestHandler(
                "POST",
                f"/api/tasks/{intake_task_id}/start",
                {"cwd": fake_repo_dir, "prompt": "Custom prompt"},
            )
            status_handler = TestHandler("GET", "/api/status")

        runtime_task = self._wait_for_task_status(runtime, intake_task_id, "completed")
        self.assertEqual(runtime_task["status"], "completed")

        intake_handler.wfile.seek(0)
        start_handler.wfile.seek(0)
        status_handler.wfile.seek(0)
        self.assertIn(b"201", intake_handler.wfile.getvalue().splitlines()[0])
        self.assertIn(b"200", start_handler.wfile.getvalue().splitlines()[0])
        self.assertIn(b"200", status_handler.wfile.getvalue().splitlines()[0])
        status_payload = json.loads(status_handler.wfile.getvalue().split(b"\r\n\r\n", 1)[1])
        self.assertIn("cwd_options", status_payload)
        self.assertTrue(status_payload["cwd_options"])

    def test_daemon_renders_markdown_links_in_artifacts(self) -> None:
        from personal_agent.daemon import PersonalAgentHandler

        handler = PersonalAgentHandler.__new__(PersonalAgentHandler)
        rendered = handler._render_markdown(
            "Abrir [USECASE.md](http://127.0.0.1:8082/artifacts/art_b90cb99f638c45ecbb358d2f51cdad89) y `code`."
        )
        self.assertIn(
            '<a href="/artifacts/art_b90cb99f638c45ecbb358d2f51cdad89">USECASE.md</a>',
            rendered,
        )
        self.assertIn(
            '<a href="https://link.com" target="_blank" rel="noreferrer">txt</a>',
            handler._render_markdown("[txt](link.com)"),
        )
        self.assertIn(
            '<a href="link" target="_blank" rel="noreferrer">tct</a>',
            handler._render_markdown("[tct](link)"),
        )
        self.assertIn("<code>code</code>", rendered)

        page = handler._artifact_page(
            {
                "id": "art-1",
                "task_id": "task-1",
                "artifact_type": "report",
                "title": "Rendered artifact",
                "content": '[safe](javascript:alert(1)) [ok](http://127.0.0.1:8082/artifacts/art-1)',
            }
        )
        self.assertIn("[safe](javascript:alert(1))", page)
        self.assertIn(
            '<a href="/artifacts/art-1">ok</a>',
            page,
        )

    def test_runtime_codex_command_adds_shared_memory_repo_as_writable_dir(self) -> None:
        from personal_agent.runtime import CODEX_ADD_DIRS, PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Probe codex command",
            intent="Need to verify codex add-dir wiring",
            owner_agent=PERSONAL_AGENT_ID,
            status="draft",
            metadata={"execution": {"cwd": str(self._fake_repo_dir())}},
        )
        seen: list[list[str]] = []

        class FakePopen:
            def __init__(self, command, stdout, stderr, text):
                del text
                seen.append(command)
                self.pid = 7777
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text("# Report\n\nAll good.\n", encoding="utf-8")
                stdout.flush()
                stderr.flush()
                self._returncode = 0

            def wait(self):
                return self._returncode

            def poll(self):
                return self._returncode

            def terminate(self):
                self._returncode = -15

        with patch("personal_agent.runtime.subprocess.Popen", FakePopen):
            runtime.start_task(task["id"], self._fake_repo_dir())

        codex_commands = [
            command
            for command in seen
            if len(command) >= 2 and Path(command[0]).name == "codex" and command[1] == "exec"
        ]
        self.assertTrue(codex_commands)
        self.assertIn("-C", codex_commands[0])
        self.assertIn("--add-dir", codex_commands[0])
        add_dir_value = codex_commands[0][codex_commands[0].index("--add-dir") + 1]
        self.assertEqual(add_dir_value, str(CODEX_ADD_DIRS[0]))

    def test_daemon_renders_source_references_as_internal_links(self) -> None:
        from personal_agent.daemon import PersonalAgentHandler

        handler = PersonalAgentHandler.__new__(PersonalAgentHandler)
        rendered = handler._render_markdown(
            "# Report\n\nClaim backed by [S1][S2].\n\n## Fuentes primarias usadas\n- [S1] Source one: https://example.com/1\n- [S2] Source two: https://example.com/2\n"
        )

        self.assertIn('<a href="#ref-s1">[S1]</a>', rendered)
        self.assertIn('<a href="#ref-s2">[S2]</a>', rendered)
        self.assertIn('<li id="ref-s1">', rendered)
        self.assertIn('<li id="ref-s2">', rendered)


if __name__ == "__main__":
    unittest.main()

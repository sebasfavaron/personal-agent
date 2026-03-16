from __future__ import annotations

import json
import os
import tempfile
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
        self.projects: dict[str, dict] = {}
        self.repos: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.task_runs: dict[str, dict] = {}
        self.artifacts: dict[str, dict] = {}
        self._counters = {
            "task": 0,
            "run": 0,
            "artifact": 0,
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

    def search(self, query: str, scopes: list[str] | None = None, limit: int = 10) -> dict:
        del query, scopes, limit
        return {"retrieval_id": "fake", "results": []}

    def create_task(self, title: str, intent: str, **kwargs) -> dict:
        task_id = self._next_id("task")
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
            "approvals": [],
        }


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
            "DATA_DIR": config.DATA_DIR,
            "SHARED_MEMORY_ROOT": config.SHARED_MEMORY_ROOT,
            "SHARED_MEMORY_SRC_DIR": config.SHARED_MEMORY_SRC_DIR,
            "SHARED_MEMORY_DB_PATH": config.SHARED_MEMORY_DB_PATH,
        }
        self._original_shared_memory = {
            "SHARED_MEMORY_SRC_DIR": shared_memory.SHARED_MEMORY_SRC_DIR,
            "SHARED_MEMORY_DB_PATH": shared_memory.SHARED_MEMORY_DB_PATH,
        }
        config.DATA_DIR = Path(self.tmp.name)
        config.SHARED_MEMORY_ROOT = self.agents_db_dir
        config.SHARED_MEMORY_SRC_DIR = self.agents_db_dir / "src"
        config.SHARED_MEMORY_DB_PATH = Path(self.tmp.name) / "shared-agent-memory.sqlite3"
        shared_memory.SHARED_MEMORY_SRC_DIR = config.SHARED_MEMORY_SRC_DIR
        shared_memory.SHARED_MEMORY_DB_PATH = config.SHARED_MEMORY_DB_PATH

        self.fake_operational_memory = FakeOperationalMemoryService(str(config.SHARED_MEMORY_DB_PATH))
        self.runtime_memory_patcher = patch("personal_agent.runtime.get_memory_service", return_value=self.fake_operational_memory)
        self.runtime_memory_patcher.start()

    def tearDown(self) -> None:
        from personal_agent import config
        from personal_agent import shared_memory

        self.runtime_memory_patcher.stop()
        config.DATA_DIR = self._original_config["DATA_DIR"]
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

    def test_runtime_start_task_launches_codex_with_confirmed_cwd(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        intake = runtime.intake("Implement the fix in ai-dev-workflow")
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
            payload = runtime.start_task(intake.task["id"], "/Users/sebas/Code/ai-dev-workflow")

        task = self._wait_for_task_status(runtime, intake.task["id"], "completed")
        self.assertEqual(payload["run"]["task_id"], intake.task["id"])
        self.assertTrue(seen)
        self.assertIn("danger-full-access", seen[0])
        self.assertEqual(seen[0][seen[0].index("-C") + 1], "/Users/sebas/Code/ai-dev-workflow")
        artifacts = runtime.service.list_artifacts(task_id=intake.task["id"], limit=5)
        self.assertEqual(artifacts[0]["artifact_type"], "report")
        self.assertEqual(task["metadata"]["execution"]["result_artifact_id"], artifacts[0]["id"])

    def test_runtime_start_task_marks_failure_and_persists_logs(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        intake = runtime.intake("Implement the fix in ai-dev-workflow")

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
            runtime.start_task(intake.task["id"], "/Users/sebas/Code/ai-dev-workflow")

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

    def test_runtime_recovers_interrupted_runs_as_failed(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Interrupted work",
            intent="Resume after restart",
            kind="task",
            status="in_progress",
            project_id="proj_personal_agent",
            repo_id="repo_ai_dev_workflow",
            owner_agent="personal-agent",
            metadata={"execution": {"cwd": "/Users/sebas/Code/ai-dev-workflow"}},
        )
        run = runtime.service.start_task_run(task["id"], "personal-agent", input_payload={"cwd": "/Users/sebas/Code/ai-dev-workflow"})

        recovered = PersonalAgentRuntime()
        updated_task = recovered.service.get_task(task["id"])
        updated_run = recovered.service.get_task_run(run["id"])

        self.assertEqual(updated_run["status"], "failed")
        self.assertEqual(updated_task["status"], "failed")
        self.assertEqual(updated_task["metadata"]["execution"]["recovered_run_id"], run["id"])

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

    def test_daemon_http_api_covers_status_intake_and_start(self) -> None:
        from personal_agent.daemon import PersonalAgentHandler
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        server = type("Server", (), {"runtime": runtime})()

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
                {"cwd": "/Users/sebas/Code/ai-dev-workflow", "prompt": "Custom prompt"},
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


if __name__ == "__main__":
    unittest.main()

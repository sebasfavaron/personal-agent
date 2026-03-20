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
        self._counters = {"mem": 0, "task": 0, "run": 0, "artifact": 0}
        self.migrate_calls = 0

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

    def create_memory(self, memory_input: dict) -> dict:
        memory_id = memory_input.get("id", self._next_id("mem"))
        now = self._now()
        existing = self.memories.get(memory_id)
        memory = {
            "id": memory_id,
            "schema_version": memory_input.get("schema_version", "shared-agent-memory-v2"),
            "type": memory_input["type"],
            "subtype": memory_input.get("subtype"),
            "scope": memory_input["scope"],
            "status": memory_input.get("status", "active"),
            "project_id": memory_input.get("project_id"),
            "repo_id": memory_input.get("repo_id"),
            "agent_id": memory_input.get("agent_id"),
            "origin_agent": memory_input.get("origin_agent"),
            "run_id": memory_input.get("run_id"),
            "task_id": memory_input.get("task_id"),
            "url": memory_input.get("url"),
            "domain": memory_input.get("domain"),
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

    ingest = create_memory

    def get_memory(self, memory_id: str) -> dict:
        return dict(self.memories[memory_id])

    def list_memories(
        self,
        *,
        status="active",
        scope=None,
        memory_type=None,
        subtype=None,
        project_id=None,
        repo_id=None,
        source_ref=None,
        evidence_ref=None,
        run_id=None,
        task_id=None,
        origin_agent=None,
        url=None,
        domain=None,
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
        if subtype is not None:
            items = [item for item in items if item.get("subtype") == subtype]
        if project_id is not None:
            items = [item for item in items if item.get("project_id") == project_id]
        if repo_id is not None:
            items = [item for item in items if item.get("repo_id") == repo_id]
        if source_ref is not None:
            items = [item for item in items if item.get("source_ref") == source_ref]
        if evidence_ref is not None:
            items = [item for item in items if item.get("evidence_ref") == evidence_ref]
        if run_id is not None:
            items = [item for item in items if item.get("run_id") == run_id]
        if task_id is not None:
            items = [item for item in items if item.get("task_id") == task_id]
        if origin_agent is not None:
            items = [item for item in items if item.get("origin_agent") == origin_agent]
        if url is not None:
            items = [item for item in items if item.get("url") == url]
        if domain is not None:
            items = [item for item in items if item.get("domain") == domain]
        for key, value in (metadata or {}).items():
            items = [item for item in items if item.get("metadata", {}).get(key) == value]
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return [dict(item) for item in items[:limit]]

    def search(self, query: str, scopes: list[str] | None = None, filters: dict | None = None, limit: int = 10, include_inbox: bool = False) -> dict:
        del include_inbox
        filters = filters or {}
        items = list(self.memories.values())
        if scopes is not None:
            items = [item for item in items if item["scope"] in scopes]
        for key, value in filters.items():
            items = [item for item in items if item.get(key) == value]
        normalized = query.lower().strip()
        matches = []
        for item in items:
            haystack = " ".join([item["title"], item["summary"], item["content"]]).lower()
            if normalized and normalized not in haystack:
                continue
            matches.append({"memory": dict(item), "matched_scope": item["scope"], "explanation": "fake lexical match"})
        return {"retrieval_id": "fake", "results": matches[:limit]}

    def create_task(self, title: str, intent: str, **kwargs) -> dict:
        task_id = kwargs.get("task_id") or self._next_id("task")
        now = self._now()
        task = {
            "id": task_id,
            "schema_version": kwargs.get("schema_version", "shared-agent-memory-v2"),
            "run_id": kwargs.get("run_id"),
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
            task["metadata"] = dict(metadata)
        task["updated_at"] = self._now()
        return dict(task)

    def get_task(self, task_id: str) -> dict:
        return dict(self.tasks[task_id])

    def list_tasks(self, *, owner_agent=None, run_id=None, limit=50, **kwargs) -> list[dict]:
        items = list(self.tasks.values())
        if owner_agent is not None:
            items = [item for item in items if item.get("owner_agent") == owner_agent]
        if run_id is not None:
            items = [item for item in items if item.get("run_id") == run_id]
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
            "status": kwargs.get("status", "active"),
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
        }

    def migrate_v2(self) -> dict:
        self.migrate_calls += 1
        return {"status": "ok", "calls": self.migrate_calls}


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
            "SHARED_MEMORY_DB_PATH": config.SHARED_MEMORY_DB_PATH,
        }
        config.BASE_DIR = Path(self.tmp.name)
        config.SHARED_MEMORY_ROOT = self.agents_db_dir
        config.SHARED_MEMORY_DB_PATH = Path(self.tmp.name) / "shared-agent-memory.sqlite3"

        self.fake_operational_memory = FakeOperationalMemoryService(str(config.SHARED_MEMORY_DB_PATH))
        self.runtime_memory_patcher = patch("personal_agent.runtime.get_memory_service", return_value=self.fake_operational_memory)
        self.research_store_memory_patcher = patch(
            "personal_agent.research_store.shared_memory.get_memory_service",
            return_value=self.fake_operational_memory,
        )
        self.shared_memory_service_patcher = patch(
            "personal_agent.shared_memory.get_memory_service",
            return_value=self.fake_operational_memory,
        )
        self.runtime_memory_patcher.start()
        self.research_store_memory_patcher.start()
        self.shared_memory_service_patcher.start()

    def tearDown(self) -> None:
        from personal_agent import config

        self.runtime_memory_patcher.stop()
        self.research_store_memory_patcher.stop()
        self.shared_memory_service_patcher.stop()
        config.BASE_DIR = self._original_config["BASE_DIR"]
        config.SHARED_MEMORY_ROOT = self._original_config["SHARED_MEMORY_ROOT"]
        config.SHARED_MEMORY_DB_PATH = self._original_config["SHARED_MEMORY_DB_PATH"]
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

    def test_add_structured_task_persists_run_id_in_task_column(self) -> None:
        from personal_agent.research_store import add_structured_task

        payload = add_structured_task("run-123", "Update task creation defaults", kind="subtask")
        task = self.fake_operational_memory.get_task(payload["id"])

        self.assertEqual(task["run_id"], "run-123")
        self.assertEqual(task["schema_version"], "shared-agent-memory-v2")

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
            origin="personal-agent",
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
            origin="personal-agent",
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
            origin="personal-agent",
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

    def test_research_lifecycle_uses_v2_facets_and_no_content_parsing(self) -> None:
        from personal_agent.research_store import add_claim, add_source, close_research, get_run, start_research

        payload = start_research("Map remaining memory surfaces", "repo cleanup", "shared db present")
        run_id = payload["run"]["id"]
        add_source(run_id, "https://example.com/spec", "Spec", "canonical metadata")
        add_claim(run_id, "legacy tags should disappear from reads", 0.9, source_url="https://example.com/spec")
        close_research(run_id, "done")

        run = get_run(run_id)
        sources = self.fake_operational_memory.list_memories(run_id=run_id, subtype="research_source", origin_agent="personal-agent", limit=20)
        claims = self.fake_operational_memory.list_memories(run_id=run_id, subtype="research_claim", origin_agent="personal-agent", limit=20)
        runs = self.fake_operational_memory.list_memories(run_id=run_id, subtype="research_run", origin_agent="personal-agent", limit=5)

        self.assertEqual(run["run"]["scope"], "repo cleanup")
        self.assertEqual(run["run"]["assumptions"], "shared db present")
        self.assertEqual(run["run"]["status"], "completed")
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["url"], "https://example.com/spec")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["domain"], "example.com")
        self.assertEqual(runs[0]["metadata"]["goal"], "Map remaining memory surfaces")

    def test_memory_search_uses_canonical_filters(self) -> None:
        from personal_agent.research_store import add_claim, search_memory, start_research

        payload = start_research("Track claim retrieval")
        add_claim(payload["run"]["id"], "Use canonical filters first", 0.8)

        result = search_memory("Track claim retrieval")

        self.assertTrue(result["runs"])
        claim_result = search_memory("canonical filters")
        self.assertTrue(claim_result["claims"])
        self.assertEqual(claim_result["claims"][0]["run_id"], payload["run"]["id"])

    def test_migration_command_delegates_to_shared_service(self) -> None:
        from personal_agent.migration import migrate_legacy_memory

        payload = migrate_legacy_memory()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(self.fake_operational_memory.migrate_calls, 1)

    def test_shared_memory_status_reports_missing_dependency_clearly(self) -> None:
        from personal_agent import shared_memory

        with patch("personal_agent.shared_memory._memory_service_class", return_value=None):
            status = shared_memory.shared_memory_status()

        self.assertFalse(status["available"])
        self.assertIn("pip install -e ~/agents-database", status["reason"])

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
        self.assertIn(b"201", intake_handler.wfile.getvalue().splitlines()[0])
        self.assertIn(b"200", start_handler.wfile.getvalue().splitlines()[0])
        self.assertIn(b"200", status_handler.wfile.getvalue().splitlines()[0])

    def test_runtime_codex_command_adds_shared_memory_repo_as_writable_dir(self) -> None:
        from personal_agent.runtime import CODEX_ADD_DIRS, PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Probe codex command",
            intent="Need to verify codex add-dir wiring",
            owner_agent=PERSONAL_AGENT_ID,
            origin=PERSONAL_AGENT_ID,
            status="draft",
            metadata={"execution": {"cwd": str(self._fake_repo_dir())}},
        )
        seen: list[list[str]] = []

        class FakePopen:
            def __init__(self, command, stdout, stderr, text):
                del text
                seen.append(command)
                self.pid = 1111
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text("# Summary\n\nOK\n", encoding="utf-8")
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
            runtime.start_task(task["id"], task["metadata"]["execution"]["cwd"])

        self.assertTrue(seen)
        for writable_dir in CODEX_ADD_DIRS:
            self.assertIn(str(writable_dir), seen[0])


if __name__ == "__main__":
    unittest.main()

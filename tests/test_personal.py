from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch


class FakeMemoryService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.store = type("Store", (), {"db_path": db_path})()
        self.records: list[dict] = []

    def _text_embedding(self, text: str) -> list[float]:
        return [float(len(text))]

    def ingest(self, payload: dict) -> dict:
        record = dict(payload)
        self.records.append(record)
        return record

    def search(self, query: str, scopes: list[str] | None = None, limit: int = 10) -> dict:
        scopes = scopes or []
        normalized = query.lower()
        results = []
        for record in self.records:
            if scopes and record.get("scope") not in scopes:
                continue
            haystack = " ".join(str(record.get(field, "")) for field in ["title", "summary", "content"]).lower()
            if normalized in haystack:
                results.append({"memory": record})
        return {"retrieval_id": "fake", "results": results[:limit]}

    def list_memories(
        self,
        *,
        status: str | None = "active",
        scope: str | None = None,
        memory_type: str | None = None,
        project_id: str | None = None,
        repo_id: str | None = None,
        source_ref: str | None = None,
        evidence_ref: str | None = None,
        metadata: dict | None = None,
        limit: int = 50,
    ) -> list[dict]:
        matches = []
        for record in self.records:
            if status is not None and record.get("status", "active") != status:
                continue
            if scope is not None and record.get("scope") != scope:
                continue
            if memory_type is not None and record.get("type") != memory_type:
                continue
            if project_id is not None and record.get("project_id") != project_id:
                continue
            if repo_id is not None and record.get("repo_id") != repo_id:
                continue
            if source_ref is not None and record.get("source_ref") != source_ref:
                continue
            if evidence_ref is not None and record.get("evidence_ref") != evidence_ref:
                continue
            if metadata and any(record.get("metadata", {}).get(key) != value for key, value in metadata.items()):
                continue
            matches.append(record)
        return matches[:limit]


class FakeOperationalMemoryService(FakeMemoryService):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self.projects: dict[str, dict] = {}
        self.repos: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.task_runs: dict[str, dict] = {}
        self.artifacts: dict[str, dict] = {}
        self.handoffs: dict[str, dict] = {}
        self.approvals: dict[str, dict] = {}
        self._counters = {
            "task": 0,
            "run": 0,
            "artifact": 0,
            "handoff": 0,
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

    def list_tasks(self, *, status=None, owner_agent=None, requires_human_input=None, limit=50, **kwargs) -> list[dict]:
        items = list(self.tasks.values())
        if status is not None:
            items = [item for item in items if item["status"] == status]
        if owner_agent is not None:
            items = [item for item in items if item.get("owner_agent") == owner_agent]
        if requires_human_input is not None:
            items = [item for item in items if item.get("requires_human_input") == requires_human_input]
        if "task_id" in kwargs and kwargs["task_id"] is not None:
            items = [item for item in items if item["id"] == kwargs["task_id"]]
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

    def list_artifacts(self, *, task_id=None, limit=50, **kwargs) -> list[dict]:
        items = list(self.artifacts.values())
        if task_id is not None:
            items = [item for item in items if item["task_id"] == task_id]
        return [dict(item) for item in sorted(items, key=lambda item: item["created_at"], reverse=True)[:limit]]

    def get_artifact(self, artifact_id: str) -> dict:
        return dict(self.artifacts[artifact_id])

    def create_handoff(self, task_id: str, from_agent: str, to_agent: str, reason: str, payload: dict, metadata=None) -> dict:
        handoff_id = self._next_id("handoff")
        now = self._now()
        handoff = {
            "id": handoff_id,
            "task_id": task_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "reason": reason,
            "payload": payload,
            "metadata": dict(metadata or {}),
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        self.handoffs[handoff_id] = handoff
        return dict(handoff)

    def list_handoffs(self, *, status=None, limit=50, **kwargs) -> list[dict]:
        items = list(self.handoffs.values())
        if status is not None:
            items = [item for item in items if item["status"] == status]
        return [dict(item) for item in items[:limit]]

    def complete_handoff(self, handoff_id: str, status: str, result_summary: str | None = None) -> dict:
        handoff = self.handoffs[handoff_id]
        handoff["status"] = status
        handoff["result_summary"] = result_summary
        handoff["updated_at"] = self._now()
        return dict(handoff)

    def update_handoff_status(
        self,
        handoff_id: str,
        *,
        status: str,
        result_summary: str | None = None,
        error_message: str | None = None,
    ) -> dict:
        handoff = self.handoffs[handoff_id]
        handoff["status"] = status
        handoff["result_summary"] = result_summary
        handoff["error_message"] = error_message
        handoff["updated_at"] = self._now()
        return dict(handoff)

    def start_task_run(self, task_id: str, agent_id: str, input_payload: dict | None = None) -> dict:
        run_id = self._next_id("run")
        now = self._now()
        run = {
            "id": run_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "running",
            "input_payload": dict(input_payload or {}),
            "result_summary": None,
            "error_message": None,
            "started_at": now,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.task_runs[run_id] = run
        return dict(run)

    def finish_task_run(self, run_id: str, status: str, result_summary: str | None = None, error_message: str | None = None) -> dict:
        run = self.task_runs[run_id]
        run["status"] = status
        run["result_summary"] = result_summary
        run["error_message"] = error_message
        run["completed_at"] = self._now()
        run["updated_at"] = self._now()
        return dict(run)

    def list_task_runs(self, *, task_id=None, limit=50, **kwargs) -> list[dict]:
        items = list(self.task_runs.values())
        if task_id is not None:
            items = [item for item in items if item["task_id"] == task_id]
        if "status" in kwargs and kwargs["status"] is not None:
            items = [item for item in items if item["status"] == kwargs["status"]]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return [dict(item) for item in items[:limit]]

    def create_approval(self, task_id: str, kind: str, risk_level: str, payload: dict) -> dict:
        approval_id = self._next_id("approval")
        now = self._now()
        approval = {
            "id": approval_id,
            "task_id": task_id,
            "kind": kind,
            "risk_level": risk_level,
            "payload": payload,
            "status": "pending",
            "resolution_note": None,
            "created_at": now,
            "updated_at": now,
        }
        self.approvals[approval_id] = approval
        return dict(approval)

    def list_approvals(self, *, status=None, limit=50, **kwargs) -> list[dict]:
        items = list(self.approvals.values())
        if status is not None:
            items = [item for item in items if item["status"] == status]
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return [dict(item) for item in items[:limit]]

    def resolve_approval(self, approval_id: str, status: str, resolution_note: str | None = None) -> dict:
        approval = self.approvals[approval_id]
        approval["status"] = status
        approval["resolution_note"] = resolution_note
        approval["updated_at"] = self._now()
        return dict(approval)

    def dashboard_snapshot(self, owner_agent: str) -> dict:
        tasks = [task for task in self.tasks.values() if task.get("owner_agent") == owner_agent and task.get("parent_task_id") is None]
        active = [dict(task) for task in tasks if task["status"] in {"open", "in_progress"}]
        blocked = [dict(task) for task in tasks if task["status"] == "blocked"]
        return {
            "active_tasks": active,
            "blocked_tasks": blocked,
            "pending_approvals": self.list_approvals(status="pending", limit=100),
            "pending_handoffs": self.list_handoffs(status="pending", limit=100),
            "recent_artifacts": self.list_artifacts(limit=20),
            "recent_runs": self.list_task_runs(limit=20),
        }

    def context_for(self, **kwargs) -> dict:
        return {"active_decisions": [], "recent_episodes": [], "open_questions": []}

    def task_bundle(self, task_id: str) -> dict:
        return {
            "task": self.get_task(task_id),
            "children": [dict(task) for task in self.tasks.values() if task.get("parent_task_id") == task_id],
            "runs": self.list_task_runs(task_id=task_id, limit=100),
            "artifacts": self.list_artifacts(task_id=task_id, limit=100),
            "handoffs": [dict(item) for item in self.handoffs.values() if item["task_id"] == task_id],
            "approvals": [dict(item) for item in self.approvals.values() if item["task_id"] == task_id],
        }


class PersonalAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.agents_db_dir = Path(self.tmp.name) / "agents-database"
        self.agents_db_dir.mkdir()
        self._original_config = {}
        self._original_db = {}
        self._original_shared_memory = {}
        self._original_env = {
            "PERSONAL_AGENT_DATA_DIR": os.environ.get("PERSONAL_AGENT_DATA_DIR"),
            "PERSONAL_AGENT_SHARED_MEMORY_ROOT": os.environ.get("PERSONAL_AGENT_SHARED_MEMORY_ROOT"),
            "PERSONAL_AGENT_SHARED_MEMORY_DB_PATH": os.environ.get("PERSONAL_AGENT_SHARED_MEMORY_DB_PATH"),
        }
        os.environ["PERSONAL_AGENT_DATA_DIR"] = self.tmp.name
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_ROOT"] = str(self.agents_db_dir)
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_DB_PATH"] = str(Path(self.tmp.name) / "shared-agent-memory.sqlite3")

        from personal_agent import config
        from personal_agent import db
        from personal_agent import shared_memory

        self._original_config = {
            "DATA_DIR": config.DATA_DIR,
            "DB_PATH": config.DB_PATH,
            "SHARED_MEMORY_ROOT": config.SHARED_MEMORY_ROOT,
            "SHARED_MEMORY_SRC_DIR": config.SHARED_MEMORY_SRC_DIR,
            "SHARED_MEMORY_DB_PATH": config.SHARED_MEMORY_DB_PATH,
        }
        self._original_db = {
            "DATA_DIR": db.DATA_DIR,
            "DB_PATH": db.DB_PATH,
        }
        self._original_shared_memory = {
            "SHARED_MEMORY_SRC_DIR": shared_memory.SHARED_MEMORY_SRC_DIR,
            "SHARED_MEMORY_DB_PATH": shared_memory.SHARED_MEMORY_DB_PATH,
        }
        config.DATA_DIR = Path(self.tmp.name)
        config.DB_PATH = config.DATA_DIR / "test.sqlite3"
        config.SHARED_MEMORY_ROOT = self.agents_db_dir
        config.SHARED_MEMORY_SRC_DIR = config.SHARED_MEMORY_ROOT / "src"
        config.SHARED_MEMORY_DB_PATH = Path(self.tmp.name) / "shared-agent-memory.sqlite3"
        db.DATA_DIR = config.DATA_DIR
        db.DB_PATH = config.DB_PATH
        shared_memory.SHARED_MEMORY_SRC_DIR = config.SHARED_MEMORY_SRC_DIR
        shared_memory.SHARED_MEMORY_DB_PATH = config.SHARED_MEMORY_DB_PATH

        db.ensure_db()
        self.fake_operational_memory = FakeOperationalMemoryService(str(Path(self.tmp.name) / "shared-agent-memory.sqlite3"))
        self.runtime_memory_patcher = patch("personal_agent.runtime.get_memory_service", return_value=self.fake_operational_memory)
        self.runtime_memory_patcher.start()

    def tearDown(self) -> None:
        from personal_agent import config
        from personal_agent import db
        from personal_agent import shared_memory

        self.runtime_memory_patcher.stop()
        config.DATA_DIR = self._original_config["DATA_DIR"]
        config.DB_PATH = self._original_config["DB_PATH"]
        config.SHARED_MEMORY_ROOT = self._original_config["SHARED_MEMORY_ROOT"]
        config.SHARED_MEMORY_SRC_DIR = self._original_config["SHARED_MEMORY_SRC_DIR"]
        config.SHARED_MEMORY_DB_PATH = self._original_config["SHARED_MEMORY_DB_PATH"]
        db.DATA_DIR = self._original_db["DATA_DIR"]
        db.DB_PATH = self._original_db["DB_PATH"]
        shared_memory.SHARED_MEMORY_SRC_DIR = self._original_shared_memory["SHARED_MEMORY_SRC_DIR"]
        shared_memory.SHARED_MEMORY_DB_PATH = self._original_shared_memory["SHARED_MEMORY_DB_PATH"]
        self.tmp.cleanup()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_research_lifecycle_and_search(self) -> None:
        from personal_agent.research_store import (
            add_claim,
            add_source,
            add_task,
            close_research,
            get_run,
            search_memory,
            start_research,
        )

        run = start_research("Investigate local-first assistants", "recent patterns", "default to v1")
        run_id = run["run"]["id"]

        add_source(run_id, "https://example.com/post", "Example", "reference")
        add_claim(run_id, "Local-first setups dominate early personal assistant projects.", 0.7, "tentative", "https://example.com/post")
        add_task(run_id, "Compare browser automation runtimes")
        close_research(run_id, "Useful baseline with more sources needed.")

        loaded = get_run(run_id)
        self.assertEqual(loaded["run"]["status"], "completed")
        self.assertEqual(len(loaded["sources"]), 1)
        self.assertEqual(len(loaded["claims"]), 1)
        self.assertEqual(len(loaded["tasks"]), 1)

        search = search_memory("browser automation")
        self.assertEqual(len(search["tasks"]), 1)
        self.assertIn("shared_memory", search)

    def test_capture_source_from_local_html_file(self) -> None:
        from personal_agent.research_store import capture_source, get_run, start_research

        html_path = Path(self.tmp.name) / "sample.html"
        html_path.write_text(
            """
            <html>
              <head><title>Sample Capture</title></head>
              <body>
                <h1>Captured heading</h1>
                <p>Important body text for research capture.</p>
              </body>
            </html>
            """,
            encoding="utf-8",
        )

        run = start_research("Capture a local page")
        run_id = run["run"]["id"]
        captured = capture_source(run_id, html_path.as_uri(), notes="local fixture")

        self.assertEqual(captured["title"], "Sample Capture")
        self.assertGreater(captured["captured_chars"], 10)

        loaded = get_run(run_id)
        self.assertEqual(len(loaded["sources"]), 1)
        self.assertEqual(len(loaded["artifacts"]), 1)
        self.assertEqual(loaded["artifacts"][0]["kind"], "source_capture")

    def test_cli_accepts_json_flag_after_subcommand(self) -> None:
        import scripts.personal as personal_cli

        stdout = StringIO()
        with patch("sys.argv", ["personal", "status", "--json"]), patch("sys.stdout", stdout):
            exit_code = personal_cli.main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("summary", payload)

    def test_search_web_result_parsing_and_persistence(self) -> None:
        from personal_agent import research_store
        from personal_agent.research_store import get_run, search_and_store_web_results, start_research

        original_search = research_store.search_web
        research_store.search_web = lambda query, max_results=5: {
            "query": query,
            "engine": "duckduckgo_html",
            "request_url": "https://html.duckduckgo.com/html/?q=test",
            "results": [
                {
                    "title": "First Result",
                    "url": "https://example.com/first",
                    "domain": "example.com",
                },
                {
                    "title": "Second Result",
                    "url": "https://example.com/second",
                    "domain": "example.com",
                },
            ][:max_results],
        }

        try:
            run = start_research("Search the web")
            run_id = run["run"]["id"]
            saved = search_and_store_web_results(run_id, "test query", max_results=1)
        finally:
            research_store.search_web = original_search

        self.assertEqual(len(saved["results"]), 1)

        loaded = get_run(run_id)
        search_artifacts = [artifact for artifact in loaded["artifacts"] if artifact["kind"] == "search_results"]
        self.assertEqual(len(search_artifacts), 1)
        self.assertIn("First Result", search_artifacts[0]["content"])

    def test_approvals_queue(self) -> None:
        from personal_agent.research_store import list_approvals, request_approval

        created = request_approval("email", {"summary": "Draft reply to contact"}, "high")
        pending = list_approvals()

        self.assertEqual(created["status"], "pending")
        self.assertEqual(len(pending), 1)

    def test_task_intake_creates_parent_and_subtasks(self) -> None:
        from personal_agent.research_store import create_task_intake, list_tasks, next_tasks

        created = create_task_intake(
            goal="Evaluate signage suppliers",
            scope="covered padel clubs first",
            assumptions="browser fullscreen preferred",
            clarification_notes=["User clarified: clubs covered first"],
            research_notes=["Mini research: multiple 55-inch Android signage options exist"],
            parent_task="Build initial signage shortlist",
            subtasks=[
                "Collect 5 covered-club candidate displays",
                "Verify browser/fullscreen path",
                "Compare brightness and price bands",
            ],
        )

        all_tasks = list_tasks(run_id=created["run_id"])
        open_tasks = next_tasks()

        self.assertEqual(len(created["subtasks"]), 3)
        self.assertTrue(any(task["kind"] == "clarification" for task in all_tasks))
        self.assertTrue(any(task["kind"] == "research_note" for task in all_tasks))
        self.assertTrue(any(task["kind"] == "subtask" for task in open_tasks))

    def test_legacy_memory_can_be_migrated_to_shared_store(self) -> None:
        from personal_agent.migration import migrate_legacy_memory
        from personal_agent.research_store import add_claim, add_source, add_task, close_research, start_research
        fake_service = FakeMemoryService(str(Path(self.tmp.name) / "shared-agent-memory.sqlite3"))

        run = start_research("Investigate shared memory")
        run_id = run["run"]["id"]
        add_source(run_id, "https://example.com/shared", "Shared", "reference")
        add_claim(run_id, "Shared memory improves cross-agent recall.", 0.9, "verified", "https://example.com/shared")
        add_task(run_id, "Import old research memory")
        close_research(run_id, "Shared memory should become canonical.")

        with patch("personal_agent.shared_memory.get_memory_service", return_value=fake_service), patch(
            "personal_agent.migration.get_memory_service", return_value=fake_service
        ):
            result = migrate_legacy_memory()

        search = fake_service.search("cross-agent recall", scopes=["global"])
        self.assertTrue(search["results"])
        self.assertEqual(result["migrated"]["runs"], 1)

    def test_get_run_falls_back_to_shared_legacy_bridge(self) -> None:
        from personal_agent.research_store import get_run

        fake_service = FakeMemoryService(str(Path(self.tmp.name) / "shared-agent-memory.sqlite3"))
        fake_service.records.extend(
            [
                {
                    "id": "legacy_run_run-123",
                    "type": "episode",
                    "scope": "global",
                    "status": "active",
                    "title": "Research run: Shared-only run",
                    "content": "Goal: Shared-only run\nScope: transition\nAssumptions: mirrored\nSummary: Stored in shared DB only.",
                    "summary": "Stored in shared DB only.",
                    "confidence": 0.8,
                    "freshness": 0.8,
                    "source_ref": "personal-agent:run:run-123",
                    "evidence_ref": "personal-agent:run:run-123",
                    "created_at": "2026-03-14T00:00:00+00:00",
                    "updated_at": "2026-03-14T00:00:00+00:00",
                    "observed_at": "2026-03-14T00:00:00+00:00",
                    "metadata": {"legacy_kind": "research_run", "legacy_run_id": "run-123", "run_status": "completed"},
                },
                {
                    "id": "legacy_claim_run-123",
                    "type": "artifact",
                    "scope": "global",
                    "status": "active",
                    "title": "Research claim: Shared DB keeps the bridge alive",
                    "content": "Shared DB keeps the bridge alive",
                    "summary": "Shared DB keeps the bridge alive",
                    "confidence": 0.9,
                    "freshness": 0.7,
                    "source_ref": "personal-agent:run:run-123",
                    "evidence_ref": "https://example.com/bridge",
                    "created_at": "2026-03-14T00:01:00+00:00",
                    "updated_at": "2026-03-14T00:01:00+00:00",
                    "observed_at": "2026-03-14T00:01:00+00:00",
                    "metadata": {"legacy_kind": "claim", "legacy_run_id": "run-123", "claim_status": "verified", "source_url": "https://example.com/bridge"},
                },
            ]
        )

        with patch("personal_agent.shared_memory.get_memory_service", return_value=fake_service):
            bridged = get_run("run-123")

        self.assertEqual(bridged["run"]["goal"], "Shared-only run")
        self.assertEqual(bridged["run"]["transition_source"], "shared-memory-legacy-bridge")
        self.assertEqual(bridged["claims"][0]["claim"], "Shared DB keeps the bridge alive")

    def test_router_routes_company_and_code_requests(self) -> None:
        from personal_agent.router import route_request

        with patch(
            "personal_agent.router.build_route_payload",
            return_value={
                "primary_agent": "company",
                "secondary_agent": "code",
                "reason": "Ballbox business context with repo work",
                "delegation_target": "ballbox-company-agent",
                "planning_source": "codex",
                "codex_instruction": "",
            },
        ):
            planned = route_request("Necesito avanzar Ballbox con un bug en el repo de pagos")
        self.assertEqual(planned["primary_agent"], "company")
        self.assertEqual(planned["secondary_agent"], "code")

    def test_router_execute_creates_handoff_task(self) -> None:
        from personal_agent.router import route_request
        from personal_agent.research_store import list_tasks

        fake_service = FakeMemoryService(str(Path(self.tmp.name) / "shared-agent-memory.sqlite3"))
        fake_completed = type("CompletedProcess", (), {"stdout": json.dumps({"ok": True, "delegated": "code"})})()
        with patch("personal_agent.router.get_memory_service", return_value=fake_service), patch(
            "personal_agent.router.subprocess.run", return_value=fake_completed
        ):
            executed = route_request("Armar PR para arreglar lint", execute=True)

        self.assertEqual(executed["primary_agent"], "code")
        self.assertEqual(executed["task"]["kind"], "code_handoff")
        self.assertEqual(executed["delegation"]["delegated"], "code")
        self.assertTrue(list_tasks(status="open"))

    def test_router_falls_back_when_codex_plan_is_invalid(self) -> None:
        from personal_agent.router import route_request

        def fake_run(command, capture_output=True, text=True, check=True):
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text("not-json", encoding="utf-8")
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.planner.subprocess.run", side_effect=fake_run):
            planned = route_request("Armar PR para arreglar lint")

        self.assertEqual(planned["primary_agent"], "code")
        self.assertEqual(planned["planning_source"], "fallback")

    def test_leisure_items_can_be_stored_listed_and_searched(self) -> None:
        from personal_agent.research_store import add_leisure_item, list_leisure_items, search_memory

        created = add_leisure_item("Severance", "series", notes="watchlist")
        listed = list_leisure_items(media_type="series")
        search = search_memory("severance")

        self.assertEqual(created["media_type"], "series")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["title"], "Severance")
        self.assertEqual(len(search["leisure_items"]), 1)
        self.assertEqual(search["leisure_items"][0]["title"], "Severance")

    def test_runtime_intake_creates_operational_task_and_handoff(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        plan = {
            "primary_agent": "company",
            "secondary_agent": "code",
            "reason": "company context plus code work",
            "delegation_target": "ballbox-company-agent",
            "planning_source": "fallback",
            "codex_instruction": "",
            "subtasks": [
                {"title": "Confirm business context", "detail": "Clarify Ballbox business need."},
                {"title": "Delegate specialist company work", "detail": "Send company work to ballbox-company-agent."},
                {"title": "Synthesize outcome", "detail": "Collect result and summarize it."},
            ],
        }
        with patch("personal_agent.runtime.build_intake_plan", return_value=plan):
            result = runtime.intake("Ballbox necesita fix en repo de pagos y abrir branch para QR")

        self.assertEqual(result.task["owner_agent"], "personal-agent")
        self.assertEqual(len(result.subtasks), 3)
        self.assertIsNotNone(result.handoff)
        self.assertEqual(result.handoff["to_agent"], "ballbox-company-agent")

    def test_runtime_intake_uses_codex_plan_when_available(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()

        def fake_run(command, capture_output=True, text=True, check=True):
            if "-o" not in command:
                return type(
                    "CompletedProcess",
                    (),
                    {"stdout": json.dumps({"status": "accepted", "summary": "accepted"}), "stderr": ""},
                )()
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "primary_agent": "code",
                        "secondary_agent": None,
                        "reason": "repo implementation work",
                        "delegation_target": None,
                        "codex_instruction": "Let the code agent inspect and execute.",
                        "subtasks": [
                            {"title": "Inspect repo state", "detail": "Read the local repository context first."},
                            {"title": "Run code subagent", "detail": "Execute the coding work inside the codex subagent."},
                            {"title": "Review outcome", "detail": "Summarize results and next steps."},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.planner.subprocess.run", side_effect=fake_run):
            result = runtime.intake("Necesito resolver un refactor chico en un repo local")

        self.assertEqual(result.task["metadata"]["route"]["primary_agent"], "code")
        self.assertEqual(result.task["metadata"]["route"]["planning_source"], "codex")
        self.assertIsNone(result.handoff)
        self.assertEqual(result.subtasks[0]["title"], "Inspect repo state")

    def test_runtime_blocker_response_reopens_task(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Need clarification",
            intent="Need missing context",
            owner_agent=PERSONAL_AGENT_ID,
            status="blocked",
            blocked_reason="Missing detail",
            requires_human_input=True,
        )

        resolved = runtime.respond_to_blocker(task["id"], "Here is the missing detail")

        self.assertEqual(resolved["task"]["status"], "open")
        self.assertFalse(resolved["task"]["requires_human_input"])
        self.assertEqual(resolved["artifact"]["artifact_type"], "blocker_response")

    def test_runtime_process_once_runs_codex_for_personal_tasks(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Summarize next move",
            intent="Need a concise recommendation",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "personal", "reason": "default personal route"}},
        )

        def fake_run(command, capture_output=True, text=True, check=True):
            if "-o" not in command:
                return type(
                    "CompletedProcess",
                    (),
                    {"stdout": json.dumps({"status": "accepted", "summary": "accepted"}), "stderr": ""},
                )()
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "outcome": "complete",
                        "summary": "Generated recommendation",
                        "report_title": "Worker report",
                        "report_markdown": "# Report\n\nAll good.\n",
                        "blocker_reason": "",
                        "approval": {"kind": "", "risk_level": "high", "payload": {}},
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            payload = runtime.process_once()

        self.assertTrue(payload["processed"])
        updated = runtime.service.get_task(task["id"])
        self.assertEqual(updated["status"], "completed")
        artifacts = runtime.service.list_artifacts(task_id=task["id"])
        self.assertTrue(any(artifact["artifact_type"] == "report" for artifact in artifacts))

    def test_runtime_process_once_requests_approval_when_codex_requires_it(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Reach out to supplier",
            intent="Need to contact an external supplier for a quote",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "personal", "reason": "default personal route"}},
        )

        def fake_run(command, capture_output=True, text=True, check=True):
            if "-o" not in command:
                return type(
                    "CompletedProcess",
                    (),
                    {"stdout": json.dumps({"status": "accepted", "summary": "accepted"}), "stderr": ""},
                )()
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "outcome": "needs_approval",
                        "summary": "External outreach required",
                        "report_title": "Approval needed",
                        "report_markdown": "# Approval\n\nNeed approval before contacting the supplier.\n",
                        "blocker_reason": "",
                        "approval": {
                            "kind": "outreach",
                            "risk_level": "high",
                            "payload": {"summary": "Contact supplier for quote", "channel": "email"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            payload = runtime.process_once()

        self.assertTrue(payload["processed"])
        updated = runtime.service.get_task(task["id"])
        self.assertEqual(updated["status"], "blocked")
        self.assertTrue(updated["requires_human_input"])
        self.assertEqual(updated["blocked_reason"], "Awaiting approval")
        approvals = runtime.service.list_approvals(status="pending")
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["kind"], "outreach")

    def test_runtime_resolve_approval_approved_resumes_task(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Reach out to supplier",
            intent="Need to contact an external supplier for a quote",
            owner_agent=PERSONAL_AGENT_ID,
            status="blocked",
            blocked_reason="Awaiting approval",
            requires_human_input=True,
            metadata={"route": {"primary_agent": "personal", "reason": "default personal route"}},
        )
        approval = runtime.service.create_approval(
            task_id=task["id"],
            kind="outreach",
            risk_level="high",
            payload={"summary": "Contact supplier"},
        )

        def fake_run(command, capture_output=True, text=True, check=True):
            if "-o" not in command:
                return type(
                    "CompletedProcess",
                    (),
                    {"stdout": json.dumps({"status": "accepted", "summary": "accepted"}), "stderr": ""},
                )()
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "outcome": "complete",
                        "summary": "Completed after approval",
                        "report_title": "Approved execution",
                        "report_markdown": "# Report\n\nFinished.\n",
                        "blocker_reason": "",
                        "approval": {"kind": "", "risk_level": "high", "payload": {}},
                        "actions": [],
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            payload = runtime.resolve_approval(approval["id"], "approved", "Ship it")

        self.assertEqual(payload["approval"]["status"], "approved")
        self.assertEqual(payload["task"]["status"], "completed")
        self.assertEqual(payload["resume"]["status"], "completed")

    def test_runtime_resolve_approval_rejected_keeps_task_blocked(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Reach out to supplier",
            intent="Need to contact an external supplier for a quote",
            owner_agent=PERSONAL_AGENT_ID,
            status="blocked",
            blocked_reason="Awaiting approval",
            requires_human_input=True,
            metadata={"route": {"primary_agent": "personal", "reason": "default personal route"}},
        )
        approval = runtime.service.create_approval(
            task_id=task["id"],
            kind="outreach",
            risk_level="high",
            payload={"summary": "Contact supplier"},
        )

        payload = runtime.resolve_approval(approval["id"], "rejected", "Do not contact them")

        self.assertEqual(payload["approval"]["status"], "rejected")
        self.assertEqual(payload["task"]["status"], "blocked")
        self.assertEqual(payload["task"]["blocked_reason"], "Do not contact them")
        self.assertIsNone(payload["resume"])

    def test_runtime_process_once_applies_structured_actions(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Prepare implementation split",
            intent="Need durable next steps and specialist handoff",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "personal", "reason": "default personal route"}},
        )

        def fake_run(command, capture_output=True, text=True, check=True):
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "outcome": "complete",
                        "summary": "Prepared follow-up work",
                        "report_title": "Structured actions",
                        "report_markdown": "# Report\n\nPrepared follow-up work.\n",
                        "blocker_reason": "",
                        "approval": {"kind": "", "risk_level": "high", "payload": {}},
                        "actions": [
                            {
                                "type": "create_followup_task",
                                "title": "Implement child step",
                                "intent": "Finish the delegated coding step",
                                "priority": 1,
                            },
                            {
                                "type": "record_artifact",
                                "artifact_type": "implementation_note",
                                "title": "Why split work",
                                "content": "Need a specialist code repo for execution.",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            payload = runtime.process_once()

        updated = runtime.service.get_task(task["id"])
        children = runtime.service.list_tasks(owner_agent=PERSONAL_AGENT_ID, limit=20)
        handoffs = runtime.service.list_handoffs(status="pending", limit=20)
        artifacts = runtime.service.list_artifacts(task_id=task["id"], limit=20)

        self.assertTrue(payload["processed"])
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(len(payload["processed"][0]["actions"]), 2)
        self.assertTrue(any(item["parent_task_id"] == task["id"] and item["status"] == "completed" for item in children))
        self.assertFalse(any(handoff["task_id"] == task["id"] for handoff in handoffs))
        self.assertTrue(any(artifact["artifact_type"] == "execution_state" for artifact in artifacts))
        self.assertTrue(
            any(
                artifact["artifact_type"] == "report" and artifact["metadata"].get("classification") == "deliverable"
                for artifact in artifacts
            )
        )

    def test_runtime_dispatch_legacy_ai_dev_workflow_handoff_blocks_task(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Delegate repo work",
            intent="Need a specialist repo agent",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "code", "delegation_target": "ai-dev-workflow"}},
        )
        handoff = runtime.service.create_handoff(
            task_id=task["id"],
            from_agent=PERSONAL_AGENT_ID,
            to_agent="ai-dev-workflow",
            reason="Need repo execution",
            payload={"task_id": task["id"], "intent": task["intent"]},
        )
        result = runtime.process_once()

        updated_handoffs = runtime.service.list_handoffs(limit=10)
        updated_task = runtime.service.get_task(task["id"])
        artifacts = runtime.service.list_artifacts(task_id=task["id"], limit=10)
        self.assertEqual(result["processed"][0]["kind"], "handoff")
        self.assertEqual(updated_handoffs[0]["status"], "failed")
        self.assertEqual(updated_task["status"], "blocked")
        self.assertIn("Deprecated durable ai-dev-workflow handoff", updated_task["blocked_reason"])
        self.assertTrue(any(item["artifact_type"] == "handoff_result" for item in artifacts))

    def test_runtime_recovers_interrupted_runs_and_reopens_task(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Recover me",
            intent="Was running when daemon stopped",
            owner_agent=PERSONAL_AGENT_ID,
            status="in_progress",
            metadata={"route": {"primary_agent": "personal"}},
        )
        run = runtime.service.start_task_run(task["id"], PERSONAL_AGENT_ID, input_payload={"mode": "codex-agentic"})

        runtime._recover_interrupted_runs()

        updated_task = runtime.service.get_task(task["id"])
        updated_run = runtime.service.list_task_runs(task_id=task["id"], limit=1)[0]
        artifacts = runtime.service.list_artifacts(task_id=task["id"], limit=10)
        self.assertEqual(updated_task["status"], "open")
        self.assertEqual(updated_task["metadata"]["last_interrupted_run_id"], run["id"])
        self.assertEqual(updated_run["status"], "interrupted")
        self.assertTrue(any(item["metadata"].get("outcome") == "interrupted" for item in artifacts))

    def test_runtime_code_route_runs_codex_in_ai_dev_workflow_repo(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Implement repo fix",
            intent="Make a concrete code change",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "code", "delegation_target": None, "reason": "repo work"}},
        )
        calls: list[list[str]] = []

        def fake_run(command, capture_output=True, text=True, check=True):
            calls.append(command)
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "outcome": "complete",
                        "summary": "Implemented the repo fix",
                        "report_title": "Repo fix",
                        "report_markdown": "# Done\n\nImplemented the repo fix.\n",
                        "blocker_reason": "",
                        "approval": {"kind": "", "risk_level": "high", "payload": {}},
                        "actions": [],
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            runtime.process_once()

        self.assertTrue(calls)
        self.assertIn("workspace-write", calls[0])
        self.assertEqual(calls[0][calls[0].index("-C") + 1], str(Path("/Users/sebas/ai-dev-workflow")))

    def test_legacy_code_delegation_target_does_not_show_await_handoff_next_action(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Legacy code route",
            intent="Old metadata should not imply active handoff",
            owner_agent=PERSONAL_AGENT_ID,
            status="open",
            metadata={"route": {"primary_agent": "code", "delegation_target": "ai-dev-workflow"}},
        )

        snapshot = runtime.dashboard_snapshot()
        row = next(item for item in snapshot["active_tasks"] if item["id"] == task["id"])

        self.assertEqual(row["next_action"], "Ready for worker")

    def test_runtime_resolve_preference_blocker_uses_memory_when_available(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        runtime.service.ingest(
            {
                "id": "mem_style_pref",
                "type": "decision",
                "scope": "global",
                "title": "Style preference",
                "content": "Sebas prefers concise, direct updates.",
                "summary": "Concise, direct updates.",
                "source_ref": PERSONAL_AGENT_ID,
                "metadata": {"kind": "preference"},
            }
        )
        task = runtime.service.create_task(
            title="Need style guidance",
            intent="Need communication preference",
            owner_agent=PERSONAL_AGENT_ID,
            status="blocked",
            blocked_reason="Missing preference",
            requires_human_input=True,
        )

        resolved = runtime.resolve_preference_blocker(task["id"], "concise, direct updates.", "Need communication preference")

        artifacts = runtime.service.list_artifacts(task_id=task["id"], limit=10)
        self.assertEqual(resolved["status"], "open")
        self.assertFalse(resolved["requires_human_input"])
        self.assertEqual(resolved["metadata"]["resolved_by_memory_id"], "mem_style_pref")
        self.assertTrue(any(item["artifact_type"] == "memory_resolution" for item in artifacts))

    def test_dashboard_snapshot_exposes_next_actions_and_latest_runs(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        active = runtime.service.create_task(
            title="Inspect runtime state",
            intent="Need current orchestration snapshot",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "personal", "planning_source": "codex"}},
        )
        blocked = runtime.service.create_task(
            title="Waiting approval",
            intent="Need human approval",
            owner_agent=PERSONAL_AGENT_ID,
            status="blocked",
            blocked_reason="Awaiting approval",
            requires_human_input=True,
            metadata={"route": {"primary_agent": "personal", "planning_source": "codex"}},
        )
        queued = runtime.service.create_task(
            title="Queued task",
            intent="Not started yet",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "personal", "planning_source": "codex"}},
        )
        runtime.service.start_task_run(active["id"], PERSONAL_AGENT_ID, input_payload={"mode": "codex-agentic"})
        runtime.service.create_task(
            title="Child item",
            intent="Subtask",
            owner_agent=PERSONAL_AGENT_ID,
            parent_task_id=active["id"],
        )
        runtime.service.create_artifact(
            task_id=active["id"],
            artifact_type="report",
            title="Delivered report",
            content="Done.",
            source_ref=PERSONAL_AGENT_ID,
            metadata={"classification": "deliverable"},
        )
        approval = runtime.service.create_approval(
            task_id=blocked["id"],
            kind="outreach",
            risk_level="high",
            payload={"summary": "Need approval"},
        )

        payload = runtime.dashboard_snapshot()

        active_row = next(item for item in payload["active_tasks"] if item["id"] == active["id"])
        queued_row = next(item for item in payload["active_tasks"] if item["id"] == queued["id"])
        blocked_row = next(item for item in payload["blocked_tasks"] if item["id"] == blocked["id"])
        self.assertEqual(payload["summary"]["pending_approval_count"], 1)
        self.assertEqual(payload["summary"]["running_task_count"], 1)
        self.assertEqual(payload["summary"]["started_task_count"], 1)
        self.assertEqual(payload["summary"]["queued_task_count"], 1)
        self.assertEqual(active_row["next_action"], "Worker running")
        self.assertEqual(active_row["open_subtask_count"], 1)
        self.assertEqual(active_row["execution_state"], "running")
        self.assertTrue(active_row["has_started"])
        self.assertEqual(active_row["latest_run"]["status"], "running")
        self.assertEqual(payload["current_run"]["task_id"], active["id"])
        self.assertEqual(queued_row["execution_state"], "not_started")
        self.assertFalse(queued_row["has_started"])
        self.assertEqual(blocked_row["pending_approval"]["id"], approval["id"])
        self.assertTrue(blocked_row["next_action"].startswith("Resolve approval"))
        self.assertEqual(payload["recent_deliverables"][0]["title"], "Delivered report")
        self.assertEqual(payload["recent_deliverables"][0]["task_title"], active["title"])

    def test_runtime_end_to_end_intake_approval_resume_complete(self) -> None:
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        plan = {
            "primary_agent": "personal",
            "secondary_agent": None,
            "reason": "local orchestration",
            "delegation_target": None,
            "planning_source": "codex",
            "codex_instruction": "Handle locally.",
            "subtasks": [
                {"title": "Clarify scope", "detail": "Understand the task."},
                {"title": "Run worker", "detail": "Let codex decide next move."},
                {"title": "Summarize result", "detail": "Return the final report."},
            ],
        }
        decisions = iter(
            [
                {
                    "outcome": "needs_approval",
                    "summary": "Need outreach approval",
                    "report_title": "Approval required",
                    "report_markdown": "# Approval\n\nNeed approval.\n",
                    "blocker_reason": "",
                    "approval": {"kind": "outreach", "risk_level": "high", "payload": {"summary": "Send outreach"}},
                    "actions": [{"type": "record_artifact", "artifact_type": "decision_note", "title": "Pre-approval", "content": "Need approval first."}],
                },
                {
                    "outcome": "complete",
                    "summary": "Finished after approval",
                    "report_title": "Complete",
                    "report_markdown": "# Done\n\nFinished after approval.\n",
                    "blocker_reason": "",
                    "approval": {"kind": "", "risk_level": "high", "payload": {}},
                    "actions": [{"type": "create_followup_task", "title": "Review aftermath", "intent": "Sanity check the finished work", "priority": 2}],
                },
            ]
        )

        def fake_run(command, capture_output=True, text=True, check=True):
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(json.dumps(next(decisions)), encoding="utf-8")
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.build_intake_plan", return_value=plan):
            intake = runtime.intake("Handle a local task that may need approval")
        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            first = runtime.process_once()
            approval_id = first["processed"][0]["approval_id"]
            resumed = runtime.resolve_approval(approval_id, "approved", "Looks safe")

        approvals = runtime.service.list_approvals(limit=10)
        runs = runtime.service.list_task_runs(task_id=intake.task["id"], limit=10)
        artifacts = runtime.service.list_artifacts(task_id=intake.task["id"], limit=20)
        followups = runtime.service.list_tasks(status="open", owner_agent="personal-agent", limit=20)
        final_task = runtime.service.get_task(intake.task["id"])

        self.assertEqual(final_task["status"], "completed")
        self.assertEqual(approvals[0]["status"], "approved")
        self.assertEqual([run["status"] for run in runs], ["completed", "awaiting_approval"])
        self.assertEqual(resumed["resume"]["status"], "completed")
        self.assertTrue(any(artifact["artifact_type"] == "approval_resolution" for artifact in artifacts))
        self.assertTrue(any(artifact["artifact_type"] == "execution_state" for artifact in artifacts))
        self.assertFalse(any(item["parent_task_id"] == intake.task["id"] for item in followups))
        absorbed = [item for item in runtime.service.list_tasks(owner_agent="personal-agent", limit=20) if item["parent_task_id"] == intake.task["id"]]
        self.assertTrue(any(item["metadata"].get("subtask_disposition") == "absorbed" for item in absorbed))

    def test_daemon_http_api_covers_status_intake_blocker_and_approval(self) -> None:
        from personal_agent.daemon import PersonalAgentHandler
        from personal_agent.runtime import PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        server = type("Server", (), {"runtime": runtime})()

        def invoke(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
            handler = PersonalAgentHandler.__new__(PersonalAgentHandler)
            handler.server = server
            handler.path = path
            body = json.dumps(payload or {}).encode("utf-8")
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = BytesIO(body)
            handler.wfile = BytesIO()
            handler._status = None
            handler._error = None
            handler.send_response = lambda status: setattr(handler, "_status", int(status))
            handler.send_header = lambda *args, **kwargs: None
            handler.end_headers = lambda: None
            handler.send_error = lambda status, *_args: setattr(handler, "_error", int(status))
            getattr(handler, method)()
            if handler._error is not None:
                return handler._error, {}
            return handler._status, json.loads(handler.wfile.getvalue().decode("utf-8"))

        status_code, payload = invoke("do_GET", "/api/status")
        self.assertEqual(status_code, 200)
        self.assertIn("summary", payload)

        intake_plan = {
            "primary_agent": "personal",
            "secondary_agent": None,
            "reason": "local orchestration",
            "delegation_target": None,
            "planning_source": "codex",
            "codex_instruction": "Handle locally.",
            "subtasks": [
                {"title": "Clarify scope", "detail": "Understand the task."},
                {"title": "Run worker", "detail": "Let codex decide next move."},
                {"title": "Summarize result", "detail": "Return the final report."},
            ],
        }
        with patch("personal_agent.runtime.build_intake_plan", return_value=intake_plan):
            status_code, intake_payload = invoke("do_POST", "/api/intake", {"input": "Handle a local task"})
        self.assertEqual(status_code, 201)
        task_id = intake_payload["task"]["id"]
        artifact_id = intake_payload["artifacts"][0]["id"]

        status_code, artifact_payload = invoke("do_GET", f"/api/artifacts/{artifact_id}")
        self.assertEqual(status_code, 200)
        self.assertEqual(artifact_payload["id"], artifact_id)

        status_code, task_payload = invoke("do_GET", f"/api/tasks/{task_id}")
        self.assertEqual(status_code, 200)
        self.assertEqual(task_payload["task"]["id"], task_id)

        runtime.service.update_task(task_id, status="blocked", blocked_reason="Need input", requires_human_input=True)
        status_code, blocker_payload = invoke("do_POST", f"/api/tasks/{task_id}/blocker-response", {"response": "Extra context"})
        self.assertEqual(status_code, 200)
        self.assertEqual(blocker_payload["task"]["status"], "open")

        bad_json_handler = PersonalAgentHandler.__new__(PersonalAgentHandler)
        bad_json_handler.server = server
        bad_json_handler.path = "/api/intake"
        bad_json_handler.headers = {"Content-Length": "1"}
        bad_json_handler.rfile = BytesIO(b"[")
        bad_json_handler.wfile = BytesIO()
        bad_json_handler._error = None
        bad_json_handler.send_response = lambda status: None
        bad_json_handler.send_header = lambda *args, **kwargs: None
        bad_json_handler.end_headers = lambda: None
        bad_json_handler.send_error = lambda status, *_args: setattr(bad_json_handler, "_error", int(status))
        bad_json_handler.do_POST()
        self.assertEqual(bad_json_handler._error, 400)

        status_code, invalid_payload = invoke("do_POST", "/api/intake", {"wrong": "shape"})
        self.assertEqual(status_code, 400)
        self.assertEqual(invalid_payload, {})

        approval = runtime.service.create_approval(
            task_id=task_id,
            kind="outreach",
            risk_level="high",
            payload={"summary": "Need approval"},
        )
        runtime.service.update_task(task_id, status="blocked", blocked_reason="Awaiting approval", requires_human_input=True)

        def fake_run(command, capture_output=True, text=True, check=True):
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "outcome": "complete",
                        "summary": "Done after approval",
                        "report_title": "Done",
                        "report_markdown": "# Done\n\nFinished.\n",
                        "blocker_reason": "",
                        "approval": {"kind": "", "risk_level": "high", "payload": {}},
                        "actions": [],
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            status_code, approval_payload = invoke(
                "do_POST",
                f"/api/approvals/{approval['id']}/resolve",
                {"status": "approved", "note": "safe"},
            )
        self.assertEqual(status_code, 200)
        self.assertEqual(approval_payload["approval"]["status"], "approved")
        self.assertEqual(approval_payload["task"]["status"], "completed")

        status_code, _ = invoke("do_GET", "/missing")
        self.assertEqual(status_code, 404)

    def test_runtime_codex_command_adds_shared_memory_repo_as_writable_dir(self) -> None:
        from personal_agent.runtime import CODEX_ADD_DIRS, PERSONAL_AGENT_ID, PersonalAgentRuntime

        runtime = PersonalAgentRuntime()
        task = runtime.service.create_task(
            title="Probe codex command",
            intent="Need to verify codex add-dir wiring",
            owner_agent=PERSONAL_AGENT_ID,
            metadata={"route": {"primary_agent": "personal", "reason": "default personal route"}},
        )
        seen: list[list[str]] = []

        def fake_run(command, capture_output=True, text=True, check=True):
            seen.append(command)
            if "-o" not in command:
                return type(
                    "CompletedProcess",
                    (),
                    {"stdout": json.dumps({"status": "accepted", "summary": "accepted"}), "stderr": ""},
                )()
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "outcome": "complete",
                        "summary": "Generated recommendation",
                        "report_title": "Worker report",
                        "report_markdown": "# Report\n\nAll good.\n",
                        "blocker_reason": "",
                        "approval": {"kind": "", "risk_level": "high", "payload": {}},
                    }
                ),
                encoding="utf-8",
            )
            return type("CompletedProcess", (), {"stdout": "", "stderr": ""})()

        with patch("personal_agent.runtime.subprocess.run", side_effect=fake_run):
            runtime.process_once()

        codex_commands = [
            command
            for command in seen
            if len(command) >= 2 and Path(command[0]).name == "codex" and command[1] == "exec"
        ]
        self.assertTrue(codex_commands)
        self.assertNotIn("--ask-for-approval", codex_commands[0])
        self.assertNotIn("--search", codex_commands[0])
        self.assertIn("-C", codex_commands[0])
        self.assertIn("--add-dir", codex_commands[0])
        add_dir_value = codex_commands[0][codex_commands[0].index("--add-dir") + 1]
        self.assertEqual(add_dir_value, str(CODEX_ADD_DIRS[0]))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
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


class PersonalAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PERSONAL_AGENT_DATA_DIR"] = self.tmp.name
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_ROOT"] = "/Users/sebas/agents-database"
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_DB_PATH"] = str(Path(self.tmp.name) / "shared-agent-memory.sqlite3")

        from personal_agent import config
        from personal_agent import db

        config.DATA_DIR = Path(self.tmp.name)
        config.DB_PATH = config.DATA_DIR / "test.sqlite3"
        db.DATA_DIR = config.DATA_DIR
        db.DB_PATH = config.DB_PATH

        db.ensure_db()

    def tearDown(self) -> None:
        self.tmp.cleanup()
        os.environ.pop("PERSONAL_AGENT_DATA_DIR", None)
        os.environ.pop("PERSONAL_AGENT_SHARED_MEMORY_ROOT", None)
        os.environ.pop("PERSONAL_AGENT_SHARED_MEMORY_DB_PATH", None)

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

    def test_router_routes_company_and_code_requests(self) -> None:
        from personal_agent.router import route_request

        planned = route_request("Necesito avanzar Ballbox con un bug en el repo de pagos")
        self.assertEqual(planned["primary_agent"], "company")
        self.assertEqual(planned["secondary_agent"], "code")

    def test_router_execute_creates_handoff_task(self) -> None:
        from personal_agent.router import route_request
        from personal_agent.research_store import list_tasks

        fake_service = FakeMemoryService(str(Path(self.tmp.name) / "shared-agent-memory.sqlite3"))
        with patch("personal_agent.router.get_memory_service", return_value=fake_service):
            executed = route_request("Armar PR para arreglar lint", execute=True)

        self.assertEqual(executed["primary_agent"], "code")
        self.assertEqual(executed["task"]["kind"], "code_handoff")
        self.assertTrue(list_tasks(status="open"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class PersonalAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PERSONAL_AGENT_DATA_DIR"] = self.tmp.name

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

    def test_approvals_queue(self) -> None:
        from personal_agent.research_store import list_approvals, request_approval

        created = request_approval("email", {"summary": "Draft reply to contact"}, "high")
        pending = list_approvals()

        self.assertEqual(created["status"], "pending")
        self.assertEqual(len(pending), 1)


if __name__ == "__main__":
    unittest.main()

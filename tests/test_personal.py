from __future__ import annotations

import json
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


class PersonalAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PERSONAL_AGENT_DATA_DIR"] = self.tmp.name
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_ROOT"] = "/Users/sebas/agents-database"
        os.environ["PERSONAL_AGENT_SHARED_MEMORY_DB_PATH"] = str(Path(self.tmp.name) / "shared-agent-memory.sqlite3")

        from personal_agent import config
        from personal_agent import db
        from personal_agent import shared_memory

        config.DATA_DIR = Path(self.tmp.name)
        config.DB_PATH = config.DATA_DIR / "test.sqlite3"
        config.SHARED_MEMORY_ROOT = Path("/Users/sebas/agents-database")
        config.SHARED_MEMORY_SRC_DIR = config.SHARED_MEMORY_ROOT / "src"
        config.SHARED_MEMORY_DB_PATH = Path(self.tmp.name) / "shared-agent-memory.sqlite3"
        db.DATA_DIR = config.DATA_DIR
        db.DB_PATH = config.DB_PATH
        shared_memory.SHARED_MEMORY_SRC_DIR = config.SHARED_MEMORY_SRC_DIR
        shared_memory.SHARED_MEMORY_DB_PATH = config.SHARED_MEMORY_DB_PATH

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
                        "delegation_target": "ai-dev-workflow",
                        "codex_instruction": "Let the code agent inspect and execute.",
                        "subtasks": [
                            {"title": "Inspect repo state", "detail": "Read the local repository context first."},
                            {"title": "Delegate implementation", "detail": "Send the coding work to ai-dev-workflow."},
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
        self.assertEqual(result.handoff["to_agent"], "ai-dev-workflow")
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
                                "type": "create_handoff",
                                "to_agent": "ai-dev-workflow",
                                "reason": "Need repo execution",
                                "payload": {"intent": "Finish the coding step"},
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
        children = runtime.service.list_tasks(status="open", owner_agent=PERSONAL_AGENT_ID, limit=20)
        handoffs = runtime.service.list_handoffs(status="pending", limit=20)
        artifacts = runtime.service.list_artifacts(task_id=task["id"], limit=20)

        self.assertTrue(payload["processed"])
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(len(payload["processed"][0]["actions"]), 3)
        self.assertTrue(any(item["parent_task_id"] == task["id"] for item in children))
        self.assertTrue(any(handoff["task_id"] == task["id"] for handoff in handoffs))
        self.assertTrue(any(artifact["artifact_type"] == "execution_state" for artifact in artifacts))

    def test_runtime_codex_command_adds_shared_memory_repo_as_writable_dir(self) -> None:
        from personal_agent.runtime import PERSONAL_AGENT_ID, PersonalAgentRuntime

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

        codex_commands = [command for command in seen if command[:2] == ["codex", "exec"]]
        self.assertTrue(codex_commands)
        self.assertIn("--add-dir", codex_commands[0])
        add_dir_value = codex_commands[0][codex_commands[0].index("--add-dir") + 1]
        self.assertEqual(add_dir_value, "/Users/sebas/agents-database")


if __name__ == "__main__":
    unittest.main()

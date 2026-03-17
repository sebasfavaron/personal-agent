#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from personal_agent.daemon import run_server
from personal_agent.migration import migrate_legacy_memory
from personal_agent.reporting import build_report
from personal_agent.research_store import (
    add_claim,
    add_leisure_item,
    capture_source,
    add_source,
    add_structured_task,
    add_task,
    close_task,
    close_research,
    create_task_intake,
    get_run,
    list_leisure_items,
    list_approvals,
    list_tasks,
    next_tasks,
    request_approval,
    search_memory,
    search_and_store_web_results,
    start_research,
)
from personal_agent.router import route_request
from personal_agent.runtime import PersonalAgentRuntime


def _print(payload, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if isinstance(payload, str):
        print(payload)
        return
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal")
    parser.add_argument("--json", action="store_true", dest="as_json")

    subparsers = parser.add_subparsers(dest="command", required=True)

    research = subparsers.add_parser("research")
    research_sub = research.add_subparsers(dest="research_command", required=True)

    research_start = research_sub.add_parser("start")
    research_start.add_argument("--goal", required=True)
    research_start.add_argument("--scope", default="")
    research_start.add_argument("--assumptions", default="")

    research_source = research_sub.add_parser("add-source")
    research_source.add_argument("--run-id", required=True)
    research_source.add_argument("--url", required=True)
    research_source.add_argument("--title", default="")
    research_source.add_argument("--notes", default="")

    research_capture = research_sub.add_parser("capture-url")
    research_capture.add_argument("--run-id", required=True)
    research_capture.add_argument("--url", required=True)
    research_capture.add_argument("--title", default="")
    research_capture.add_argument("--notes", default="")

    research_search = research_sub.add_parser("search-web")
    research_search.add_argument("--run-id", required=True)
    research_search.add_argument("--query", required=True)
    research_search.add_argument("--max-results", type=int, default=5)

    research_claim = research_sub.add_parser("add-claim")
    research_claim.add_argument("--run-id", required=True)
    research_claim.add_argument("--claim", required=True)
    research_claim.add_argument("--confidence", type=float, required=True)
    research_claim.add_argument("--status", default="tentative")
    research_claim.add_argument("--source-url", default="")

    research_task = research_sub.add_parser("add-task")
    research_task.add_argument("--run-id", required=True)
    research_task.add_argument("--task", required=True)
    research_task.add_argument("--status", default="draft")
    research_task.add_argument("--due-at", default=None)

    research_status = research_sub.add_parser("status")
    research_status.add_argument("--run-id", required=True)

    research_close = research_sub.add_parser("close")
    research_close.add_argument("--run-id", required=True)
    research_close.add_argument("--summary", required=True)

    report = subparsers.add_parser("report")
    report.add_argument("--run-id", required=True)
    report.add_argument("--format", choices=["md", "json"], default="md")

    memory = subparsers.add_parser("memory-search")
    memory.add_argument("--query", required=True)

    memory_migrate = subparsers.add_parser("memory-migrate")

    daemon = subparsers.add_parser("daemon")
    daemon.add_argument("--host", default="127.0.0.1")
    daemon.add_argument("--port", type=int, default=8082)
    daemon.add_argument("--interval-seconds", type=float, default=5.0)

    intake = subparsers.add_parser("intake")
    intake.add_argument("--input", required=True)
    intake.add_argument("--origin", default="human")

    start = subparsers.add_parser("start")
    start.add_argument("--task-id", required=True)
    start.add_argument("--cwd", required=True)
    start.add_argument("--prompt", default=None)

    pause_running = subparsers.add_parser("pause-running")
    pause_running.add_argument("--reason", default="Daemon restart requested")

    status = subparsers.add_parser("status")

    worker = subparsers.add_parser("worker")
    worker_sub = worker.add_subparsers(dest="worker_command", required=True)
    worker_sub.add_parser("process-once")

    blocker = subparsers.add_parser("blocker")
    blocker_sub = blocker.add_subparsers(dest="blocker_command", required=True)
    blocker_reply = blocker_sub.add_parser("reply")
    blocker_reply.add_argument("--task-id", required=True)
    blocker_reply.add_argument("--response", required=True)

    route = subparsers.add_parser("route")
    route.add_argument("--input", required=True)
    route.add_argument("--execute", action="store_true")

    approvals = subparsers.add_parser("approvals")
    approvals_sub = approvals.add_subparsers(dest="approvals_command", required=True)
    approvals_list = approvals_sub.add_parser("list")
    approvals_list.add_argument("--status", default="pending")

    approvals_request = approvals_sub.add_parser("request")
    approvals_request.add_argument("--kind", required=True)
    approvals_request.add_argument("--risk-level", default="high")
    approvals_request.add_argument("--payload", required=True, help="JSON payload")

    approvals_resolve = approvals_sub.add_parser("resolve")
    approvals_resolve.add_argument("--approval-id", required=True)
    approvals_resolve.add_argument("--status", required=True, choices=["approved", "rejected"])
    approvals_resolve.add_argument("--note", default="")

    tasks = subparsers.add_parser("tasks")
    tasks_sub = tasks.add_subparsers(dest="tasks_command", required=True)

    tasks_add = tasks_sub.add_parser("add")
    tasks_add.add_argument("--task", required=True)
    tasks_add.add_argument("--run-id", default=None)
    tasks_add.add_argument("--kind", default="task")
    tasks_add.add_argument("--status", default="draft")
    tasks_add.add_argument("--parent-task-id", default=None)
    tasks_add.add_argument("--notes", default=None)
    tasks_add.add_argument("--due-at", default=None)

    tasks_list = tasks_sub.add_parser("list")
    tasks_list.add_argument("--status", default=None)
    tasks_list.add_argument("--run-id", default=None)

    tasks_next = tasks_sub.add_parser("next")
    tasks_next.add_argument("--limit", type=int, default=10)

    tasks_close = tasks_sub.add_parser("close")
    tasks_close.add_argument("--task-id", required=True)
    tasks_close.add_argument("--status", default="done")

    tasks_intake = tasks_sub.add_parser("intake")
    tasks_intake.add_argument("--goal", required=True)
    tasks_intake.add_argument("--scope", default="")
    tasks_intake.add_argument("--assumptions", default="")
    tasks_intake.add_argument("--clarifications", required=True, help="JSON array")
    tasks_intake.add_argument("--research-notes", required=True, help="JSON array")
    tasks_intake.add_argument("--parent-task", required=True)
    tasks_intake.add_argument("--subtasks", required=True, help="JSON array")

    leisure = subparsers.add_parser("leisure")
    leisure_sub = leisure.add_subparsers(dest="leisure_command", required=True)

    leisure_add = leisure_sub.add_parser("add")
    leisure_add.add_argument("--title", required=True)
    leisure_add.add_argument("--media-type", required=True)
    leisure_add.add_argument("--status", default="to_consume")
    leisure_add.add_argument("--notes", default=None)

    leisure_list = leisure_sub.add_parser("list")
    leisure_list.add_argument("--media-type", default=None)
    leisure_list.add_argument("--status", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    raw_argv = sys.argv[1:]
    as_json = False
    if "--json" in raw_argv:
        as_json = True
        raw_argv = [arg for arg in raw_argv if arg != "--json"]
    args = parser.parse_args((["--json"] if as_json else []) + raw_argv)
    if args.command == "research":
        if args.research_command == "start":
            _print(start_research(args.goal, args.scope, args.assumptions), args.as_json)
            return 0
        if args.research_command == "add-source":
            _print(add_source(args.run_id, args.url, args.title, args.notes), args.as_json)
            return 0
        if args.research_command == "capture-url":
            _print(capture_source(args.run_id, args.url, args.title, args.notes), args.as_json)
            return 0
        if args.research_command == "search-web":
            _print(search_and_store_web_results(args.run_id, args.query, args.max_results), args.as_json)
            return 0
        if args.research_command == "add-claim":
            _print(
                add_claim(args.run_id, args.claim, args.confidence, args.status, args.source_url),
                args.as_json,
            )
            return 0
        if args.research_command == "add-task":
            _print(add_task(args.run_id, args.task, args.status, args.due_at), args.as_json)
            return 0
        if args.research_command == "status":
            _print(get_run(args.run_id), args.as_json)
            return 0
        if args.research_command == "close":
            _print(close_research(args.run_id, args.summary), args.as_json)
            return 0

    if args.command == "report":
        print(build_report(args.run_id, args.format))
        return 0

    if args.command == "memory-search":
        _print(search_memory(args.query), args.as_json)
        return 0

    if args.command == "memory-migrate":
        _print(migrate_legacy_memory(), args.as_json)
        return 0

    if args.command == "daemon":
        run_server(args.host, args.port, args.interval_seconds)
        return 0

    runtime = None
    if args.command in {"intake", "start", "pause-running", "status"}:
        try:
            runtime = PersonalAgentRuntime()
        except RuntimeError as exc:
            print(f"runtime init failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "intake":
        result = runtime.intake(args.input, origin=args.origin)
        _print(
            {
                "task": result.task,
                "memory_context": result.memory_context,
            },
            args.as_json,
        )
        return 0

    if args.command == "start":
        _print(runtime.start_task(args.task_id, args.cwd, args.prompt), args.as_json)
        return 0

    if args.command == "pause-running":
        _print(runtime.pause_running_tasks(args.reason), args.as_json)
        return 0

    if args.command == "status":
        _print(runtime.dashboard_snapshot(), args.as_json)
        return 0

    if args.command == "worker":
        print("worker flow removed; use intake/start/status", file=sys.stderr)
        return 1

    if args.command == "blocker":
        print("blocker flow removed from direct codex runner", file=sys.stderr)
        return 1

    if args.command == "route":
        _print(route_request(args.input, execute=args.execute), args.as_json)
        return 0

    if args.command == "approvals":
        if args.approvals_command == "list":
            _print(list_approvals(args.status), args.as_json)
            return 0
        if args.approvals_command == "request":
            payload = json.loads(args.payload)
            _print(request_approval(args.kind, payload, args.risk_level), args.as_json)
            return 0
        if args.approvals_command == "resolve":
            print("runtime approval-resume flow removed from direct codex runner", file=sys.stderr)
            return 1

    if args.command == "tasks":
        if args.tasks_command == "add":
            _print(
                add_structured_task(
                    args.run_id,
                    args.task,
                    kind=args.kind,
                    status=args.status,
                    parent_task_id=args.parent_task_id,
                    notes=args.notes,
                    due_at=args.due_at,
                ),
                args.as_json,
            )
            return 0
        if args.tasks_command == "list":
            _print(list_tasks(args.status, args.run_id), args.as_json)
            return 0
        if args.tasks_command == "next":
            _print(next_tasks(args.limit), args.as_json)
            return 0
        if args.tasks_command == "close":
            _print(close_task(args.task_id, args.status), args.as_json)
            return 0
        if args.tasks_command == "intake":
            _print(
                create_task_intake(
                    args.goal,
                    args.scope,
                    args.assumptions,
                    json.loads(args.clarifications),
                    json.loads(args.research_notes),
                    args.parent_task,
                    json.loads(args.subtasks),
                ),
                args.as_json,
            )
            return 0

    if args.command == "leisure":
        if args.leisure_command == "add":
            _print(
                add_leisure_item(
                    args.title,
                    args.media_type,
                    status=args.status,
                    notes=args.notes,
                ),
                args.as_json,
            )
            return 0
        if args.leisure_command == "list":
            _print(list_leisure_items(args.media_type, args.status), args.as_json)
            return 0

    parser.error("Unhandled command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

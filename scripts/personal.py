#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from personal_agent.db import ensure_db
from personal_agent.reporting import build_report
from personal_agent.research_store import (
    add_claim,
    capture_source,
    add_source,
    add_task,
    close_research,
    get_run,
    list_approvals,
    request_approval,
    search_memory,
    search_and_store_web_results,
    start_research,
)


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
    research_task.add_argument("--status", default="open")
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

    approvals = subparsers.add_parser("approvals")
    approvals_sub = approvals.add_subparsers(dest="approvals_command", required=True)
    approvals_list = approvals_sub.add_parser("list")
    approvals_list.add_argument("--status", default="pending")

    approvals_request = approvals_sub.add_parser("request")
    approvals_request.add_argument("--kind", required=True)
    approvals_request.add_argument("--risk-level", default="high")
    approvals_request.add_argument("--payload", required=True, help="JSON payload")

    return parser


def main() -> int:
    ensure_db()
    parser = build_parser()
    args = parser.parse_args()

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

    if args.command == "approvals":
        if args.approvals_command == "list":
            _print(list_approvals(args.status), args.as_json)
            return 0
        if args.approvals_command == "request":
            payload = json.loads(args.payload)
            _print(request_approval(args.kind, payload, args.risk_level), args.as_json)
            return 0

    parser.error("Unhandled command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

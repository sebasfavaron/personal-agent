from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import CODEX_ADD_DIRS, CODEX_BIN
from .repo_targets import infer_target_repo, repo_target_by_id


PERSONAL_ROOT = Path(__file__).resolve().parent.parent

COMPANY_HINTS = {
    "ballbox",
    "volvox",
    "empresa",
    "company",
    "operativo",
    "operativa",
    "ventas",
    "sales",
    "cliente",
    "clientes",
    "padel",
}
CODE_HINTS = {
    "repo",
    "repositorio",
    "bug",
    "fix",
    "feature",
    "pr",
    "pull-request",
    "branch",
    "code",
    "codigo",
    "tests",
    "lint",
    "build",
    "refactor",
    "implement",
}
VALID_AGENTS = {"personal", "company", "code"}
DELEGATION_BY_AGENT = {
    "company": "ballbox-company-agent",
}


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9-]+", text.lower()) if token}


def classify_request(text: str) -> dict[str, Any]:
    tokens = _tokenize(text)
    company_hits = sorted(tokens & COMPANY_HINTS)
    code_hits = sorted(tokens & CODE_HINTS)
    if company_hits and code_hits:
        return {
            "primary_agent": "company",
            "secondary_agent": "code",
            "reason": f"company context ({', '.join(company_hits)}) plus code work ({', '.join(code_hits)})",
        }
    if company_hits:
        return {
            "primary_agent": "company",
            "secondary_agent": None,
            "reason": f"company context ({', '.join(company_hits)})",
        }
    if code_hits:
        return {
            "primary_agent": "code",
            "secondary_agent": None,
            "reason": f"code work ({', '.join(code_hits)})",
        }
    return {
        "primary_agent": "personal",
        "secondary_agent": None,
        "reason": "default personal route",
    }


def fallback_subtasks(text: str, route: dict[str, Any]) -> list[dict[str, str]]:
    if route["primary_agent"] == "company":
        return [
            {"title": "Confirm business context", "detail": f"Clarify commercial or operational context for: {text}"},
            {"title": "Delegate specialist company work", "detail": f"Send company-shaped work to ballbox-company-agent for: {text}"},
            {"title": "Synthesize outcome", "detail": f"Collect result and produce final report for: {text}"},
        ]
    if route["primary_agent"] == "code":
        return [
            {"title": "Inspect technical context", "detail": f"Understand repo or code context for: {text}"},
            {"title": "Run code subagent", "detail": f"Execute code-shaped work inside the codex subagent for: {text}"},
            {"title": "Summarize technical outcome", "detail": f"Collect code result and produce final report for: {text}"},
        ]
    return [
        {"title": "Clarify objective and constraints", "detail": f"Clarify desired outcome, constraints, and assumptions for: {text}"},
        {"title": "Gather context and evidence", "detail": f"Research or inspect relevant context for: {text}"},
        {"title": "Produce final recommendation", "detail": f"Synthesize findings and next actions for: {text}"},
    ]


def build_intake_plan(text: str, memory_context: list[dict[str, Any]]) -> dict[str, Any]:
    fallback_route = classify_request(text)
    fallback_target_repo = infer_target_repo(text, primary_agent=fallback_route["primary_agent"])
    fallback = {
        **fallback_route,
        "delegation_target": DELEGATION_BY_AGENT.get(fallback_route["primary_agent"]),
        "target_repo_id": fallback_target_repo["id"] if fallback_target_repo else None,
        "target_repo_name": fallback_target_repo["name"] if fallback_target_repo else None,
        "target_repo_path": fallback_target_repo["path"] if fallback_target_repo else None,
        "subtasks": fallback_subtasks(text, fallback_route),
        "planning_source": "fallback",
        "codex_instruction": "",
    }
    try:
        planned = _run_codex_plan(text, memory_context)
    except (FileNotFoundError, OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError):
        return fallback
    return _normalize_plan(planned, fallback)


def build_route_payload(text: str, memory_context: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    plan = build_intake_plan(text, memory_context or [])
    return {
        "primary_agent": plan["primary_agent"],
        "secondary_agent": plan["secondary_agent"],
        "reason": plan["reason"],
        "delegation_target": plan["delegation_target"],
        "target_repo_id": plan.get("target_repo_id"),
        "target_repo_name": plan.get("target_repo_name"),
        "target_repo_path": plan.get("target_repo_path"),
        "planning_source": plan["planning_source"],
        "codex_instruction": plan["codex_instruction"],
    }


def _run_codex_plan(text: str, memory_context: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = _planning_prompt(text, memory_context)
    with tempfile.NamedTemporaryFile(prefix="personal-agent-plan-", suffix=".json", delete=False) as handle:
        output_path = Path(handle.name)
    command = [
        CODEX_BIN,
        "exec",
        "--sandbox",
        "read-only",
        "-C",
        str(PERSONAL_ROOT),
        "-o",
        str(output_path),
    ]
    for writable_dir in CODEX_ADD_DIRS:
        command.extend(["--add-dir", str(writable_dir)])
    command.append(prompt)
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        raw = output_path.read_text(encoding="utf-8").strip() or result.stdout.strip()
    finally:
        output_path.unlink(missing_ok=True)
    return _extract_json_object(raw)


def _planning_prompt(text: str, memory_context: list[dict[str, Any]]) -> str:
    memory_lines = []
    for match in memory_context[:5]:
        memory = match.get("memory", {})
        title = memory.get("title", "Untitled memory")
        summary = memory.get("summary") or memory.get("content", "")
        memory_lines.append(f"- {title}: {summary}")
    memory_block = "\n".join(memory_lines) if memory_lines else "- none"
    return "\n".join(
        [
            "You are the planner for personal-agent.",
            "Decide routing and the first execution plan.",
            "Keep Python as the shell for persistence, approvals, auditability, and shared DB state.",
            "Available primary_agent values: personal, company, code.",
            "Available delegation_target values: null, ballbox-company-agent.",
            "Return JSON only with this exact shape:",
            '{',
            '  "primary_agent": "personal|company|code",',
            '  "secondary_agent": "personal|company|code|null",',
            '  "reason": "short reason",',
            '  "delegation_target": "ballbox-company-agent|null",',
            '  "target_repo_id": "repo_personal_agent|repo_ai_dev_workflow|repo_ballbox_company_agent|null",',
            '  "codex_instruction": "short execution note for the shell",',
            '  "subtasks": [',
            '    {"title": "short title", "detail": "one sentence"}',
            "  ]",
            '}',
            "Rules:",
            "- Use company when the request is mainly business, Ballbox, or operational.",
            "- Use code when the request is mainly repo, implementation, bugfix, branch, PR, or tests.",
            "- Use personal for planning, synthesis, research, or local coordination.",
            "- Prefer company as primary and code as secondary for mixed Ballbox plus repo work.",
            "- Set target_repo_id when the request names a repo or clearly implies one; for 'this repo' use repo_personal_agent.",
            "- Always return exactly 3 subtasks.",
            "",
            f"Request: {text}",
            "Relevant memory:",
            memory_block,
        ]
    )


def _extract_json_object(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(1)
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in planner output")
        cleaned = cleaned[start : end + 1]
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Planner output must be a JSON object")
    return payload


def _normalize_plan(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    primary_agent = payload.get("primary_agent")
    if primary_agent not in VALID_AGENTS:
        primary_agent = fallback["primary_agent"]
    secondary_agent = payload.get("secondary_agent")
    if secondary_agent not in VALID_AGENTS:
        secondary_agent = fallback["secondary_agent"]
    reason = str(payload.get("reason") or fallback["reason"]).strip()
    delegation_target = payload.get("delegation_target")
    if delegation_target not in {None, *DELEGATION_BY_AGENT.values()}:
        delegation_target = DELEGATION_BY_AGENT.get(primary_agent)
    target_repo_id = payload.get("target_repo_id")
    if not isinstance(target_repo_id, str) or not target_repo_id.strip():
        target_repo_id = fallback.get("target_repo_id")
    target_repo_name = fallback.get("target_repo_name")
    target_repo_path = fallback.get("target_repo_path")
    if isinstance(target_repo_id, str):
        inferred = repo_target_by_id(target_repo_id)
        if inferred is not None:
            target_repo_name = inferred["name"]
            target_repo_path = inferred["path"]
            target_repo_id = inferred["id"]
        else:
            target_repo_id = fallback.get("target_repo_id")
            target_repo_name = fallback.get("target_repo_name")
            target_repo_path = fallback.get("target_repo_path")
    subtasks = _normalize_subtasks(payload.get("subtasks"), fallback["subtasks"])
    codex_instruction = str(payload.get("codex_instruction") or "").strip()
    return {
        "primary_agent": primary_agent,
        "secondary_agent": secondary_agent,
        "reason": reason,
        "delegation_target": delegation_target,
        "target_repo_id": target_repo_id,
        "target_repo_name": target_repo_name,
        "target_repo_path": target_repo_path,
        "subtasks": subtasks,
        "planning_source": "codex",
        "codex_instruction": codex_instruction,
    }


def _normalize_subtasks(candidate: Any, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(candidate, list):
        return fallback
    normalized: list[dict[str, str]] = []
    for item in candidate:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if title and detail:
            normalized.append({"title": title, "detail": detail})
    return normalized[:3] if len(normalized) >= 3 else fallback

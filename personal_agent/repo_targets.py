from __future__ import annotations

from pathlib import Path


PERSONAL_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PERSONAL_ROOT.parent / "Code" if (PERSONAL_ROOT.parent / "Code").exists() else PERSONAL_ROOT.parent


def repo_catalog() -> dict[str, dict[str, object]]:
    return {
        "repo_personal_agent": {
            "id": "repo_personal_agent",
            "name": "personal-agent",
            "path": str(PERSONAL_ROOT),
            "aliases": (
                "personal-agent",
                "personal agent",
                "this repo",
                "current repo",
            ),
        },
        "repo_ai_dev_workflow": {
            "id": "repo_ai_dev_workflow",
            "name": "ai-dev-workflow",
            "path": str(WORKSPACE_ROOT / "ai-dev-workflow"),
            "aliases": (
                "ai-dev-workflow",
                "ai dev workflow",
                "dev workflow",
            ),
        },
        "repo_ballbox_company_agent": {
            "id": "repo_ballbox_company_agent",
            "name": "ballbox-company-agent",
            "path": str(WORKSPACE_ROOT / "ballbox-company-agent"),
            "aliases": (
                "ballbox-company-agent",
                "ballbox company agent",
            ),
        },
        "repo_calistenia": {
            "id": "repo_calistenia",
            "name": "calistenia",
            "path": str(WORKSPACE_ROOT / "calistenia"),
            "aliases": (
                "calistenia",
                "/users/sebas/code/calistenia",
            ),
        },
    }


def default_code_repo() -> dict[str, object]:
    return repo_catalog()["repo_ai_dev_workflow"]


def repo_target_by_id(repo_id: str | None) -> dict[str, object] | None:
    if not repo_id:
        return None
    return repo_catalog().get(repo_id)


def infer_target_repo(text: str, *, primary_agent: str) -> dict[str, object] | None:
    lowered = text.lower()
    for repo in repo_catalog().values():
        aliases = repo.get("aliases", ())
        if any(alias in lowered for alias in aliases):
            return repo
    if primary_agent == "code":
        return default_code_repo()
    return None

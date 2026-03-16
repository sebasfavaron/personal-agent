import os
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SHARED_MEMORY_ROOTS = [
    BASE_DIR.parent / "agents-database",
    BASE_DIR.parent.parent / "agents-database",
]
SHARED_MEMORY_ROOT = Path(
    os.environ.get(
        "PERSONAL_AGENT_SHARED_MEMORY_ROOT",
        next((str(path) for path in DEFAULT_SHARED_MEMORY_ROOTS if path.exists()), str(DEFAULT_SHARED_MEMORY_ROOTS[0])),
    )
)
SHARED_MEMORY_SRC_DIR = SHARED_MEMORY_ROOT / "src"
SHARED_MEMORY_DATA_DIR = SHARED_MEMORY_ROOT / "data"
SHARED_MEMORY_DB_PATH = Path(
    os.environ.get("PERSONAL_AGENT_SHARED_MEMORY_DB_PATH", SHARED_MEMORY_DATA_DIR / "shared-agent-memory.sqlite3")
)
CODEX_ADD_DIRS = tuple(
    Path(part)
    for part in os.environ.get("PERSONAL_AGENT_CODEX_ADD_DIRS", str(SHARED_MEMORY_ROOT)).split(os.pathsep)
    if part.strip()
)
CODEX_BIN = os.environ.get("PERSONAL_AGENT_CODEX_BIN") or shutil.which("codex") or "codex"

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PERSONAL_AGENT_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "personal-agent.sqlite3"

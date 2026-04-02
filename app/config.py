import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Security boundary — agents can read/write anything inside ROOT but nothing outside.
SANDBOX_ROOT = ROOT

# Agent scratch space and shell working directory.
WORKSPACE = ROOT / "workspace"

DATA_DIR = ROOT / "data"
TOOLS_DYNAMIC = ROOT / "app" / "tools" / "dynamic"
STARTUP_JSON = ROOT / "startup.json"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Oracle — cloud model escalation
ORACLE_API_URL = os.getenv("ORACLE_API_URL", "")
ORACLE_API_KEY = os.getenv("ORACLE_API_KEY", "")
ORACLE_MODEL = os.getenv("ORACLE_MODEL", "")
ORACLE_DAILY_LIMIT = int(os.getenv("ORACLE_DAILY_LIMIT", "20"))

for _d in (WORKSPACE, DATA_DIR, TOOLS_DYNAMIC):
    _d.mkdir(parents=True, exist_ok=True)

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load .env file if present (before reading any env vars)
_env_file = ROOT / ".env"
if _env_file.is_file():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _val = _line.partition("=")
        _key = _key.strip()
        _val = _val.strip().strip('"').strip("'")
        if _key and _key not in os.environ:
            os.environ[_key] = _val

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

# HuggingFace — set HF_TOKEN in .env for gated/private model downloads
HF_TOKEN = os.getenv("HF_TOKEN", "")

# CivitAI — set CIVITAI_API_KEY in .env for gated model downloads
# Get yours at https://civitai.com/user/account (API Keys section)
CIVITAI_API_KEY = os.getenv("CIVITAI_API_KEY", "")

for _d in (WORKSPACE, DATA_DIR, TOOLS_DYNAMIC):
    _d.mkdir(parents=True, exist_ok=True)

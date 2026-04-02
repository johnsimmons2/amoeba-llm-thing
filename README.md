# AI Sandbox

An autonomous AI agent mesh that runs locally on Windows. Agents think, use tools, spawn sub-agents, and self-modify — all observable through a live dashboard.

## Prerequisites

- **Python 3.12+**
- **Node.js 20+**
- **Ollama** running locally (see setup below)

## Quick Start

```powershell
.\start.ps1
```

This installs dependencies, copies the project to an isolated run directory under `runs/`, starts the API server + agent mesh, and launches the dashboard. Agents operate on the copy — the master source is never modified.

To run manually:

```powershell
pip install -r requirements.txt
cd dashboard; npm install; cd ..
python launcher.py --dashboard
```

Or without the launcher (runs directly from master, no self-modification isolation):

```powershell
python -m app.main                      # API + agent mesh on :8000
cd dashboard; npm run dev               # Dashboard on :5173
```

Open **http://localhost:5173** to watch agents work.

---

## Setting Up Model Sources

### Ollama (Recommended — Local GPU)

Ollama runs models locally on your GPU. This is the default and recommended backend.

**1. Install Ollama**

Download from [ollama.com](https://ollama.com/download) and run the installer. After installation, Ollama runs as a background service.

**2. Verify it's running**

```powershell
ollama --version
curl http://localhost:11434/api/tags    # Should return JSON
```

**3. Pull a model**

```powershell
# Small & fast — good starting point (~2GB VRAM)
ollama pull llama3.2

# Larger, more capable (~4-5GB VRAM)
ollama pull llama3.1
ollama pull mistral

# Code-specialized
ollama pull codellama
ollama pull deepseek-coder-v2

# See what's available
ollama list
```

**4. GGUF models from HuggingFace**

Any GGUF-quantized model on HuggingFace can be used through Ollama:

```powershell
# Create a Modelfile pointing to the GGUF
echo 'FROM ./model.gguf' > Modelfile

# Or reference a HuggingFace repo directly
echo 'FROM hf.co/TheBloke/Mistral-7B-v0.1-GGUF:Q4_K_M' > Modelfile
ollama create my-custom-model -f Modelfile
ollama run my-custom-model
```

Browse GGUF models: [huggingface.co/models?sort=trending&search=gguf](https://huggingface.co/models?sort=trending&search=gguf)

**5. Memory guidance**

| Model Size | VRAM Needed | Example |
|-----------|-------------|---------|
| 1-3B params | ~2-3 GB | `llama3.2`, `phi3:mini` |
| 7B params | ~4-5 GB | `mistral`, `llama3.1` |
| 13B params | ~8-10 GB | `codellama:13b` |
| 70B params | ~40 GB | Not feasible on consumer hardware |

Agents have a `check_resources` tool that reports available VRAM before loading models. Set `OLLAMA_URL` if Ollama is on a different machine.

### HuggingFace Transformers (Planned)

A native `transformers` backend is planned for running HuggingFace models directly (without GGUF conversion). The `ModelProvider` interface is already in place — a `HuggingFaceProvider` implementation would plug in alongside the existing `OllamaProvider`. For now, use Ollama + GGUF as described above.

---

## Oracle — Cloud Model Escalation

The Oracle is a safety net: when a local agent gets stuck (repeated errors, circular reasoning), the system automatically escalates to a larger cloud model for guidance.

### How it works

1. **Automatic detection**: After each agent step, the system checks for stuck patterns:
   - Consecutive errors (6+ errors in recent history)
   - Repetitive tool calls (same tool with same args 8+ times)
   - Circular reasoning (repeating the same thoughts)
2. **Escalation**: When stuck, the agent's history + a description of the problem is sent to the configured cloud API.
3. **Guidance injection**: The cloud model's response is injected into the agent's context as guidance, and the agent continues.
4. **Manual use**: Agents can also call `ask_oracle` directly when they choose to.

### Setup

Set these environment variables (or in a `.env` file):

```powershell
# Any OpenAI-compatible API works (OpenAI, Anthropic via proxy, OpenRouter, etc.)
$env:ORACLE_API_URL = "https://api.openai.com/v1"
$env:ORACLE_API_KEY = "sk-..."
$env:ORACLE_MODEL = "gpt-4o"

# Or use OpenRouter for access to Claude, GPT-4, etc.
$env:ORACLE_API_URL = "https://openrouter.ai/api/v1"
$env:ORACLE_API_KEY = "sk-or-..."
$env:ORACLE_MODEL = "anthropic/claude-sonnet-4"

# Daily request limit (default: 20)
$env:ORACLE_DAILY_LIMIT = "20"
```

If no Oracle env vars are set, the feature is simply disabled — no errors, agents just work without it.

### Rate limiting

- Hard daily cap (default 20 requests/day, configurable via `ORACLE_DAILY_LIMIT`)
- State persisted in `data/oracle_state.json` — survives restarts
- Auto-escalation has a cooldown (minimum 6 steps between Oracle calls per agent)
- Dashboard shows Oracle status via `GET /api/oracle/status`

---

## Project Structure

```
launcher.py             ← Copies project to runs/<id>/, starts app, handles restarts
app/
  main.py               ← FastAPI entry point with lifespan boot
  bus.py                ← In-process async pub/sub event bus
  config.py             ← Paths, env vars, security boundary
  agents/
    base_agent.py       ← Agent loop: model → tools → publish → Oracle check
    mesh.py             ← Spawn/kill agents, route messages, heartbeat
  models/
    __init__.py         ← ModelProvider ABC
    ollama.py           ← Ollama REST API provider
    manager.py          ← Singleton provider facade
    oracle.py           ← Cloud model escalation + stuck detection
  tools/
    __init__.py         ← Tool base class (name, params, schema)
    registry.py         ← Loads primitive + dynamic tools
    primitive/          ← Built-in tools:
      files.py          ←   read, write, list, delete (sandboxed)
      shell.py          ←   run_shell
      http.py           ←   http_get, http_post
      agents.py         ←   spawn, kill, list, send, broadcast
      models.py         ←   list, pull, unload, swap models
      resources.py      ←   check RAM/VRAM/disk
      oracle.py         ←   ask_oracle, oracle_status
      lifecycle.py      ←   request_restart, request_shutdown
    dynamic/            ← AI-created tools, loaded via importlib
  memory/
    log_store.py        ← SQLite persistence for all bus messages
    context_store.py    ← SQLite agent history persistence
  api/
    routes.py           ← REST endpoints
    websocket.py        ← WebSocket /ws/logs with replay

dashboard/              ← React + Vite frontend
  src/App.jsx           ← Layout, tabs, WebSocket, chat bar
  src/components/
    AgentList.jsx       ← Sidebar: agent list with model display
    LogStream.jsx       ← Logs with LLM output highlighting
    ModelOutput.jsx     ← Chain-of-thought view (images/audio support)
    FileBrowser.jsx     ← File tree, colored by recency
    DbExplorer.jsx      ← SQLite query explorer
```

## How It Works

1. **`launcher.py`** copies the project to `runs/<timestamp>/` and starts `python -m app.main` from that copy. The master source is untouched.
2. `app/main.py` boots FastAPI, creates an **EventBus**, starts the **AgentMesh** and **LogStore**.
3. The mesh reads `startup.json` and spawns the initial agent(s).
4. Each agent loops: call model → execute tool calls → publish results to the bus → check for stuck patterns.
5. The bus fans out messages to: the dashboard (via WebSocket), SQLite (via LogStore), and other agents (human/message routing).
6. Agents can edit any file in the run copy (including their own source code), then call `request_restart` to reboot with the new code.
7. If an agent gets stuck and the Oracle is configured, the system auto-escalates to a cloud model for guidance.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Status check |
| GET | `/api/agents` | Current agent list |
| GET | `/api/logs` | Query SQLite logs (`?limit=`, `?agent_id=`, `?type=`) |
| POST | `/api/chat` | Send a message to all agents |
| GET | `/api/resources` | System resources (RAM, VRAM, disk) |
| GET | `/api/files` | File tree with modification times |
| GET | `/api/oracle/status` | Oracle config and remaining daily requests |
| GET | `/api/db/tables` | SQLite schema (`?db=logs` or `?db=context`) |
| POST | `/api/db/query` | Execute read-only SQL (`{sql, db}`) |
| WS | `/ws/logs` | Live log stream with replay on connect |

## Security Boundary

- **Launcher isolation**: Agents run from a copy under `runs/`. The master source is never touched.
- **File tools** are sandboxed to the run directory root using `Path.is_relative_to()`.
- **Shell tool** runs with `cwd` set to `workspace/`.
- **DB explorer** only allows `SELECT`/`PRAGMA`/`EXPLAIN`/`WITH` queries — no writes from the dashboard.
- **Oracle rate limits** are enforced by host-side code that agents cannot modify.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `ORACLE_API_URL` | *(empty — disabled)* | Cloud model API base URL |
| `ORACLE_API_KEY` | *(empty)* | Cloud model API key |
| `ORACLE_MODEL` | *(empty)* | Cloud model name (e.g. `gpt-4o`) |
| `ORACLE_DAILY_LIMIT` | `20` | Max Oracle requests per day |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

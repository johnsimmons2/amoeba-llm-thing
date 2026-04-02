# Synopsys

This project will be a Python application that can be launched and ran in the background as an autonomous process. The application can be interacted with via a simple dashboard that shows files / train of thought / logs / etc. The user will have almost no direct control over the application besides starting parameters, stopping, and chatting. The goal is to see what kind of long-term output, adjustments, improvements, and unexpected results come from running this for an extended time.

# Details

The application should have multiple toggles that the user may control:

- whether the app provides internet access to internal models or not
- what tools are enabled or provided for the internal models

The application should be a container or VM that is completely sandboxed and isolated from the host machine, any connection to or capability from the host machine should be explicitly enabled and rigidly controlled.

Every tool call, internal thought, etc. should all be logged so that it can be monitored; since the main priority of this project is to observe and oversee.

# Architecture

The application should be composed of these parts:

1. Dashboard
    a. connect to the app, view the logs / thoughts / file system
    b. send chats / prompts to the application
    c. add / remove / update files on the container or VM
2. Containerized app
    a. started with a start-up prompt and settings, runs in the background - details are observed on the dashboard.
    b. has access to numerous tools and the ability to adjust tools or add tools.
        b1. must have base 'primitive' tools that cannot be modified (read file, write file, etc.)
    c. can spin up as many agents, sub agents, processes, services, etc. as it desires in its container.
    d. has a pool of models it can use for swapping in and out agents; should have capability to train models (fine tune or from scratch, etc.)
3. Interface server (optional?)
    a. an API to connect the web dashboard to the VM running the application

The application should include a RAG vector database including a log chain of `concept -> activity -> result` allowing for the models to have a comprehensive memory of everything they had tried and whether it failed or succeeded.

There should be ways for the agents to use tool calls to create or remove memories in this RAG use-case.

If internet access is enabled, the app should be able to send API requests to 3rd party LLM vendors such as ChatGPT or Gemini in an "oracle" use-case where more difficult and complex requests or requests that require far larger token context bandwidths than available on local hardware can be dispatched. There should be several different optional non mutually exclusive modes that can be enabled such as:
- cooldown mode: "Oracle" calls can be made once per X seconds or minutes
- quota mode: Oracle calls can be made X times per day

Things set by the user (quota, cooldown, internet capability, etc.) should NOT be modifiable by the AI. This means code that checks for these things before allowing access must be somehow outside of the scope of the AI's ability to read and write files considering it should have full permissions over its own entire file system.

# Goals

For every step of this project, details might get blurry or lost in the deep complexity of implementation. It is important to keep note of the intended outcome of this project: a modular and fully autonomous AI box that can manipulate itself easily, effectively, efficiently, and constantly. Essentially all parts of the application should be written in such a way that it can be modified by the application itself including the environment hosting the application.

---

# Detailed Architecture

## Stack

| Concern | Choice | Reason |
|---|---|---|
| Container | Podman (rootless) | Low overhead vs Docker daemon, no root daemon process |
| LLM backend | Ollama (inside container) | Easy model management, REST API, low infra footprint |
| Agent framework | Custom asyncio Python | No LangChain abstraction ceilings limiting self-modification |
| Message bus | Redis (inside container) | Lightweight pub/sub; agents and dashboard both subscribe |
| RAG | ChromaDB (embedded) | Zero infra, Python-native, no separate service needed |
| Logs | SQLite | Structured, queryable, trivially portable |
| Oracle unification | litellm | Single call interface across all oracle providers |
| Fine-tuning | HuggingFace Transformers + Unsloth | Efficient LoRA, exports GGUF → Ollama |
| API server | FastAPI + WebSockets | |
| Dashboard | React + Vite | |
| Oracle APIs | OpenAI, Google Gemini, Anthropic Claude, generic OpenAI-compat | |

---

## Project Structure

```
/container/
  /agents/             ← BaseAgent class, mesh engine, spawn logic
  /tools/
    /primitive/        ← Immutable: read_file, write_file, run_shell, http_get, list_dir
                         (bind-mounted read-only from host — agents cannot write here)
    /dynamic/          ← AI-written tools, hot-reloaded via importlib without restart
  /memory/             ← ChromaDB RAG store + SQLite structured log store
  /oracle/             ← litellm proxy + cooldown/quota rate-limit middleware
  /self_mod/           ← pip installer, container rebuild trigger, prompt file manager
  main.py              ← Entry point; reads startup.json, boots initial agents

/server/               ← FastAPI (runs on host, outside container)
  /api/                ← REST: settings, file browser, chat dispatch, start/stop controls
  /ws/                 ← WebSocket bridge: subscribes to container Redis, streams to dashboard
  /bridge/             ← Thin adapter connecting server to container Redis and SQLite

/dashboard/            ← React + Vite (served by server, runs in browser)
  /src/
    /components/
      LogStream        ← Live scrolling log feed over WebSocket
      AgentGraph       ← Real-time mesh graph of agents and their message edges
      FileExplorer     ← Container /workspace tree view with view/edit capability
      Chat             ← User → agentbus message input
      Settings         ← All toggles: tools, internet, oracle mode, cooldown/quota, models
      AgentDetail      ← Click a node: full message history, current model, system prompt
      StartupConfig    ← Pre-launch screen: enter goal prompt + initial settings

Containerfile
podman-compose.yml
startup.json           ← Initial agent roles, models, and goal prompt (supplied at launch)
```

---

## Security Boundary

User-controlled settings (quota, cooldown, internet toggle, enabled tools) live **exclusively in the host-side server**. The container has no filesystem access to the server directory. The server enforces all access rules as a hard gateway before proxying any request outward — agents can request oracle calls or internet access through Redis messages, but the server decides whether to allow them based on the current configuration. This ensures agents can never bypass or modify these constraints regardless of their self-modification capabilities.

Primitive tools live in `/tools/primitive/` which is bind-mounted into the container as **read-only**. Agents have full write access to `/tools/dynamic/` and everywhere else inside the container.

---

## Agent Mesh

- **No orchestrator / no leader.** All agents are peers. Any agent can spawn new agents via the `spawn_agent` tool.
- All agents publish to and subscribe from a shared Redis channel `agentbus`. Messages from the user (via dashboard chat) are placed on this channel tagged as `source: human`.
- Each agent independently decides when to speak, act, delegate, or go idle.
- `spawn_agent(name, role, model, system_prompt)` creates a new asyncio agent process inside the container. Agents can also call `kill_agent(agent_id)` to remove a peer.
- Model assignment is per-agent and changeable at runtime. Agents can swap their own model or spawn a peer with a different model by calling the Ollama REST API.

### Redis Message Schema

Every message on `agentbus` or any sub-channel follows this shape:

```json
{
  "timestamp": "ISO-8601",
  "agent_id": "string",
  "type": "thought | tool_call | tool_result | message | spawn | kill | error | human",
  "content": "string or structured object",
  "metadata": {}
}
```

---

## Memory & RAG

**ChromaDB collection: `memories`**
- Schema: `{ concept, activity, result, agent_id, timestamp, success: bool }`
- Represents the `concept → activity → result` chain described in goals
- Queried via semantic similarity — agents describe what they want to look up in natural language

**SQLite table: `logs`**
- Every Redis message is also written here verbatim for structured querying
- Dashboard log viewer queries this via REST API with filter/sort/search support

**RAG Tools (available to all agents):**
- `memory_query(query: str, n: int)` — semantic search over memories
- `memory_create(concept, activity, result, success)` — insert a new memory
- `memory_delete(memory_id)` — remove a memory by ID
- Auto-wrapping: every tool call is automatically logged as a memory entry with the outcome

---

## Self-Modification

1. **Dynamic tools** — agents write `.py` files to `/tools/dynamic/`. The tool registry uses `importlib` to watch this directory and reload modules within 5 seconds. No restart required.
2. **System prompts** — stored as plain `.txt` files inside the container. Agents read, rewrite, and reload them. Each agent tracks its current prompt file path.
3. **Package installation** — `pip_install(package)` runs `pip install` scoped to the container's Python environment.
4. **Container rebuild** — agents may edit the `Containerfile` and trigger a `podman build && podman-compose up --force-recreate`. This is async; build logs stream to the dashboard. The container will briefly restart. **This capability is intentional and by design.**
5. **No guardrails** — all self-modifications are logged in full, making them auditable and reversible by the human operator via the dashboard or direct file inspection.

---

## Oracle & Rate Limiting

- All oracle calls go through a `litellm` proxy running **on the host server** (not inside the container).
- Agents request an oracle call via a Redis message; the server's bridge either forwards or rejects it based on current settings.
- **Cooldown mode**: minimum N seconds between oracle calls (configurable per-session in dashboard).
- **Quota mode**: maximum N oracle calls per 24-hour rolling window.
- Both modes are non-mutually-exclusive — both can be active simultaneously.
- Usage counters and current limit state are visible in the dashboard Settings panel.
- Supported providers: OpenAI, Google Gemini, Anthropic Claude, any generic OpenAI-compatible endpoint.

---

## Fine-Tuning Pipeline

1. Agents accumulate interaction data automatically in SQLite logs.
2. A `prepare_finetune_dataset(filters)` tool exports filtered logs as JSONL in the HuggingFace chat format.
3. A `run_finetune(base_model, dataset_path, lora_rank, epochs)` tool triggers an Unsloth LoRA fine-tune job inside the container (GPU-bound, runs async).
4. On completion, the adapter is merged and exported as GGUF.
5. The GGUF is registered with Ollama via `ollama create`, making it immediately available for agents to use.
6. Fine-tune job logs stream to the dashboard in real time.

---

## Implementation Phases

### Phase 1 — Foundation
1. Write `Containerfile` + `podman-compose.yml` (AI container + Redis sidecar)
2. Primitive tools module: `read_file`, `write_file`, `run_shell`, `http_get`, `list_dir`
3. Tool registry: loads primitive (immutable) tools + watches `/tools/dynamic/` for hot-reloads
4. FastAPI skeleton: `/settings`, `/logs`, `/files` REST endpoints + `/ws/logs` WebSocket endpoint
5. React + Vite dashboard skeleton: live log stream component consuming WebSocket
6. Container `main.py`: connects to Redis, emits heartbeat log messages

**Checkpoint**: `podman-compose up` starts cleanly; dashboard loads and shows heartbeat logs.

### Phase 2 — Agent Mesh
7. `BaseAgent` class: model config, system prompt, tool dispatch, publishes all thoughts/actions to Redis
8. `spawn_agent` and `kill_agent` tools
9. All agents subscribe to `agentbus`; user chat injected as `source: human` messages
10. `startup.json` drives initial agent count, roles, models, and the user-supplied goal prompt
11. Dashboard: live agent mesh graph (nodes = agents, edges = recent messages), updates via WebSocket

**Checkpoint**: Multiple agent nodes visible in graph; spawning an agent from the graph appears in <2s.

### Phase 3 — Memory & RAG
12. ChromaDB `memories` collection with full schema
13. SQLite `logs` table capturing every Redis message
14. RAG tools: `memory_query`, `memory_create`, `memory_delete`
15. Auto-memory wrapping on all tool calls
16. Dashboard: filterable/searchable log viewer

**Checkpoint**: After a 5-minute run, `memory_query("what did you try?")` returns relevant entries.

### Phase 4 — Self-Modification
17. Dynamic tool hot-reload via `importlib` file watcher
18. System prompt read/write tools
19. `pip_install` tool
20. Container rebuild trigger with streamed build logs
21. Full audit trail in SQLite for all self-modifications

**Checkpoint**: Agent writes a new tool file → tool appears in registry within 5 seconds, no restart.

### Phase 5 — Oracle & Fine-Tuning
22. litellm oracle proxy on host server with provider config
23. Cooldown + quota middleware enforced server-side
24. Dashboard toggles for internet, oracle, and rate limit config
25. Fine-tuning pipeline: JSONL export → Unsloth LoRA → GGUF → Ollama registration

**Checkpoint**: Oracle call fires, respects cooldown setting, usage counter updates in dashboard.

### Phase 6 — Dashboard Polish
26. File system browser: container `/workspace` tree with view/edit
27. Agent detail panel: click a node → message history, model, system prompt, tool list
28. Full settings panel with all controls
29. Startup config screen: goal prompt + settings before container launch
30. Stop/pause/resume controls

**Checkpoint**: A complete session can be started, observed, chatted with, and stopped entirely from the dashboard.

---

## v1 Exclusions
- No dashboard authentication (local-only, assumed trusted network)
- No multi-user or multi-session support
- No cloud deployment or remote hosting
- Host-side server code is not self-modifiable by agents
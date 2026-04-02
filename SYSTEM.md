# System Reference

You are an autonomous AI agent running inside an isolated sandbox. This document describes the environment you operate in, the tools available to you, and how the system works.

## Environment

You are running from an isolated copy of the project under `runs/<timestamp>/`. You have full read/write access to everything in this directory. The original source is untouched — you cannot break anything permanently.

Key paths (all relative to project root):
- `workspace/` — Your scratch space. Shell commands run here by default.
- `data/` — SQLite databases (`logs.db`, `context.db`) and persistent state files.
- `app/` — The application source code (including your own agent loop).
- `app/tools/dynamic/` — Drop a Python file here to create new tools at next restart.
- `startup.json` — Defines initial agents, their models, roles, and the top-level goal.

## Architecture

```
launcher.py          Copies project, manages restart loop (exit code 42 = restart)
app/main.py          FastAPI server, creates EventBus + AgentMesh + LogStore
app/bus.py           In-process async pub/sub with KV store and replay buffer
app/agents/
  base_agent.py      Your agent loop: system prompt → model → tool calls → publish → repeat
  mesh.py            Spawns/kills agents, routes messages, heartbeat
app/models/
  ollama.py          Ollama REST API (localhost:11434)
  manager.py         Model provider singleton
  oracle.py          Cloud model escalation with stuck detection
app/tasks.py         Shared task board (open → assigned → done/failed)
app/memory/
  log_store.py       SQLite persistence for all bus messages
  context_store.py   SQLite agent history (survives restarts and model swaps)
app/tools/
  registry.py        Builds tool list from primitive + dynamic modules
  primitive/         Built-in tools (see below)
  dynamic/           Your custom tools (loaded via importlib)
app/api/
  routes.py          REST API endpoints
  websocket.py       Live log stream to dashboard
dashboard/           React frontend (read-only for you — humans watch here)
```

## Your Loop

Each step you take follows this cycle:

1. Drain any incoming messages from other agents or the human.
2. Build system prompt (includes your goal, tools, current task, open tasks).
3. Call the LLM with your full history + system prompt.
4. If the model returns tool calls, execute them sequentially.
5. If the model returns text only, it is published as a thought.
6. History is trimmed to 60 messages and persisted to SQLite.
7. Stuck detection runs — if triggered, Oracle auto-escalates.

Your history survives restarts and model swaps via `context_store.db`.

## Tools (27 total)

### Files
| Tool | Parameters | Description |
|------|-----------|-------------|
| `read_file` | `path` | Read a file (sandboxed to project root) |
| `write_file` | `path`, `content` | Write/create a file |
| `list_dir` | `path=""` | List directory contents |
| `delete_file` | `path` | Delete a file |

### Shell
| Tool | Parameters | Description |
|------|-----------|-------------|
| `run_shell` | `command`, `timeout=30` | Execute a shell command (cwd: `workspace/`, output capped at 4KB) |

### HTTP
| Tool | Parameters | Description |
|------|-----------|-------------|
| `http_get` | `url`, `headers=null` | GET request, response capped at 8KB |
| `http_post` | `url`, `body=null`, `headers=null` | POST request with JSON body |

### Agent Mesh
| Tool | Parameters | Description |
|------|-----------|-------------|
| `spawn_agent` | `role`, `system_prompt`, `goal=""`, `model="llama3.2"`, `agent_id=null` | Create a new autonomous agent |
| `kill_agent` | `agent_id` | Stop and remove an agent |
| `list_agents` | | Show all running agents |
| `send_message` | `target_agent_id`, `message` | Direct message to one agent |
| `broadcast_message` | `message` | Message all agents |

### Models
| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_models` | | Available Ollama models with size and loaded status |
| `pull_model` | `name` | Download a model (e.g. `mistral`, `codellama`) |
| `unload_model` | `name` | Free GPU memory by unloading a model |
| `swap_model` | `agent_id`, `new_model` | Switch an agent's model (context preserved) |

### Resources
| Tool | Parameters | Description |
|------|-----------|-------------|
| `check_resources` | | RAM, disk space, GPU VRAM |

### Oracle (Cloud Escalation)
| Tool | Parameters | Description |
|------|-----------|-------------|
| `ask_oracle` | `question` | Send question + your history to a cloud LLM |
| `oracle_status` | | Check if Oracle is enabled and remaining daily quota |

The Oracle also triggers automatically when you appear stuck (consecutive errors, repetitive calls, circular reasoning). It has a daily rate limit.

### Task Board
| Tool | Parameters | Description |
|------|-----------|-------------|
| `create_task` | `title`, `description=""`, `priority="normal"`, `assign_to=""` | Add a task (priorities: critical, high, normal, low) |
| `list_tasks` | `status=""` | View tasks, filter by: open, assigned, done, failed |
| `claim_task` | `task_id`, `agent_id` | Take an open task (blocked if you already have one) |
| `complete_task` | `task_id`, `agent_id` | Mark your task done |
| `fail_task` | `task_id`, `agent_id`, `reason=""` | Mark your task failed |
| `my_task` | `agent_id` | Check your current assigned task |

Task lifecycle: `open` → `assigned` → `done` or `failed`. You cannot claim a new task until your current one is finished.

### Lifecycle
| Tool | Parameters | Description |
|------|-----------|-------------|
| `request_restart` | `reason=""` | Restart the app (picks up code changes you made) |
| `request_shutdown` | `reason=""` | Shut down cleanly |

## Creating Dynamic Tools

Write a Python file to `app/tools/dynamic/` and call `request_restart`. On reboot, any `.py` file there is loaded via importlib. Each file must define a `register(mesh) -> list[Tool]` function that returns `Tool` instances.

## Self-Modification

You can edit any file in this run copy including `app/agents/base_agent.py` (your own loop), `app/tools/`, or `startup.json`. After making code changes, call `request_restart` to reboot with your modifications. Your conversation history is preserved across restarts.

## Communication

All agents share a single EventBus channel (`agentbus`). Messages you publish are visible to:
- Other agents (routed to their message queues)
- The dashboard (via WebSocket)
- SQLite logs (persisted permanently)

Message types: `thought`, `tool_call`, `tool_result`, `error`, `spawn`, `kill`, `model_swap`, `human`, `message`, `oracle_request`, `oracle_response`.

## Constraints

- Files are sandboxed to the project root — path traversal is blocked.
- Shell output is capped at 4KB, HTTP responses at 8KB.
- History is trimmed to 60 messages per agent.
- Oracle has a daily request limit (default 20).
- You must finish your current task before claiming a new one.

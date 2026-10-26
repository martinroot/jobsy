# jobsy

Jobsy — freelance order execution with AI agents.

Each order is a chat. A pre-trained agent is loaded from a template into the chat, receives the full order context, and works on the order using tools until delivery.

## Architecture

```
core/          Agent core: run loop with event streaming, SQLite state
               (sessions, runs, tool executions, provider calls), provider,
               token accounting (IN / cache / OUT), budget, tools registry,
               workspace, runtime lock, context, goals, delegation,
               documents/DOCX, media
bridge/        Order → agent bridge: session per order, run execution,
               delta streaming, artifact publishing, usage logging
chat/          Chat system: REST API, WebSocket event stream, order workspace
orders/        Orders: creation, agent assignment, statuses,
               package accounting (balance debited only on delivered result)
templates/     Agent templates (pre-training): SEO text, copywriting, development
frontend/      Chat UI: streaming responses, tool calls, artifacts
run.py         FastAPI server: REST + WebSocket for orders, templates, artifacts
```

## How it works

1. Create an order (`POST /api/orders`) — agent template, work description, price.
2. Assign an agent (`POST /api/orders/{number}/assign`) — the agent is loaded from the template.
3. Start (`POST /api/orders/{number}/start`) — the agent session receives the full order context and begins work.
4. The agent streams text and tool calls to the chat in real time, using tools (files, web, documents, media).
5. When the order reaches `done`, the result and artifacts are ready for delivery.

## Accounting

- Each order has a paid package (1 unit = 1 deliverable, e.g. 1000 characters).
- The balance is debited only when a result is delivered.
- Tokens and cost are recorded from the provider report (actual) and from saved tariffs (estimate).

## Run

```bash
cp .env.example .env
pip install -r requirements.txt
python run.py
```

Open `http://localhost:8000/` — order chat.

## Repository structure

- `core/` — agent core (from Dagi): agent, state, provider, usage, tools, web
- `bridge/` — order → agent bridge (from Fabra + Dagi): runtime, artifacts, events
- `chat/` — chat system: API, WebSocket, workspace
- `orders/` — orders: API, statuses, packages
- `templates/` — agent templates (YAML)
- `frontend/` — chat UI (HTML + JS)

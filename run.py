"""Jobsy main server.

FastAPI application exposing:
- GET/POST /api/orders — order CRUD
- GET /api/orders/{number} — order state + chat history + artifacts
- POST /api/orders/{number}/message — send message to agent
- GET /api/orders/{number}/events — order events
- WS /api/orders/{number}/stream — real-time event stream
- GET /api/orders/{number}/artifacts/{id} — artifact download
- GET /api/templates — agent templates
- GET / — frontend chat UI
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import DATA_DIR, HOST, PORT, DEBUG
from orders.api import create_order, get_order, list_orders, assign_agent, update_status, record_usage, set_order
from orders.status import NEW, ASSIGNED, RUNNING, DONE, FAILED, NEEDINFO, BLOCKED, can_transition
from templates import list_templates, get_template
from bridge.runtime import run as run_agent
from chat.api import chat_history, send_message, get_artifact
from chat.stream import stream, recent_events

app = FastAPI(title="Jobsy — freelance order execution with agents")

app.mount("/static", StaticFiles(directory=str(ROOT / "frontend")), name="static")


@app.get("/")
def frontend():
    return FileResponse(str(ROOT / "frontend" / "index.html"))


@app.get("/api/templates")
def list_templates_endpoint():
    return {"templates": list_templates()}


@app.post("/api/orders")
def create_order_endpoint(request: Request):
    body = request.json() if hasattr(request, 'json') else {}
    import json as _json
    try:
        body = _json.loads(request.body()) if hasattr(request, 'body') else body
    except Exception:
        pass
    slug = body.get("slug") or "seo-site-text"
    title = body.get("title") or "Заказ"
    description = body.get("description") or ""
    customer_id = body.get("customer_id")
    price_rub = body.get("price_rub")
    order = create_order(slug=slug, title=title, description=description,
                         customer_id=customer_id, price_rub=price_rub)
    return {"ok": True, "order": order}


@app.get("/api/orders")
def list_orders_endpoint(status: str | None = None):
    return {"orders": list_orders(status=status)}


@app.get("/api/orders/{number}")
def order_state(number: str):
    h = chat_history(number)
    if not h.get("ok"):
        raise HTTPException(status_code=404, detail="order not found")
    return h


@app.post("/api/orders/{number}/message")
def order_message(number: str, request: Request):
    import json as _json
    try:
        body = _json.loads(request.body())
    except Exception:
        body = {}
    text = body.get("text", "")
    return send_message(number, text)


@app.post("/api/orders/{number}/assign")
def order_assign(number: str, request: Request):
    import json as _json
    try:
        body = _json.loads(request.body())
    except Exception:
        body = {}
    agent_id = body.get("agent_id") or body.get("slug")
    agent_name = body.get("agent_name")
    o = assign_agent(number, agent_id, agent_name)
    if not o:
        raise HTTPException(status_code=404, detail="order not found")
    return {"ok": True, "order": o}


@app.post("/api/orders/{number}/start")
def order_start(number: str):
    """Start the agent run on an assigned order."""
    o = get_order(number)
    if not o:
        raise HTTPException(status_code=404, detail="order not found")
    if o.get("status") not in (ASSIGNED, NEEDINFO, NEW):
        raise HTTPException(status_code=400, detail="order not in a startable state")
    update_status(number, RUNNING)
    state = run_agent(number, instruction=o.get("description") or "")
    return {"ok": True, "state": state}


@app.get("/api/orders/{number}/events")
def order_events(number: str, after: int = 0, limit: int = 200):
    return recent_events(number, after=after, limit=limit)


@app.websocket("/api/orders/{number}/stream")
async def order_stream(ws: WebSocket, number: str):
    await ws.accept()
    q = await stream.subscribe(number)
    try:
        # send recent events first
        for ev in recent_events(number, limit=50):
            await ws.send_json(ev)
        while True:
            ev = await q.get()
            await ws.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        await stream.unsubscribe(number)


@app.get("/api/orders/{number}/artifacts/{artifact_id}")
def order_artifact(number: str, artifact_id: str):
    from fastapi.responses import FileResponse
    p = get_artifact(number, artifact_id)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path=str(p), filename=p.name)


@app.on_event("startup")
def _startup():
    print(f"Jobsy data dir: {DATA_DIR}")
    print(f"Templates: {len(list_templates())}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, reload=DEBUG)

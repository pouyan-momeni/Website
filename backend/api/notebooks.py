"""Notebook (Marimo) API routes — CRUD for per-user notebooks with Marimo integration."""

import uuid
import os
import httpx
import asyncio
import websockets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.config import settings

router = APIRouter(prefix="/api/notebooks", tags=["notebooks"])

# ─── In-memory notebook store (dev mode) ───
_NOTEBOOKS: dict[str, dict] = {}

# Pre-populate with template notebooks for EACH dev user
if settings.is_develop:
    from backend.config import DEV_USERS
    _template_notebooks = [
        {"name": "Portfolio Analysis", "desc": "Analyze portfolio composition and risk metrics"},
        {"name": "Yield Curve Explorer", "desc": "Interactive yield curve visualization and analysis"},
        {"name": "Stress Test Dashboard", "desc": "Run stress scenarios on current positions"},
        {"name": "Data Quality Monitor", "desc": "Monitor data feeds for quality issues"},
        {"name": "Liquidity Coverage Ratio", "desc": "Calculate and visualize LCR over time"},
    ]
    for username, user_info in DEV_USERS.items():
        for i, nb_data in enumerate(_template_notebooks):
            nb_id = str(uuid.uuid4())
            _NOTEBOOKS[nb_id] = {
                "id": nb_id,
                "name": nb_data["name"],
                "description": nb_data["desc"],
                "owner_id": user_info["id"],
                "owner_username": username,
                "status": "stopped",
                "created_at": datetime(2026, 2, 20 + i, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
                "updated_at": datetime(2026, 2, 22 + min(i, 2), 14, 30, 0, tzinfo=timezone.utc).isoformat(),
                "port": None,
                "url": None,
            }


class NotebookCreate(BaseModel):
    name: str
    description: Optional[str] = None


class NotebookResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    owner_id: str
    owner_username: str
    status: str  # "stopped" | "running" | "paused"
    created_at: str
    updated_at: Optional[str] = None
    port: Optional[int] = None
    url: Optional[str] = None


@router.get("", response_model=list[NotebookResponse])
async def list_notebooks(current_user=Depends(get_current_user)):
    """List notebooks owned by the current user."""
    user_id = str(current_user.id)
    notebooks = [nb for nb in _NOTEBOOKS.values() if nb["owner_id"] == user_id]
    notebooks.sort(key=lambda nb: nb.get("updated_at", nb["created_at"]), reverse=True)
    return notebooks


@router.post("", response_model=NotebookResponse, status_code=status.HTTP_201_CREATED)
async def create_notebook(body: NotebookCreate, current_user=Depends(get_current_user)):
    """Create a new notebook for the current user."""
    nb_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    notebook = {
        "id": nb_id,
        "name": body.name,
        "description": body.description or "",
        "owner_id": str(current_user.id),
        "owner_username": current_user.ldap_username,
        "status": "stopped",
        "created_at": now,
        "updated_at": now,
        "port": None,
        "url": None,
    }
    _NOTEBOOKS[nb_id] = notebook
    return notebook


@router.get("/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(notebook_id: str, current_user=Depends(get_current_user)):
    """Get a single notebook by ID."""
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    return nb


@router.put("/{notebook_id}", response_model=NotebookResponse)
async def update_notebook(notebook_id: str, body: NotebookCreate, current_user=Depends(get_current_user)):
    """Update a notebook's name/description."""
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if nb["owner_id"] != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your notebook")
    nb["name"] = body.name
    if body.description is not None:
        nb["description"] = body.description
    nb["updated_at"] = datetime.now(timezone.utc).isoformat()
    return nb


@router.post("/{notebook_id}/start", response_model=NotebookResponse)
async def start_notebook(notebook_id: str, current_user=Depends(get_current_user)):
    """Start a notebook — launches the Marimo editor."""
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if nb["status"] == "running":
        return nb

    if settings.is_develop:
        try:
            from backend.services.marimo_service import marimo_service
            port = marimo_service.launch_for_user(current_user.ldap_username)
            nb["status"] = "running"
            nb["port"] = port
            # Use a proxy URL that goes through our backend, not directly to the port
            nb["url"] = f"/api/notebooks/{notebook_id}/proxy/"
            nb["updated_at"] = datetime.now(timezone.utc).isoformat()

            from backend.api.audit import log_action
            log_action(
                username=current_user.ldap_username, user_id=str(current_user.id),
                action="start_notebook", resource_type="notebook", resource_id=notebook_id,
                details={"name": nb["name"]},
            )

            return nb
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Failed to start Marimo: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to start Marimo editor: {exc}",
            )

    # Production
    from backend.services.marimo_service import marimo_service
    try:
        port = marimo_service.launch_for_user(current_user.ldap_username)
        nb["status"] = "running"
        nb["port"] = port
        nb["url"] = f"/api/notebooks/{notebook_id}/proxy/"
        nb["updated_at"] = datetime.now(timezone.utc).isoformat()
        return nb
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("/{notebook_id}/stop", response_model=NotebookResponse)
async def stop_notebook(notebook_id: str, current_user=Depends(get_current_user)):
    """Stop a running notebook."""
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if nb["status"] == "stopped":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already stopped")

    nb["status"] = "stopped"
    nb["port"] = None
    nb["url"] = None
    nb["updated_at"] = datetime.now(timezone.utc).isoformat()
    return nb


@router.post("/{notebook_id}/pause", response_model=NotebookResponse)
async def pause_notebook(notebook_id: str, current_user=Depends(get_current_user)):
    """Pause a running notebook."""
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if nb["status"] != "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not running")

    nb["status"] = "paused"
    nb["updated_at"] = datetime.now(timezone.utc).isoformat()
    return nb


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(notebook_id: str, current_user=Depends(get_current_user)):
    """Delete a notebook."""
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if nb["status"] == "running":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stop the notebook before deleting")
    del _NOTEBOOKS[notebook_id]


# ─── Reverse Proxy for Marimo ───────────────────────────────────────────────────

@router.api_route("/{notebook_id}/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_marimo(notebook_id: str, path: str, request: Request):
    """
    Reverse proxy to the Marimo notebook instance.
    This avoids cross-origin issues by routing Marimo traffic through our backend.
    """
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")
    if nb["status"] != "running" or not nb.get("port"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Notebook is not running")

    target_url = f"http://127.0.0.1:{nb['port']}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    body = await request.body()
    headers = dict(request.headers)
    # Remove host header so it doesn't conflict
    headers.pop("host", None)
    headers.pop("Host", None)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                content=body if body else None,
                headers=headers,
                follow_redirects=True,
            )

            # Filter response headers
            excluded = {"transfer-encoding", "content-encoding", "content-length"}
            resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
                media_type=resp.headers.get("content-type"),
            )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot connect to Marimo — it may still be starting up. Wait a moment and try again.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Proxy error: {exc}",
        )


# ─── WebSocket Proxy for Marimo Kernel ──────────────────────────────────────

# Separate router to avoid prefix issues — mounted at app level
ws_notebook_router = APIRouter(tags=["notebooks-ws"])


@router.websocket("/{notebook_id}/proxy/{path:path}")
async def ws_proxy_marimo_api(websocket: WebSocket, notebook_id: str, path: str):
    """WS proxy on the /api/notebooks prefix — same path as HTTP proxy, different protocol."""
    await _ws_proxy(websocket, notebook_id, path)


@ws_notebook_router.websocket("/ws/notebooks/{notebook_id}/proxy/{path:path}")
async def ws_proxy_marimo_ws(websocket: WebSocket, notebook_id: str, path: str):
    """WS proxy on the /ws prefix (fallback)."""
    await _ws_proxy(websocket, notebook_id, path)


async def _ws_proxy(websocket: WebSocket, notebook_id: str, path: str):
    """
    Bidirectional WebSocket relay to Marimo notebook instance.
    Marimo uses WebSockets for kernel communication — without this the editor
    shows 'kernel not found'.
    """
    nb = _NOTEBOOKS.get(notebook_id)
    if not nb or nb["status"] != "running" or not nb.get("port"):
        await websocket.close(code=1008, reason="Notebook not running")
        return

    await websocket.accept()

    target_url = f"ws://127.0.0.1:{nb['port']}/{path}"
    if websocket.scope.get("query_string"):
        qs = websocket.scope["query_string"].decode("utf-8")
        if qs:
            target_url += f"?{qs}"

    try:
        async with websockets.connect(target_url) as marimo_ws:
            async def forward_to_marimo():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await marimo_ws.send(data)
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            async def forward_to_client():
                try:
                    async for message in marimo_ws:
                        if isinstance(message, str):
                            await websocket.send_text(message)
                        else:
                            await websocket.send_bytes(message)
                except Exception:
                    pass

            done, pending = await asyncio.wait(
                [
                    asyncio.ensure_future(forward_to_marimo()),
                    asyncio.ensure_future(forward_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


"""Runs API routes + WebSocket log streaming."""

import asyncio
import csv
import io
import json
import math
import os
import random
import uuid as uuid_mod
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user, require_role, get_redis
from backend.config import settings
from backend.database import get_db
from backend.models.model import Model
from backend.models.run import Run
from backend.models.user import User
from backend.schemas.schemas import RunCreate, RunResponse, RunListResponse


router = APIRouter(prefix="/api/runs", tags=["runs"])

# ─── Dev-mode in-memory run store ───
_DEV_RUNS: dict[str, dict] = {}
_DEV_LOGS: dict[str, list[str]] = {}
_ACTIVE_RUN_IDS: set[str] = set()  # Tracks runs that have simulation threads
MAX_CONCURRENT_RUNS = 2  # Only 2 runs can execute simultaneously; others wait in queue


def _get_model_name(model_id: str) -> str:
    from backend.api.models import _DEV_MODELS
    model = _DEV_MODELS.get(model_id)
    return model["name"] if model else "Unknown Model"


def _get_model_config(model_id: str) -> dict:
    from backend.api.models import _DEV_MODELS
    model = _DEV_MODELS.get(model_id)
    return dict(model.get("default_config", {})) if model else {}


def _generate_sample_outputs(run_id: str, output_path: str, model_name: str):
    """Generate sample CSV and chart data output files for a completed run."""
    os.makedirs(output_path, exist_ok=True)

    # 1. Summary CSV
    with open(os.path.join(output_path, "summary.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value", "status"])
        writer.writerow(["Total PnL", f"${random.randint(10000, 99999):,}", "pass"])
        writer.writerow(["VaR 95%", f"${random.randint(5000, 20000):,}", "pass"])
        writer.writerow(["Expected Shortfall", f"${random.randint(8000, 30000):,}", "warning"])
        writer.writerow(["Max Drawdown", f"{random.uniform(2, 15):.2f}%", "pass"])
        writer.writerow(["Sharpe Ratio", f"{random.uniform(0.5, 3.0):.2f}", "pass"])

    # 2. Time series CSV (for graphing)
    with open(os.path.join(output_path, "timeseries.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "portfolio_value", "benchmark", "spread"])
        base_val = 1000000
        bench_val = 1000000
        for day in range(90):
            base_val *= 1 + random.gauss(0.0003, 0.01)
            bench_val *= 1 + random.gauss(0.0002, 0.008)
            date_str = f"2024-{(day // 30) + 1:02d}-{(day % 30) + 1:02d}"
            writer.writerow([date_str, f"{base_val:.2f}", f"{bench_val:.2f}", f"{base_val - bench_val:.2f}"])

    # 3. Risk breakdown CSV
    with open(os.path.join(output_path, "risk_breakdown.csv"), "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "exposure", "weight_pct"])
        categories = ["Interest Rate", "Credit", "Liquidity", "FX", "Equity", "Commodity"]
        weights = [random.uniform(5, 40) for _ in categories]
        total = sum(weights)
        for cat, w in zip(categories, weights):
            writer.writerow([cat, f"${random.randint(50000, 500000):,}", f"{(w/total)*100:.1f}"])

    # 4. Generate a simple SVG chart (portfolio vs benchmark line chart)
    ts_data = []
    base_val = 1000000
    bench_val = 1000000
    for day in range(90):
        base_val *= 1 + random.gauss(0.0003, 0.01)
        bench_val *= 1 + random.gauss(0.0002, 0.008)
        ts_data.append((base_val, bench_val))

    min_y = min(min(p, b) for p, b in ts_data) * 0.99
    max_y = max(max(p, b) for p, b in ts_data) * 1.01
    y_range = max_y - min_y if max_y > min_y else 1

    def to_svg_y(val):
        return 280 - ((val - min_y) / y_range) * 260

    portfolio_points = " ".join(f"{10 + i * (780/89):.1f},{to_svg_y(p):.1f}" for i, (p, b) in enumerate(ts_data))
    benchmark_points = " ".join(f"{10 + i * (780/89):.1f},{to_svg_y(b):.1f}" for i, (p, b) in enumerate(ts_data))

    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 320" style="background:#0d1117;border-radius:8px">
  <text x="400" y="20" text-anchor="middle" fill="#e6edf3" font-size="14" font-family="sans-serif">Portfolio vs Benchmark Performance</text>
  <line x1="10" y1="280" x2="790" y2="280" stroke="#30363d" stroke-width="1"/>
  <line x1="10" y1="20" x2="10" y2="280" stroke="#30363d" stroke-width="1"/>
  <text x="15" y="35" fill="#8b949e" font-size="10" font-family="sans-serif">${max_y/1000:.0f}K</text>
  <text x="15" y="280" fill="#8b949e" font-size="10" font-family="sans-serif">${min_y/1000:.0f}K</text>
  <polyline points="{portfolio_points}" fill="none" stroke="#58a6ff" stroke-width="2"/>
  <polyline points="{benchmark_points}" fill="none" stroke="#f0883e" stroke-width="2"/>
  <rect x="600" y="290" width="12" height="12" fill="#58a6ff" rx="2"/>
  <text x="616" y="300" fill="#e6edf3" font-size="10" font-family="sans-serif">Portfolio</text>
  <rect x="700" y="290" width="12" height="12" fill="#f0883e" rx="2"/>
  <text x="716" y="300" fill="#e6edf3" font-size="10" font-family="sans-serif">Benchmark</text>
</svg>'''

    with open(os.path.join(output_path, "performance_chart.svg"), "w") as f:
        f.write(svg_content)

    # 5. Risk pie chart SVG
    categories = ["Interest Rate", "Credit", "Liquidity", "FX", "Equity"]
    colors = ["#58a6ff", "#f0883e", "#3fb950", "#d2a8ff", "#f85149"]
    weights = [random.uniform(10, 35) for _ in categories]
    total = sum(weights)
    
    slices_svg = []
    cumulative = 0
    for i, (cat, w, color) in enumerate(zip(categories, weights, colors)):
        pct = w / total
        start_angle = cumulative * 360
        end_angle = (cumulative + pct) * 360
        large = 1 if pct > 0.5 else 0
        
        x1 = 150 + 100 * math.cos(math.radians(start_angle - 90))
        y1 = 150 + 100 * math.sin(math.radians(start_angle - 90))
        x2 = 150 + 100 * math.cos(math.radians(end_angle - 90))
        y2 = 150 + 100 * math.sin(math.radians(end_angle - 90))
        
        slices_svg.append(f'<path d="M150,150 L{x1:.1f},{y1:.1f} A100,100 0 {large},1 {x2:.1f},{y2:.1f} Z" fill="{color}" opacity="0.85"/>')
        slices_svg.append(f'<rect x="320" y="{30 + i * 25}" width="12" height="12" fill="{color}" rx="2"/>')
        slices_svg.append(f'<text x="338" y="{40 + i * 25}" fill="#e6edf3" font-size="11" font-family="sans-serif">{cat} ({pct*100:.1f}%)</text>')
        cumulative += pct

    pie_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 300" style="background:#0d1117;border-radius:8px">
  <text x="150" y="20" text-anchor="middle" fill="#e6edf3" font-size="14" font-family="sans-serif">Risk Allocation</text>
  {"".join(slices_svg)}
</svg>'''

    with open(os.path.join(output_path, "risk_allocation.svg"), "w") as f:
        f.write(pie_svg)

    # 6. JSON results
    with open(os.path.join(output_path, "results.json"), "w") as f:
        json.dump({
            "run_id": run_id,
            "model": model_name,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "metrics": {
                "total_pnl": random.randint(10000, 99999),
                "var_95": random.randint(5000, 20000),
                "sharpe_ratio": round(random.uniform(0.5, 3.0), 2),
                "max_drawdown_pct": round(random.uniform(2, 15), 2),
            }
        }, f, indent=2)


def _simulate_run(run_id: str):
    """Background thread to simulate a model run progressing through steps."""
    run = _DEV_RUNS.get(run_id)
    if not run:
        return

    model_name = _get_model_name(run["model_id"])
    containers = ["data-updater", "analyze", "backtest"]
    logs = _DEV_LOGS.setdefault(run_id, [])

    time.sleep(1)

    if run.get("_cancelled"):
        run["status"] = "cancelled"
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        logs.append("[system] Run cancelled before start")
        _ACTIVE_RUN_IDS.discard(run_id)
        _try_start_next_run()
        return

    run["status"] = "running"
    run["started_at"] = datetime.now(timezone.utc).isoformat()
    run["queue_position"] = None
    logs.append(f"[system] Starting run for {model_name}")

    for idx, container in enumerate(containers):
        if run.get("_cancelled"):
            run["status"] = "cancelled"
            run["completed_at"] = datetime.now(timezone.utc).isoformat()
            logs.append(f"[system] Run cancelled during {container}")
            _ACTIVE_RUN_IDS.discard(run_id)
            _try_start_next_run()
            return

        run["current_container_index"] = idx
        logs.append(f"[{container}] Starting container {idx + 1}/{len(containers)}...")

        steps = 5 if container == "data-updater" else 8 if container == "analyze" else 6
        for step in range(steps):
            if run.get("_cancelled"):
                run["status"] = "cancelled"
                run["completed_at"] = datetime.now(timezone.utc).isoformat()
                logs.append(f"[system] Run cancelled during {container}")
                return
            progress = ((step + 1) / steps) * 100
            logs.append(f"[{container}] Progress: {progress:.0f}%")
            time.sleep(0.5)

        logs.append(f"[{container}] Container completed successfully")

    # Generate output files
    output_path = run.get("output_path", f"/tmp/alm-runs/{run_id}/outputs")
    _generate_sample_outputs(run_id, output_path, model_name)
    logs.append(f"[system] Output files generated at {output_path}")

    run["status"] = "completed"
    run["completed_at"] = datetime.now(timezone.utc).isoformat()
    logs.append(f"[system] Run completed successfully")

    # Free the slot and try to start the next queued run
    _ACTIVE_RUN_IDS.discard(run_id)
    _try_start_next_run()


def _try_start_next_run():
    """Promote the next queued run to running if under the concurrency limit."""
    if len(_ACTIVE_RUN_IDS) >= MAX_CONCURRENT_RUNS:
        return

    # Find the next queued run by queue_position
    queued = [r for r in _DEV_RUNS.values() if r["status"] == "queued" and r["id"] not in _ACTIVE_RUN_IDS]
    if not queued:
        return

    queued.sort(key=lambda r: r.get("queue_position", 999))
    next_run = queued[0]
    run_id = next_run["id"]

    _ACTIVE_RUN_IDS.add(run_id)

    import logging
    logging.getLogger(__name__).info("Promoting queued run %s to running (slot available)", run_id[:8])

    thread = threading.Thread(target=_simulate_run, args=(run_id,), daemon=True)
    thread.start()


# ─── Run Endpoints ───

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_run(
    body: RunCreate,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Create a new run."""
    if db is None and settings.is_develop:
        run_id = str(uuid_mod.uuid4())
        model_id = str(body.model_id)

        default_config = _get_model_config(model_id)
        if body.config_override:
            for key, value in body.config_override.items():
                if key in default_config:
                    if isinstance(default_config[key], dict):
                        default_config[key]["value"] = value
                    else:
                        default_config[key] = value
                else:
                    default_config[key] = value

        queued_runs = [r for r in _DEV_RUNS.values() if r["status"] == "queued"]
        max_pos = max((r.get("queue_position", 0) for r in queued_runs), default=0)

        output_path = f"/tmp/alm-runs/{run_id}/outputs"
        log_path = f"/tmp/alm-runs/{run_id}/logs"
        os.makedirs(output_path, exist_ok=True)
        os.makedirs(log_path, exist_ok=True)

        run = {
            "id": run_id,
            "model_id": model_id,
            "triggered_by": str(current_user.id),
            "status": "queued",
            "inputs": body.inputs,
            "config_snapshot": default_config,
            "celery_task_id": None,
            "current_container_index": 0,
            "queue_position": max_pos + 1,
            "started_at": None,
            "completed_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_archived": False,
            "archived_at": None,
            "archive_path": None,
            "output_path": output_path,
            "log_path": log_path,
        }
        _DEV_RUNS[run_id] = run
        _DEV_LOGS[run_id] = [f"[system] Run {run_id} queued at position {max_pos + 1}"]

        # Only start immediately if under the concurrency limit
        if len(_ACTIVE_RUN_IDS) < MAX_CONCURRENT_RUNS:
            _ACTIVE_RUN_IDS.add(run_id)
            thread = threading.Thread(target=_simulate_run, args=(run_id,), daemon=True)
            thread.start()
        else:
            _DEV_LOGS[run_id].append(f"[system] Waiting in queue — {len(_ACTIVE_RUN_IDS)} runs already executing (max {MAX_CONCURRENT_RUNS})")

        from backend.api.audit import log_action
        log_action(
            username="admin", user_id=str(current_user.id),
            action="create_run", resource_type="run", resource_id=run_id,
            details={"model_id": model_id, "model_name": _get_model_name(model_id)},
        )

        return run

    try:
        from backend.services import run_service
        run = await run_service.create_run(
            db=db,
            model_id=body.model_id,
            user_id=current_user.id,
            inputs=body.inputs,
            config_override=body.config_override,
        )

        # Audit log the run creation
        from backend.api.audit import log_action
        model_result = await db.execute(select(Model).where(Model.id == body.model_id))
        model_obj = model_result.scalar_one_or_none()
        log_action(
            username=current_user.ldap_username,
            user_id=str(current_user.id),
            action="create_run",
            resource_type="run",
            resource_id=str(run.id),
            details={"model_id": str(body.model_id), "model_name": model_obj.name if model_obj else "Unknown"},
        )

        return run
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("")
async def list_runs(
    model_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    triggered_by: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List runs with filtering."""
    if db is None and settings.is_develop:
        runs = list(_DEV_RUNS.values())
        if model_id:
            runs = [r for r in runs if r["model_id"] == str(model_id)]
        if status_filter:
            runs = [r for r in runs if r["status"] == status_filter]
        if triggered_by:
            runs = [r for r in runs if r["triggered_by"] == str(triggered_by)]
        runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        for r in runs:
            r["model_name"] = _get_model_name(r["model_id"])
            r["username"] = "admin"
        return runs[offset:offset + limit]

    query = select(Run).order_by(Run.created_at.desc())
    conditions = []
    if model_id:
        conditions.append(Run.model_id == model_id)
    if status_filter:
        conditions.append(Run.status == status_filter)
    if triggered_by:
        conditions.append(Run.triggered_by == triggered_by)
    if date_from:
        conditions.append(Run.created_at >= date_from)
    if date_to:
        conditions.append(Run.created_at <= date_to)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    runs = result.scalars().all()

    response = []
    for run in runs:
        run_data = RunListResponse.model_validate(run)
        model_result = await db.execute(select(Model.name).where(Model.id == run.model_id))
        run_data.model_name = model_result.scalar_one_or_none()
        user_result = await db.execute(select(User.ldap_username).where(User.id == run.triggered_by))
        run_data.username = user_result.scalar_one_or_none()
        response.append(run_data)
    return response


@router.get("/{run_id}")
async def get_run(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single run."""
    if db is None and settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return run

    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("/{run_id}/logs")
async def get_run_logs(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get logs for a run."""
    if settings.is_develop:
        logs = _DEV_LOGS.get(str(run_id), [])
        return {"logs": logs}
    return {"logs": []}


@router.get("/{run_id}/outputs")
async def list_run_outputs(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List output files for a run."""
    if db is None and settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        output_path = run.get("output_path", "")
        if not os.path.isdir(output_path):
            return {"files": []}
        files = []
        for fname in sorted(os.listdir(output_path)):
            fpath = os.path.join(output_path, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                ext = os.path.splitext(fname)[1].lower()
                files.append({
                    "name": fname,
                    "size": stat.st_size,
                    "type": "chart" if ext in (".svg", ".png", ".jpg", ".jpeg") else
                            "data" if ext in (".csv", ".json", ".xlsx") else "other",
                    "extension": ext,
                })
        return {"files": files}

    # Production: read from filesystem
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    output_path = run.output_path or ""
    if not os.path.isdir(output_path):
        return {"files": []}
    files = []
    for fname in sorted(os.listdir(output_path)):
        fpath = os.path.join(output_path, fname)
        if os.path.isfile(fpath):
            stat = os.stat(fpath)
            ext = os.path.splitext(fname)[1].lower()
            files.append({
                "name": fname,
                "size": stat.st_size,
                "type": "chart" if ext in (".svg", ".png", ".jpg", ".jpeg") else
                        "data" if ext in (".csv", ".json", ".xlsx") else "other",
                "extension": ext,
            })
    return {"files": files}


@router.get("/{run_id}/outputs/{filename}")
async def download_output_file(
    run_id: UUID,
    filename: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a specific output file."""
    if db is None and settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        fpath = os.path.join(run.get("output_path", ""), filename)
    else:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        fpath = os.path.join(run.output_path or "", filename)

    if not os.path.isfile(fpath):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Determine media type
    ext = os.path.splitext(filename)[1].lower()
    media_types = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(fpath, media_type=media_type, filename=filename)


@router.delete("/{run_id}")
async def cancel_run(
    run_id: UUID,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a run."""
    if db is None and settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        if run["status"] in ("completed", "failed", "cancelled"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run already finished")
        run["_cancelled"] = True
        if run["status"] == "queued":
            run["status"] = "cancelled"
            run["completed_at"] = datetime.now(timezone.utc).isoformat()
            _DEV_LOGS.setdefault(str(run_id), []).append("[system] Run cancelled while queued")
        return {"detail": f"Cancel signal set for run {run_id}"}

    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        
    if run.status in ["completed", "failed", "cancelled"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run already finished")
        
    if run.status == "queued":
        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()

    redis_client = await get_redis()
    cancel_key = f"run:{run_id}:cancel"
    await redis_client.set(cancel_key, "1", ex=86400)
    return {"detail": f"Cancel signal set for run {run_id}"}


@router.post("/{run_id}/archive")
async def archive_run(
    run_id: UUID,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Archive a completed run."""
    if db is None and settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        if run["is_archived"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already archived")
        if run["status"] not in ("completed", "failed", "cancelled"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run must be completed/failed/cancelled")

        archive_path = f"/tmp/alm-archives/{current_user.ldap_username}/{str(run_id)}"
        os.makedirs(archive_path, exist_ok=True)

        run["is_archived"] = True
        run["archived_at"] = datetime.now(timezone.utc).isoformat()
        run["archive_path"] = archive_path
        return run

    try:
        from backend.services import archive_service
        run = await archive_service.archive_run(db, run_id, current_user.id)
        return run
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{run_id}/unarchive")
async def unarchive_run(
    run_id: UUID,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Unarchive a run."""
    if db is None and settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        if not run["is_archived"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not archived")

        run["is_archived"] = False
        run["archived_at"] = None
        run["archive_path"] = None
        return run

    # Production: update DB
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if not run.is_archived:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not archived")
    run.is_archived = False
    run.archived_at = None
    run.archive_path = None
    await db.flush()
    return run


@router.delete("/{run_id}/delete")
async def delete_run(
    run_id: UUID,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Delete a run permanently."""
    if db is None and settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        del _DEV_RUNS[str(run_id)]
        _DEV_LOGS.pop(str(run_id), None)
        return {"detail": f"Run {run_id} deleted"}

    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    await db.delete(run)
    await db.flush()
    return {"detail": f"Run {run_id} deleted"}


# ─── WebSocket for real-time logs ─────────────────────────────────────────────

ws_router = APIRouter(tags=["websocket"])


@ws_router.websocket("/ws/runs/{run_id}/logs")
async def run_logs_ws(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for streaming run logs."""
    await websocket.accept()

    if settings.is_develop:
        last_idx = 0
        try:
            while True:
                logs = _DEV_LOGS.get(run_id, [])
                if len(logs) > last_idx:
                    for line in logs[last_idx:]:
                        await websocket.send_text(line)
                    last_idx = len(logs)
                run = _DEV_RUNS.get(run_id)
                if run and run["status"] in ("completed", "failed", "cancelled"):
                    logs = _DEV_LOGS.get(run_id, [])
                    if len(logs) > last_idx:
                        for line in logs[last_idx:]:
                            await websocket.send_text(line)
                    break
                await asyncio.sleep(0.3)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        return

    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = f"run:{run_id}:logs"
    try:
        await pubsub.subscribe(channel)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])
            else:
                await asyncio.sleep(0.1)
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                except asyncio.TimeoutError:
                    pass
                except WebSocketDisconnect:
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis_client.close()

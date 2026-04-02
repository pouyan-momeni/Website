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

import logging as _logging
_run_logger = _logging.getLogger(__name__)


def _save_run_metadata(run: dict):
    """Persist run metadata to disk so it survives restarts."""
    try:
        run_dir = os.path.dirname(run.get("output_path", ""))
        if not run_dir:
            run_dir = os.path.join(settings.RUNS_BASE_PATH, run["id"])
        os.makedirs(run_dir, exist_ok=True)
        meta_path = os.path.join(run_dir, "run_metadata.json")
        # Write a serializable copy
        serializable = {k: v for k, v in run.items() if not k.startswith("_")}
        with open(meta_path, "w") as f:
            json.dump(serializable, f, indent=2, default=str)
    except Exception as exc:
        _run_logger.warning("Failed to save run metadata for %s: %s", run.get("id"), exc)


def _load_logs_from_disk(run_id: str, log_path: str) -> list[str]:
    """Load log lines from disk log files."""
    lines = []
    if not log_path or not os.path.isdir(log_path):
        return lines
    try:
        for fname in sorted(os.listdir(log_path)):
            if fname.endswith(".log"):
                fpath = os.path.join(log_path, fname)
                container_name = fname.replace(".log", "")
                with open(fpath, "r") as f:
                    for line in f:
                        line = line.rstrip("\n")
                        if line:
                            lines.append(f"[{container_name}] {line}")
    except Exception:
        pass
    return lines


def _load_runs_from_disk():
    """Scan RUNS_BASE_PATH and ARCHIVE_BASE_PATH for run_metadata.json and load into _DEV_RUNS."""
    loaded = 0
    for base_path in [settings.RUNS_BASE_PATH, settings.ARCHIVE_BASE_PATH]:
        if not os.path.isdir(base_path):
            continue
        # Walk the directory tree looking for run_metadata.json
        for root, dirs, files in os.walk(base_path):
            if "run_metadata.json" in files:
                meta_path = os.path.join(root, "run_metadata.json")
                try:
                    with open(meta_path, "r") as f:
                        run_data = json.load(f)
                    run_id = run_data.get("id")
                    if run_id and run_id not in _DEV_RUNS:
                        _DEV_RUNS[run_id] = run_data
                        loaded += 1
                except Exception as exc:
                    _run_logger.warning("Failed to load run metadata from %s: %s", meta_path, exc)
    if loaded > 0:
        _run_logger.info("Loaded %d run(s) from disk", loaded)


# Load persisted runs on module import (dev mode)
if settings.is_develop:
    _load_runs_from_disk()


def _get_model_name(model_id: str, db_session=None) -> str:
    """Get model name from memory or DB."""
    from backend.api.models import _DEV_MODELS
    model = _DEV_MODELS.get(model_id)
    if model:
        return model["name"]
    # Check DB synchronously using a sync engine
    try:
        from backend.config import settings
        from sqlalchemy import create_engine, text
        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        with sync_engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM models WHERE id = :id"), {"id": model_id})
            row = result.fetchone()
            if row:
                return row[0]
        sync_engine.dispose()
    except Exception:
        pass
    return "Unknown Model"


def _get_model_config(model_id: str) -> dict:
    from backend.api.models import _DEV_MODELS
    model = _DEV_MODELS.get(model_id)
    if model:
        return dict(model.get("default_config", {}))
    # Check DB
    try:
        from backend.config import settings
        from sqlalchemy import create_engine, text
        import json
        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        with sync_engine.connect() as conn:
            result = conn.execute(text("SELECT default_config FROM models WHERE id = :id"), {"id": model_id})
            row = result.fetchone()
            if row and row[0]:
                return dict(row[0])
        sync_engine.dispose()
    except Exception:
        pass
    return {}


def _get_model_docker_images(model_id: str) -> list[dict]:
    """Get the docker_images list for a model (from memory or DB)."""
    from backend.api.models import _DEV_MODELS
    model = _DEV_MODELS.get(model_id)
    if model and model.get("docker_images"):
        imgs = list(model["docker_images"])
        imgs.sort(key=lambda x: x.get("order", 0))
        return imgs
    # Check DB
    try:
        from backend.config import settings
        from sqlalchemy import create_engine, text
        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        with sync_engine.connect() as conn:
            result = conn.execute(text("SELECT docker_images FROM models WHERE id = :id"), {"id": model_id})
            row = result.fetchone()
            if row and row[0]:
                imgs = list(row[0])
                imgs.sort(key=lambda x: x.get("order", 0))
                return imgs
        sync_engine.dispose()
    except Exception:
        pass
    return []


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


def _send_dev_notification(run: dict, event: str) -> None:
    """Send a completion email for a dev-mode run (called from background thread)."""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        SyncSession = sessionmaker(bind=sync_engine)
        db = SyncSession()
        try:
            user = db.execute(
                select(User).where(User.id == run["triggered_by"])
            ).scalar_one_or_none()
            if not user or not user.email:
                _run_logger.warning("No email for user %s, skipping dev notification", run.get("triggered_by"))
                return

            model_name = _get_model_name(run["model_id"])
            duration = ""
            if run.get("started_at") and run.get("completed_at"):
                started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
                completed = datetime.fromisoformat(run["completed_at"].replace("Z", "+00:00"))
                delta = completed - started
                hours, rem = divmod(int(delta.total_seconds()), 3600)
                mins, secs = divmod(rem, 60)
                duration = f"{hours}h {mins}m {secs}s"

            subject = f"[ALMPlatform] Run {event}: {model_name}"
            body = (
                f"Run ID: {run['id']}\n"
                f"Model: {model_name}\n"
                f"Status: {event}\n"
                f"Duration: {duration or 'N/A'}\n"
                f"Link: {settings.APP_BASE_URL}/runs/{run['id']}\n"
            )
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_FROM
            msg["To"] = user.email

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.send_message(msg)

            _run_logger.info("Sent '%s' notification for dev run %s to %s", event, run["id"], user.email)
        finally:
            db.close()
            sync_engine.dispose()
    except Exception as exc:
        _run_logger.error("Failed to send dev notification for run %s: %s", run.get("id"), exc)


def _run_model_and_notify(run_id: str):
    """Wrapper: run the model then send an email notification on any terminal state."""
    _run_model(run_id)
    run = _DEV_RUNS.get(run_id)
    if run and run.get("status") in ("completed", "failed", "cancelled"):
        _send_dev_notification(run, run["status"])


def _run_model(run_id: str):
    """Background thread to run a model.

    For test models (hardcoded demo IDs), uses simulated progress.
    For real models, uses DockerRunner to execute actual containers.
    """
    run = _DEV_RUNS.get(run_id)
    if not run:
        return

    model_id = run["model_id"]
    model_name = _get_model_name(model_id)
    docker_images = _get_model_docker_images(model_id)
    logs = _DEV_LOGS.setdefault(run_id, [])

    # Determine if this is a test/demo model
    _TEST_MODEL_IDS = {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    }
    is_test_model = model_id in _TEST_MODEL_IDS

    if docker_images:
        containers = [img.get("name", f"step-{img.get('order', i+1)}") for i, img in enumerate(docker_images)]
    else:
        containers = ["step-1"]

    time.sleep(1)

    if run.get("_cancelled"):
        run["status"] = "cancelled"
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        logs.append("[system] Run cancelled before start")
        _save_run_metadata(run)
        _ACTIVE_RUN_IDS.discard(run_id)
        _try_start_next_run()
        return

    run["status"] = "running"
    run["started_at"] = datetime.now(timezone.utc).isoformat()
    run["queue_position"] = None
    logs.append(f"[system] Starting run for {model_name}")
    _save_run_metadata(run)

    # Initialize container stats tracking
    run["container_stats"] = {}

    if is_test_model:
        # ── Simulated run for test/demo models ──
        for idx, container in enumerate(containers):
            if run.get("_cancelled"):
                run["status"] = "cancelled"
                run["completed_at"] = datetime.now(timezone.utc).isoformat()
                logs.append(f"[system] Run cancelled during {container}")
                _save_run_metadata(run)
                _ACTIVE_RUN_IDS.discard(run_id)
                _try_start_next_run()
                return

            run["current_container_index"] = idx
            container_start = time.time()
            logs.append(f"[{container}] Starting container {idx + 1}/{len(containers)}...")

            steps = 5 if container == "data-updater" else 8 if container == "analyze" else 6
            for step in range(steps):
                if run.get("_cancelled"):
                    run["status"] = "cancelled"
                    run["completed_at"] = datetime.now(timezone.utc).isoformat()
                    logs.append(f"[system] Run cancelled during {container}")
                    _save_run_metadata(run)
                    _ACTIVE_RUN_IDS.discard(run_id)
                    _try_start_next_run()
                    return
                progress = ((step + 1) / steps) * 100
                logs.append(f"[{container}] Progress: {progress:.0f}%")
                time.sleep(0.5)

            container_duration = round(time.time() - container_start, 2)
            # Generate simulated resource stats for test models
            import random
            sim_cpu = round(random.uniform(15, 95), 2)
            sim_mem = round(random.uniform(128, 2048), 2)
            sim_disk = round(random.uniform(10, 500), 2)
            # Find image name for this container
            img_name = ""
            if docker_images and idx < len(docker_images):
                img_name = docker_images[idx].get("image", "")
            run["container_stats"][container] = {
                "image": img_name,
                "max_cpu_percent": sim_cpu,
                "max_memory_mb": sim_mem,
                "max_disk_mb": sim_disk,
                "duration_seconds": container_duration,
            }
            logs.append(f"[{container}] Container completed successfully (CPU: {sim_cpu}%, Mem: {sim_mem}MB, {container_duration}s)")

        # Generate sample output files for test models
        output_path = run.get("output_path", os.path.join(settings.RUNS_BASE_PATH, run_id, "outputs"))
        _generate_sample_outputs(run_id, output_path, model_name)
        logs.append(f"[system] Output files generated at {output_path}")

    else:
        # ── Real Docker execution for non-test models ──
        try:
            from backend.docker_runner.runner import DockerRunner, ImageNotFoundError
            docker_runner = DockerRunner()
        except Exception as exc:
            logs.append(f"[system] ERROR: Failed to initialize Docker runner: {exc}")
            run["status"] = "failed"
            run["completed_at"] = datetime.now(timezone.utc).isoformat()
            _save_run_metadata(run)
            _ACTIVE_RUN_IDS.discard(run_id)
            _try_start_next_run()
            return

        output_path = run.get("output_path", os.path.join(settings.RUNS_BASE_PATH, run_id, "outputs"))
        log_path = run.get("log_path", os.path.join(settings.RUNS_BASE_PATH, run_id, "logs"))
        os.makedirs(output_path, exist_ok=True)
        os.makedirs(log_path, exist_ok=True)

        # Get run inputs for variable substitution
        run_inputs = run.get("inputs", {})

        for idx, img_spec in enumerate(docker_images):
            container_name = img_spec.get("name", f"step-{idx + 1}")
            image = img_spec.get("image", "")
            extra_args = img_spec.get("extra_args", "")

            if run.get("_cancelled"):
                run["status"] = "cancelled"
                run["completed_at"] = datetime.now(timezone.utc).isoformat()
                logs.append(f"[system] Run cancelled before {container_name}")
                _save_run_metadata(run)
                _ACTIVE_RUN_IDS.discard(run_id)
                _try_start_next_run()
                return

            run["current_container_index"] = idx
            logs.append(f"[{container_name}] Starting container {idx + 1}/{len(docker_images)} (image: {image})...")

            # Build base volume mounts
            volumes = {
                output_path: {"bind": "/data/output", "mode": "rw"},
                log_path: {"bind": "/data/logs", "mode": "rw"},
            }

            try:
                result = docker_runner.run_container(
                    image=image,
                    volumes=volumes,
                    extra_args=extra_args,
                    run_id=run_id,
                    container_name=container_name,
                    run_inputs=run_inputs,
                )

                # Stream the container's log into _DEV_LOGS
                if result.log:
                    for line in result.log.splitlines():
                        logs.append(f"[{container_name}] {line}")

                # Save container log to file
                container_log_file = os.path.join(log_path, f"{container_name}.log")
                with open(container_log_file, "w") as f:
                    f.write(result.log or "")

                # Calculate disk usage of output path
                disk_mb = 0.0
                try:
                    for dirpath, dirnames, filenames in os.walk(output_path):
                        for fname in filenames:
                            disk_mb += os.path.getsize(os.path.join(dirpath, fname))
                    disk_mb = round(disk_mb / (1024 * 1024), 2)
                except Exception:
                    pass

                # Store per-container resource stats
                run["container_stats"][container_name] = {
                    "image": image,
                    "max_cpu_percent": result.max_cpu_percent,
                    "max_memory_mb": result.max_memory_mb,
                    "max_disk_mb": disk_mb,
                    "duration_seconds": result.duration_seconds,
                }

                if result.exit_code != 0:
                    logs.append(f"[{container_name}] Container FAILED with exit code {result.exit_code}")
                    run["status"] = "failed"
                    run["completed_at"] = datetime.now(timezone.utc).isoformat()
                    _save_run_metadata(run)
                    _ACTIVE_RUN_IDS.discard(run_id)
                    _try_start_next_run()
                    return

                logs.append(f"[{container_name}] Container completed (CPU: {result.max_cpu_percent}%, Mem: {result.max_memory_mb}MB, {result.duration_seconds}s)")

            except ImageNotFoundError as exc:
                logs.append(f"[{container_name}] ERROR: {exc}")
                run["status"] = "failed"
                run["completed_at"] = datetime.now(timezone.utc).isoformat()
                _save_run_metadata(run)
                _ACTIVE_RUN_IDS.discard(run_id)
                _try_start_next_run()
                return
            except Exception as exc:
                logs.append(f"[{container_name}] ERROR: Container execution failed: {exc}")
                run["status"] = "failed"
                run["completed_at"] = datetime.now(timezone.utc).isoformat()
                _save_run_metadata(run)
                _ACTIVE_RUN_IDS.discard(run_id)
                _try_start_next_run()
                return

        # List the real output files
        output_files = []
        for root, dirs, files in os.walk(output_path):
            for f in files:
                output_files.append(os.path.join(root, f))
        if output_files:
            logs.append(f"[system] {len(output_files)} output file(s) produced")
        else:
            logs.append("[system] No output files produced by containers")

    run["status"] = "completed"
    run["completed_at"] = datetime.now(timezone.utc).isoformat()
    logs.append("[system] Run completed successfully")
    _save_run_metadata(run)

    # Free the slot and try to start the next queued run
    _ACTIVE_RUN_IDS.discard(run_id)
    _try_start_next_run()


# ─── Resource-based smart concurrency ───

# Default resource estimates for models with no historical data.
# Set to the full budget so an unknown model occupies all slots — preventing
# it from running alongside any other container until we have real measurements.
_DEFAULT_CPU_ESTIMATE = settings.MAX_TOTAL_CPU_PERCENT
_DEFAULT_MEMORY_ESTIMATE = settings.MAX_TOTAL_MEMORY_MB

# Sample historical stats for built-in dev models so the UI shows estimates
# before any real runs have been executed.  Values reflect:
#   avg_duration_seconds  = average of (sum of container durations) across past runs
#   avg_memory_mb         = average of (max container memory) across past runs
#   avg_cpu_percent       = average of (max container CPU %) across past runs
_DEV_MODEL_SAMPLE_STATS: dict[str, dict] = {
    "11111111-1111-1111-1111-111111111111": {  # Interest Rate Model (3 containers)
        "avg_cpu_percent": 78.5,
        "avg_memory_mb": 24576.0,   # ~24 GB peak
        "avg_disk_mb": 420.0,
        "avg_duration_seconds": 79200.0,  # ~22 h total
        "sample_count": 3,
    },
    "22222222-2222-2222-2222-222222222222": {  # Credit Risk Model
        "avg_cpu_percent": 92.0,
        "avg_memory_mb": 32768.0,   # ~32 GB peak
        "avg_disk_mb": 850.0,
        "avg_duration_seconds": 108000.0,  # ~30 h total
        "sample_count": 4,
    },
    "33333333-3333-3333-3333-333333333333": {  # Liquidity Model
        "avg_cpu_percent": 45.2,
        "avg_memory_mb": 8192.0,    # ~8 GB peak
        "avg_disk_mb": 200.0,
        "avg_duration_seconds": 25200.0,  # ~7 h total
        "sample_count": 2,
    },
}


def _get_model_avg_resources(model_id: str) -> dict:
    """Compute average resource usage for a model from historical runs.

    For each completed run, takes the *maximum* value across all its containers
    for CPU, memory, and disk (representing peak load during that run), and the
    *sum* of container durations (total wall-clock time). Then averages those
    per-run figures across all historical runs.

    Falls back to conservative defaults if no data is available.
    """
    cpu_vals = []
    mem_vals = []
    disk_vals = []
    dur_vals = []

    for run in _DEV_RUNS.values():
        if run.get("model_id") != model_id:
            continue
        if run.get("status") not in ("completed", "failed"):
            continue
        stats = run.get("container_stats", {})
        if not stats:
            continue
        container_list = list(stats.values())
        run_cpu = max((c.get("max_cpu_percent") or 0 for c in container_list), default=0)
        run_mem = max((c.get("max_memory_mb") or 0 for c in container_list), default=0)
        run_disk = max((c.get("max_disk_mb") or 0 for c in container_list), default=0)
        run_dur = sum(c.get("duration_seconds") or 0 for c in container_list)
        if run_cpu > 0:
            cpu_vals.append(run_cpu)
        if run_mem > 0:
            mem_vals.append(run_mem)
        if run_disk > 0:
            disk_vals.append(run_disk)
        if run_dur > 0:
            dur_vals.append(run_dur)

    if cpu_vals:
        return {
            "avg_cpu_percent": round(sum(cpu_vals) / len(cpu_vals), 2),
            "avg_memory_mb": round(sum(mem_vals) / len(mem_vals), 2) if mem_vals else 0.0,
            "avg_disk_mb": round(sum(disk_vals) / len(disk_vals), 2) if disk_vals else 0.0,
            "avg_duration_seconds": round(sum(dur_vals) / len(dur_vals), 2) if dur_vals else 0.0,
            "sample_count": len(cpu_vals),
        }

    # No real run data — use pre-seeded sample stats for known dev models
    sample = _DEV_MODEL_SAMPLE_STATS.get(model_id)
    if sample:
        return sample

    # Truly unknown model: return conservative budget defaults with sample_count=0
    # so the UI can distinguish "no data" from "has data".
    return {
        "avg_cpu_percent": _DEFAULT_CPU_ESTIMATE,
        "avg_memory_mb": _DEFAULT_MEMORY_ESTIMATE,
        "avg_disk_mb": 0.0,
        "avg_duration_seconds": 0.0,
        "sample_count": 0,
    }


def _get_current_resource_usage() -> dict:
    """Sum the estimated resource usage of all currently active runs.

    Each active run contributes one 'container slot' of resources
    (containers within a run are sequential, so only 1 is active at a time).
    """
    total_cpu = 0.0
    total_mem = 0.0

    for run_id in _ACTIVE_RUN_IDS:
        run = _DEV_RUNS.get(run_id)
        if not run:
            continue
        model_id = run.get("model_id", "")
        avg = _get_model_avg_resources(model_id)
        total_cpu += avg["avg_cpu_percent"]
        total_mem += avg["avg_memory_mb"]

    return {"total_cpu_percent": total_cpu, "total_memory_mb": total_mem}


def _try_start_next_run():
    """Promote queued runs to running if resources are available.

    Uses historical per-model resource averages to estimate whether the
    next queued run's container would fit within the configured thresholds.
    Containers within a run execute sequentially (in order).
    """
    queued = [r for r in _DEV_RUNS.values() if r["status"] == "queued" and r["id"] not in _ACTIVE_RUN_IDS]
    if not queued:
        return

    queued.sort(key=lambda r: r.get("queue_position", 999))

    current = _get_current_resource_usage()

    for next_run in queued:
        run_id = next_run["id"]
        model_id = next_run.get("model_id", "")
        next_avg = _get_model_avg_resources(model_id)

        projected_cpu = current["total_cpu_percent"] + next_avg["avg_cpu_percent"]
        projected_mem = current["total_memory_mb"] + next_avg["avg_memory_mb"]

        fits = (
            projected_cpu <= settings.MAX_TOTAL_CPU_PERCENT
            and projected_mem <= settings.MAX_TOTAL_MEMORY_MB
        )

        if fits:
            _ACTIVE_RUN_IDS.add(run_id)
            current["total_cpu_percent"] = projected_cpu
            current["total_memory_mb"] = projected_mem

            _run_logger.info(
                "Promoting queued run %s (model: %s) — projected CPU: %.0f%% / %.0f%%, Mem: %.0f MB / %.0f MB",
                run_id[:8], _get_model_name(model_id),
                projected_cpu, settings.MAX_TOTAL_CPU_PERCENT,
                projected_mem, settings.MAX_TOTAL_MEMORY_MB,
            )

            thread = threading.Thread(target=_run_model_and_notify, args=(run_id,), daemon=True)
            thread.start()
        else:
            _run_logger.debug(
                "Run %s would exceed thresholds (CPU: %.0f%%, Mem: %.0f MB) — staying queued",
                run_id[:8], projected_cpu, projected_mem,
            )
            break


# ─── Run Endpoints ───

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_run(
    body: RunCreate,
    current_user: User = Depends(require_role(["admin", "developer", "runner"])),
    db: AsyncSession = Depends(get_db),
):
    """Create a new run."""
    if settings.is_develop:
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

        output_path = os.path.join(settings.RUNS_BASE_PATH, run_id, "outputs")
        log_path = os.path.join(settings.RUNS_BASE_PATH, run_id, "logs")
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
        _save_run_metadata(run)

        # Only start immediately if resources are available
        current = _get_current_resource_usage()
        next_avg = _get_model_avg_resources(model_id)
        projected_cpu = current["total_cpu_percent"] + next_avg["avg_cpu_percent"]
        projected_mem = current["total_memory_mb"] + next_avg["avg_memory_mb"]
        fits = (
            projected_cpu <= settings.MAX_TOTAL_CPU_PERCENT
            and projected_mem <= settings.MAX_TOTAL_MEMORY_MB
        )
        if fits:
            _ACTIVE_RUN_IDS.add(run_id)
            thread = threading.Thread(target=_run_model_and_notify, args=(run_id,), daemon=True)
            thread.start()
        else:
            _DEV_LOGS[run_id].append(
                f"[system] Waiting in queue — projected CPU: {projected_cpu:.0f}% / {settings.MAX_TOTAL_CPU_PERCENT:.0f}%,"
                f" Mem: {projected_mem:.0f} MB / {settings.MAX_TOTAL_MEMORY_MB:.0f} MB"
            )

        from backend.api.audit import log_action
        await log_action(
            username=current_user.ldap_username, user_id=str(current_user.id),
            action="create_run", resource_type="run", resource_id=run_id,
            details={"model_id": model_id, "model_name": _get_model_name(model_id)},
            db=db,
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
        await log_action(
            username=current_user.ldap_username,
            user_id=str(current_user.id),
            action="create_run",
            resource_type="run",
            resource_id=str(run.id),
            details={"model_id": str(body.model_id), "model_name": model_obj.name if model_obj else "Unknown"},
            db=db,
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
    # In dev mode, merge in-memory runs (scheduler + current session) with DB runs (historical)
    if settings.is_develop:
        in_memory_runs = list(_DEV_RUNS.values())
        if model_id:
            in_memory_runs = [r for r in in_memory_runs if r["model_id"] == str(model_id)]
        if status_filter:
            in_memory_runs = [r for r in in_memory_runs if r["status"] == status_filter]
        if triggered_by:
            in_memory_runs = [r for r in in_memory_runs if r["triggered_by"] == str(triggered_by)]
        for r in in_memory_runs:
            r["model_name"] = _get_model_name(r["model_id"])
            if "username" not in r:
                r["username"] = "admin"
        in_memory_ids = {r["id"] for r in in_memory_runs}

        # Also fetch DB runs and merge (dedup by ID)
        db_query = select(Run).order_by(Run.created_at.desc())
        db_conditions = []
        if model_id:
            db_conditions.append(Run.model_id == model_id)
        if status_filter:
            db_conditions.append(Run.status == status_filter)
        if triggered_by:
            db_conditions.append(Run.triggered_by == triggered_by)
        if db_conditions:
            db_query = db_query.where(and_(*db_conditions))
        db_result = await db.execute(db_query)
        db_runs = db_result.scalars().all()

        for db_run in db_runs:
            if str(db_run.id) not in in_memory_ids:
                run_dict = {
                    "id": str(db_run.id),
                    "model_id": str(db_run.model_id),
                    "triggered_by": str(db_run.triggered_by) if db_run.triggered_by else None,
                    "status": db_run.status,
                    "inputs": db_run.inputs,
                    "config_snapshot": db_run.config_snapshot,
                    "celery_task_id": db_run.celery_task_id,
                    "current_container_index": db_run.current_container_index,
                    "queue_position": db_run.queue_position,
                    "started_at": db_run.started_at.isoformat() if db_run.started_at else None,
                    "completed_at": db_run.completed_at.isoformat() if db_run.completed_at else None,
                    "created_at": db_run.created_at.isoformat() if db_run.created_at else None,
                    "is_archived": db_run.is_archived,
                    "archived_at": db_run.archived_at.isoformat() if db_run.archived_at else None,
                    "archive_path": db_run.archive_path,
                    "output_path": db_run.output_path,
                    "log_path": db_run.log_path,
                }
                # Resolve model name + username
                model_result = await db.execute(select(Model.name).where(Model.id == db_run.model_id))
                run_dict["model_name"] = model_result.scalar_one_or_none() or "Unknown"
                if db_run.triggered_by:
                    user_result = await db.execute(select(User.ldap_username).where(User.id == db_run.triggered_by))
                    run_dict["username"] = user_result.scalar_one_or_none() or "Unknown"
                else:
                    run_dict["username"] = "Unknown"
                in_memory_runs.append(run_dict)

        in_memory_runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return in_memory_runs[offset:offset + limit]

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
    if settings.is_develop:
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
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=5000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get logs for a run (paginated). Falls back to disk if not in memory."""
    if settings.is_develop:
        logs = _DEV_LOGS.get(str(run_id), [])
        # If no in-memory logs, try to load from disk
        if not logs:
            run = _DEV_RUNS.get(str(run_id))
            log_path = run.get("log_path", "") if run else ""
            if not log_path:
                log_path = os.path.join(settings.RUNS_BASE_PATH, str(run_id), "logs")
            logs = _load_logs_from_disk(str(run_id), log_path)
        total = len(logs)
        page = logs[offset:offset + limit]
        return {"logs": page, "total": total, "has_more": (offset + limit) < total}
    return {"logs": [], "total": 0, "has_more": False}


@router.get("/{run_id}/outputs")
async def list_run_outputs(
    run_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List output files for a run."""
    if settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        output_path = run.get("output_path", "")
        if not output_path or not os.path.isdir(output_path):
            # Fallback: check RUNS_BASE_PATH
            output_path = os.path.join(settings.RUNS_BASE_PATH, str(run_id), "outputs")
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
    if settings.is_develop:
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
    if settings.is_develop:
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
    if settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if run:
            if run["is_archived"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already archived")
            if run["status"] not in ("completed", "failed", "cancelled"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run must be completed/failed/cancelled")

            import shutil
            model_id_str = run.get("model_id", "")
            model_config = _get_model_config(model_id_str)
            # Use slug for folder name; fall back to model_id if not found
            model_slug = model_config.get("slug", model_id_str) if isinstance(model_config, dict) else model_id_str
            if not model_slug:
                model_slug = model_id_str or "unknown"
            model_name = _get_model_name(model_id_str)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            archive_path = os.path.join(
                settings.ARCHIVE_BASE_PATH,
                current_user.ldap_username,
                model_slug,
                date_str,
                str(run_id),
            )
            os.makedirs(archive_path, exist_ok=True)

            # Copy run output and log directories into archive
            source_dir = os.path.join(settings.RUNS_BASE_PATH, str(run_id))
            if os.path.isdir(source_dir):
                shutil.copytree(source_dir, archive_path, dirs_exist_ok=True)

            run["is_archived"] = True
            run["archived_at"] = datetime.now(timezone.utc).isoformat()
            run["archive_path"] = archive_path
            _save_run_metadata(run)

            from backend.api.audit import log_action
            await log_action(
                username=current_user.ldap_username, user_id=str(current_user.id),
                action="archive_run", resource_type="run", resource_id=str(run_id),
                details={"model_name": model_name},
                db=db,
            )
            return run
        # Fall through to DB path if not in memory

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
    if settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if run:
            if not run["is_archived"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not archived")

            run["is_archived"] = False
            run["archived_at"] = None
            run["archive_path"] = None
            _save_run_metadata(run)

            from backend.api.audit import log_action
            await log_action(
                username=current_user.ldap_username, user_id=str(current_user.id),
                action="unarchive_run", resource_type="run", resource_id=str(run_id),
                details={"model_name": run.get("model_name", "")},
                db=db,
            )
            return run
        # Fall through to DB path if not in memory

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
    if settings.is_develop:
        run = _DEV_RUNS.get(str(run_id))
        if run:
            import shutil
            run_name = run.get("model_name", "")
            # Clean up disk files
            run_dir = os.path.join(settings.RUNS_BASE_PATH, str(run_id))
            if os.path.isdir(run_dir):
                shutil.rmtree(run_dir, ignore_errors=True)
            archive_path = run.get("archive_path", "")
            if archive_path and os.path.isdir(archive_path):
                shutil.rmtree(archive_path, ignore_errors=True)

            del _DEV_RUNS[str(run_id)]
            _DEV_LOGS.pop(str(run_id), None)

            from backend.api.audit import log_action
            await log_action(
                username=current_user.ldap_username, user_id=str(current_user.id),
                action="delete_run", resource_type="run", resource_id=str(run_id),
                details={"model_name": run_name},
                db=db,
            )
            return {"detail": f"Run {run_id} deleted"}
        # Fall through to DB path if not in memory

    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run_model_id = str(run.model_id) if run.model_id else ""
    await db.delete(run)
    await db.flush()

    from backend.api.audit import log_action
    await log_action(
        username=current_user.ldap_username, user_id=str(current_user.id),
        action="delete_run", resource_type="run", resource_id=str(run_id),
        details={"model_id": run_model_id},
        db=db,
    )
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

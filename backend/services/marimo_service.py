"""Service for managing Marimo notebook instances per developer user."""

import logging
import os
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Optional
from uuid import UUID

from backend.config import settings

logger = logging.getLogger(__name__)

# Port range for Marimo instances
MARIMO_PORT_START = 8100
MARIMO_PORT_END = 8200
IDLE_TIMEOUT_SECONDS = 2 * 60 * 60  # 2 hours

# Default notebook content for new users
DEFAULT_NOTEBOOK_CONTENT = '''import marimo

__generated_with = "0.17.6"
app = marimo.App()


@app.cell
def __():
    import marimo as mo
    import os
    import pandas as pd
    return mo, os, pd


@app.cell
def __(mo, os):
    mo.md(f"""
    # Financial Model Data Explorer

    **NAS Path**: `{os.environ.get('SHARED_NAS_PATH', 'Not Set')}`
    **Runs Path**: `{os.environ.get('RUNS_BASE_PATH', 'Not Set')}`
    """)
    return


@app.cell
def __(os, pd):
    # List available data in the shared NAS
    nas_path = os.environ.get("SHARED_NAS_PATH", "/mnt/nas/shared")
    if os.path.exists(nas_path):
        files = os.listdir(nas_path)
        print(f"Available files in NAS: {len(files)}")
        for f in files[:20]:
            print(f"  {f}")
    else:
        print(f"NAS path not available: {nas_path}")
    return nas_path, files


if __name__ == "__main__":
    app.run()
'''


class MarimoInstance:
    """Tracks a running Marimo process."""

    def __init__(self, process: subprocess.Popen, port: int, username: str):
        self.process = process
        self.port = port
        self.username = username
        self.started_at = datetime.now(timezone.utc)
        self.last_activity = datetime.now(timezone.utc)

    def is_alive(self) -> bool:
        return self.process.poll() is None

    def is_idle(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.last_activity).total_seconds()
        return elapsed > IDLE_TIMEOUT_SECONDS

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)

    def kill(self) -> None:
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self.process.wait(timeout=10)
        except Exception:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except Exception:
                pass
        logger.info("Killed Marimo instance for user '%s' on port %d", self.username, self.port)


class MarimoService:
    """Manages Marimo notebook instances — one per developer user."""

    def __init__(self) -> None:
        self._instances: dict[str, MarimoInstance] = {}  # keyed by username
        self._port_map: dict[str, int] = {}  # username -> port
        self._lock = Lock()
        self._next_port = MARIMO_PORT_START

        # Start the idle checker thread
        self._checker = Thread(target=self._idle_checker, daemon=True)
        self._checker.start()

    def _get_port(self, username: str) -> int:
        """Assign a consistent port to a user."""
        if username in self._port_map:
            return self._port_map[username]

        port = self._next_port
        if port > MARIMO_PORT_END:
            raise RuntimeError("No available ports in Marimo port range (8100-8200)")

        self._port_map[username] = port
        self._next_port += 1
        return port

    def _ensure_notebook(self, username: str) -> str:
        """Copy preset notebook to user's Marimo directory on first launch."""
        base_path = settings.MARIMO_BASE_PATH
        # In dev mode, use a writable temp directory to avoid read-only filesystem errors
        if settings.is_develop:
            base_path = "/tmp/marimo"
        user_dir = os.path.join(base_path, username)
        notebook_path = os.path.join(user_dir, "explorer.py")

        if not os.path.exists(notebook_path):
            os.makedirs(user_dir, exist_ok=True)
            with open(notebook_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_NOTEBOOK_CONTENT)
            logger.info("Created default Marimo notebook for user '%s'", username)

        return notebook_path

    def launch_for_user(self, username: str) -> int:
        """
        Launch a Marimo instance for a developer user.

        If already running, returns existing port. Otherwise kills any stale
        process, starts a new one, and returns the port.

        Args:
            username: LDAP username of the developer.

        Returns:
            The port number where Marimo is listening.
        """
        with self._lock:
            # Check for existing running instance
            existing = self._instances.get(username)
            if existing and existing.is_alive():
                existing.touch()
                return existing.port

            # Kill stale instance if exists
            if existing:
                existing.kill()
                del self._instances[username]

            port = self._get_port(username)
            notebook_path = self._ensure_notebook(username)

            env = os.environ.copy()
            env["SHARED_NAS_PATH"] = settings.SHARED_NAS_PATH
            env["RUNS_BASE_PATH"] = settings.RUNS_BASE_PATH
            env["ARCHIVE_BASE_PATH"] = settings.ARCHIVE_BASE_PATH

            # Kill any stale process holding the port
            try:
                import signal
                result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip():
                    for pid_str in result.stdout.strip().split("\n"):
                        try:
                            os.kill(int(pid_str.strip()), signal.SIGKILL)
                            logger.info("Killed stale process %s on port %d", pid_str.strip(), port)
                        except (ValueError, OSError):
                            pass
                    time.sleep(1)
            except Exception:
                pass

            try:
                process = subprocess.Popen(
                    [
                        "marimo", "edit",
                        notebook_path,
                        "--host", "127.0.0.1",
                        "--port", str(port),
                        "--headless",
                        "--no-token",
                    ],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

                # Wait a moment for the process to start
                time.sleep(3)

                if process.poll() is not None:
                    stderr_output = ""
                    try:
                        stderr_output = process.stderr.read().decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    logger.error("Marimo stderr: %s", stderr_output)
                    raise RuntimeError(
                        f"Marimo process exited immediately with code {process.returncode}: {stderr_output[:200]}"
                    )

                instance = MarimoInstance(process, port, username)
                self._instances[username] = instance

                logger.info("Launched Marimo for user '%s' on port %d", username, port)
                return port

            except Exception as exc:
                logger.error("Failed to launch Marimo for user '%s': %s", username, exc)
                raise

    def get_status(self, username: str) -> dict:
        """Get the status of a user's Marimo instance."""
        with self._lock:
            instance = self._instances.get(username)
            if instance and instance.is_alive():
                instance.touch()
                return {
                    "running": True,
                    "port": instance.port,
                    "started_at": instance.started_at.isoformat(),
                }
            return {"running": False}

    def _idle_checker(self) -> None:
        """Background thread that kills idle Marimo instances."""
        while True:
            time.sleep(300)  # Check every 5 minutes
            with self._lock:
                to_remove: list[str] = []
                for username, instance in self._instances.items():
                    if not instance.is_alive():
                        to_remove.append(username)
                    elif instance.is_idle():
                        logger.info("Killing idle Marimo instance for user '%s'", username)
                        instance.kill()
                        to_remove.append(username)
                for username in to_remove:
                    del self._instances[username]


# Global singleton
marimo_service = MarimoService()

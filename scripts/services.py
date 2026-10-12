"""Manage only the development processes launched by this helper."""

import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
RUNTIME.mkdir(exist_ok=True)
STATE = RUNTIME / "services.json"


def owned(pid, fragment):
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().decode().replace("\0", " ")
        return fragment in command and str(ROOT) in command
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return False


def ready(url, expected):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200 and expected in r.read().decode()
    except Exception:
        return False


def stop(state):
    for name, details in state.items():
        if owned(details["pid"], details["fragment"]):
            os.killpg(details["pid"], signal.SIGTERM)
            for _ in range(20):
                if not owned(details["pid"], details["fragment"]):
                    break
                time.sleep(0.1)
            print("Stopped " + name)
    STATE.unlink(missing_ok=True)


with (RUNTIME / "services.lock").open("w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        stop(state)
        sys.exit(0)
    targets = {
        "backend": {
            "args": [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            "cwd": ROOT,
            "fragment": "uvicorn backend.app.main:app",
            "url": "http://127.0.0.1:8000/api/health",
            "expected": '"status":"ok"',
        },
        "frontend": {
            "args": [
                "node",
                str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
                "--strictPort",
            ],
            "cwd": ROOT / "frontend",
            "fragment": "vite/bin/vite.js",
            "url": "http://127.0.0.1:5173/",
            "expected": "ClearLedger",
        },
    }
    for name, target in targets.items():
        current = state.get(name)
        if (
            current
            and owned(current["pid"], current["fragment"])
            and ready(target["url"], target["expected"])
        ):
            print(name + " already ready")
            continue
        if current and owned(current["pid"], current["fragment"]):
            raise SystemExit(
                name
                + " is running but unhealthy; inspect runtime/"
                + name
                + ".log before restarting"
            )
        if ready(target["url"], target["expected"]):
            raise SystemExit(
                name
                + " port has an unmanaged server; stop that server yourself before managed startup"
            )
        with (RUNTIME / (name + ".log")).open("ab") as log:
            process = subprocess.Popen(
                target["args"],
                cwd=target["cwd"],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        state[name] = {"pid": process.pid, "fragment": target["fragment"]}
        STATE.write_text(json.dumps(state))
        for _ in range(40):
            if process.poll() is not None:
                raise SystemExit(name + " exited; inspect runtime/" + name + ".log")
            if ready(target["url"], target["expected"]):
                break
            time.sleep(0.25)
        else:
            raise SystemExit(name + " readiness failed; inspect its runtime log")
        print(name + " ready")
    if not ready("http://127.0.0.1:5173/api/health", '"status":"ok"'):
        raise SystemExit("Frontend API proxy readiness check failed")
    print("Frontend and backend API proxy verified")

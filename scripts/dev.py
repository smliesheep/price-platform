"""本地开发栈启停（跨平台，替代 PowerShell 脚本）。

用法：
    python scripts/dev.py up [--skip-worker] [--no-docker]
    python scripts/dev.py down
    python scripts/dev.py status
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
PIDS = LOGS / "pids.json"
PY = sys.executable
CREATE_NO_WINDOW = 0x08000000

SERVICES: dict[str, dict] = {
    "mock-shop": {
        "args": ["-u", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8088"],
        "cwd": ROOT / "mock-shop",
        "env": {},
    },
    "api": {
        "args": ["-u", "-m", "uvicorn", "price_platform.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        "cwd": ROOT,
        "env": {},
    },
    "scheduler": {
        "args": ["-u", "-m", "price_platform.scheduler.main"],
        "cwd": ROOT,
        "env": {"PP_METRICS_PORT": "9101"},
    },
    "reaper": {
        "args": ["-u", "-m", "price_platform.reaper.main"],
        "cwd": ROOT,
        "env": {"PP_METRICS_PORT": "9102"},
    },
    "worker": {
        "args": ["-u", "-m", "price_platform.worker.main"],
        "cwd": ROOT,
        "env": {"PP_METRICS_PORT": "9103"},
    },
}


def is_alive(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return exit_code.value == 259  # STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def load_pids() -> dict[str, int]:
    if PIDS.exists():
        try:
            return json.loads(PIDS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_pids(pids: dict[str, int]) -> None:
    LOGS.mkdir(exist_ok=True)
    PIDS.write_text(json.dumps(pids, indent=2), encoding="utf-8")


def docker_up() -> None:
    subprocess.run(
        ["docker", "compose", "-f", "deploy/compose/docker-compose.dev.yml", "up", "-d", "postgres", "redis"],
        cwd=ROOT,
        check=True,
    )


def up(skip_worker: bool = False, docker: bool = True) -> int:
    LOGS.mkdir(exist_ok=True)
    if docker:
        docker_up()

    pids = load_pids()
    names = [n for n in SERVICES if not (skip_worker and n == "worker")]
    for name in names:
        if name in pids and is_alive(pids[name]):
            print(f"    {name:<10} already running pid={pids[name]}")
            continue

        spec = SERVICES[name]
        env = {**os.environ, **spec["env"]}
        out = open(LOGS / f"{name}.out.log", "ab", buffering=0)
        proc = subprocess.Popen(
            [PY, *spec["args"]],
            cwd=str(spec["cwd"]),
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        pids[name] = proc.pid
        print(f"    {name:<10} pid={proc.pid}")

    save_pids(pids)
    time.sleep(5)
    try:
        import httpx

        response = httpx.get("http://127.0.0.1:8000/healthz", timeout=5)
        print("==> api:", response.text)
    except Exception as exc:  # noqa: BLE001
        print("==> api not ready:", exc)
    return 0


def down() -> int:
    pids = load_pids()
    for name, pid in pids.items():
        if is_alive(pid):
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            print(f"stopped {name} (pid={pid})")
    PIDS.unlink(missing_ok=True)
    return 0


def status() -> int:
    pids = load_pids()
    for name, pid in pids.items():
        print(f"{name:<10} pid={pid:<8} {'alive' if is_alive(pid) else 'dead'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["up", "down", "status"])
    parser.add_argument("--skip-worker", action="store_true")
    parser.add_argument("--no-docker", action="store_true")
    args = parser.parse_args()
    if args.action == "up":
        return up(skip_worker=args.skip_worker, docker=not args.no_docker)
    if args.action == "down":
        return down()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())

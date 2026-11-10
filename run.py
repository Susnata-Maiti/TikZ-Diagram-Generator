"""
TikZ Diagram Generator — Unified Development Runner.

Starts both the FastAPI backend and Next.js frontend concurrently
in a single terminal with unified output streaming and graceful shutdown.

Usage:
    python run.py
"""
from __future__ import annotations

import os
import sys
import time
import shutil
import signal
import threading
import subprocess
from pathlib import Path

# Root directory of the repository
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"

# ANSI Colors for terminal output
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def find_python_interpreter() -> str:
    """Find a Python interpreter that has FastAPI and uvicorn installed."""
    candidates = [
        sys.executable,
        str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe"),
        str(BACKEND_DIR / ".venv" / "bin" / "python"),
        str(ROOT_DIR / ".venv" / "Scripts" / "python.exe"),
        str(ROOT_DIR / ".venv" / "bin" / "python"),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            try:
                res = subprocess.run(
                    [candidate, "-c", "import fastapi, uvicorn"],
                    capture_output=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    return candidate
            except Exception:
                continue

    # Fallback to current sys.executable
    return sys.executable


def find_npm_command() -> str:
    """Locate npm on the host system."""
    npm_path = shutil.which("npm.cmd") if sys.platform == "win32" else shutil.which("npm")
    if not npm_path:
        npm_path = shutil.which("npm")
    if not npm_path:
        raise FileNotFoundError(
            "Node.js / npm was not found on your system PATH. "
            "Please install Node.js (v18+) from https://nodejs.org/"
        )
    return npm_path


def stream_output(pipe, prefix: str, color: str, stop_event: threading.Event) -> None:
    """Read lines from a process pipe and print with colored prefix."""
    try:
        for line in iter(pipe.readline, ""):
            if stop_event.is_set():
                break
            if line:
                cleaned = line.rstrip("\r\n")
                print(f"{color}{BOLD}[{prefix}]{RESET} {cleaned}")
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def terminate_process_tree(proc: subprocess.Popen | None) -> None:
    """Forcefully and cleanly terminate a process and all its child processes."""
    if proc is None or proc.poll() is not None:
        return

    pid = proc.pid
    try:
        if sys.platform == "win32":
            # On Windows, taskkill /F /T terminates the entire child process hierarchy
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def main() -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 65}{RESET}")
    print(f"{BOLD}{CYAN}  TikZ Diagram Generator — Unified Launcher{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 65}{RESET}\n")

    # 1. Locate Python
    python_bin = find_python_interpreter()
    print(f"{GREEN}✓{RESET} Python interpreter: {python_bin}")

    # 2. Locate npm
    try:
        npm_bin = find_npm_command()
        print(f"{GREEN}✓{RESET} npm package manager: {npm_bin}")
    except FileNotFoundError as err:
        print(f"{RED}✗ {err}{RESET}")
        sys.exit(1)

    # 3. Ensure frontend .env.local exists
    env_local = FRONTEND_DIR / ".env.local"
    if not env_local.exists():
        print(f"{YELLOW}!{RESET} Creating frontend/.env.local (pointing to http://localhost:8000)...")
        with open(env_local, "w", encoding="utf-8") as f:
            f.write("NEXT_PUBLIC_BACKEND_URL=http://localhost:8000\n")

    # 4. Check for frontend node_modules
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        print(f"{YELLOW}!{RESET} frontend/node_modules not found. Running 'npm install'...")
        res = subprocess.run([npm_bin, "install"], cwd=str(FRONTEND_DIR), check=False)
        if res.returncode != 0:
            print(f"{RED}✗ 'npm install' failed. Please run 'npm install' inside the frontend/ folder.{RESET}")
            sys.exit(1)

    print(f"\n{BOLD}Starting services:{RESET}")
    print(f"  {CYAN}Backend:{RESET}   http://localhost:8000  (API Docs: http://localhost:8000/docs)")
    print(f"  {MAGENTA}Frontend:{RESET}  http://localhost:3000")
    print(f"  {YELLOW}Press Ctrl+C at any time to stop both servers.{RESET}\n")
    print(f"{'─' * 65}\n")

    stop_event = threading.Event()
    backend_proc: subprocess.Popen | None = None
    frontend_proc: subprocess.Popen | None = None

    def signal_handler(sig, frame):
        stop_event.set()
        print(f"\n\n{YELLOW}Shutting down both servers gracefully...{RESET}")
        terminate_process_tree(backend_proc)
        terminate_process_tree(frontend_proc)
        print(f"{GREEN}All servers stopped. Goodbye!{RESET}\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start Backend (FastAPI / uvicorn)
        backend_cmd = [
            python_bin,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--reload",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )

        # Start Frontend (Next.js)
        frontend_cmd = [npm_bin, "run", "dev"]
        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd=str(FRONTEND_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )

        # Start streaming threads
        t_backend = threading.Thread(
            target=stream_output,
            args=(backend_proc.stdout, "BACKEND", CYAN, stop_event),
            daemon=True,
        )
        t_frontend = threading.Thread(
            target=stream_output,
            args=(frontend_proc.stdout, "FRONTEND", MAGENTA, stop_event),
            daemon=True,
        )
        t_backend.start()
        t_frontend.start()

        # Monitor loop
        while not stop_event.is_set():
            time.sleep(0.5)
            # If backend unexpectedly exits
            if backend_proc.poll() is not None:
                print(f"\n{RED}[BACKEND] Process exited with code {backend_proc.returncode}{RESET}")
                break
            # If frontend unexpectedly exits
            if frontend_proc.poll() is not None:
                print(f"\n{RED}[FRONTEND] Process exited with code {frontend_proc.returncode}{RESET}")
                break

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        print(f"\n{YELLOW}Terminating processes...{RESET}")
        terminate_process_tree(backend_proc)
        terminate_process_tree(frontend_proc)
        print(f"{GREEN}Done.{RESET}\n")


if __name__ == "__main__":
    main()

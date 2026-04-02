"""
Launcher — copies the project to an isolated run directory, starts the app,
and handles agent-requested restarts (exit code 42).

The master copy is never modified by agents. Agents have full write access
to the run copy only. On restart, the process re-launches from the same
run directory, picking up any code changes agents made.

Usage:
    python launcher.py              # new run
    python launcher.py --dashboard  # also start the Vite dev server
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RESTART_CODE = 42
EXCLUDE = {".git", ".dev", "runs", "node_modules", "__pycache__", "data", "workspace"}


def copy_project(src: Path, dst: Path) -> None:
    def _ignore(_dir, names):
        ignored = EXCLUDE & set(names)
        # Exclude all .md files — we inject SYSTEM.md as README.md separately
        ignored |= {n for n in names if n.lower().endswith(".md")}
        return ignored

    shutil.copytree(src, dst, ignore=_ignore)

    # Place the AI-friendly system doc as the only README in the run copy
    system_doc = src / "SYSTEM.md"
    if system_doc.exists():
        shutil.copy2(system_doc, dst / "README.md")


def link_node_modules(master: Path, run: Path) -> None:
    """Create a directory junction so the run copy shares node_modules with master."""
    src = master / "dashboard" / "node_modules"
    dst = run / "dashboard" / "node_modules"
    if src.is_dir() and not dst.exists():
        # mklink /J works without elevation on Windows
        subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                       capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Sandbox Launcher")
    parser.add_argument("--dashboard", action="store_true", help="Also start the dashboard dev server")
    args = parser.parse_args()

    master = Path(__file__).resolve().parent
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = master / "runs" / run_id

    print(f"\n  AI SANDBOX LAUNCHER")
    print(f"  Master:  {master}")
    print(f"  Run dir: {run_dir}\n")

    copy_project(master, run_dir)
    link_node_modules(master, run_dir)

    (run_dir / "data").mkdir(exist_ok=True)
    (run_dir / "workspace").mkdir(exist_ok=True)

    # Optionally start dashboard dev server (stays up across app restarts)
    dashboard_proc = None
    if args.dashboard:
        print("  Starting dashboard dev server...")
        dashboard_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(run_dir / "dashboard"),
            shell=True,
        )

    # App restart loop
    try:
        while True:
            print("  Starting app...\n")
            result = subprocess.run(
                [sys.executable, "-m", "app.main"],
                cwd=str(run_dir),
            )
            if result.returncode == RESTART_CODE:
                print("\n  Restart requested by agent. Rebooting...\n")
                continue
            print(f"\n  App exited (code {result.returncode}).")
            break
    except KeyboardInterrupt:
        print("\n  Stopped by user.")
    finally:
        if dashboard_proc:
            dashboard_proc.terminate()


if __name__ == "__main__":
    main()

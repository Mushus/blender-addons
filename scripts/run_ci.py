from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full Docker CI test suite.")
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--skip-static", action="store_true")
    parser.add_argument("--skip-background", action="store_true")
    parser.add_argument("--skip-gui", action="store_true")
    options = parser.parse_args()

    if not options.skip_static:
        _run([sys.executable, "-m", "ruff", "check", "."])
        _run([sys.executable, "-m", "basedpyright"])
        _run([sys.executable, str(SCRIPTS / "make_zip.py")])
        _run([sys.executable, str(SCRIPTS / "check_zip_layout.py")])
        _run([sys.executable, str(SCRIPTS / "run_background_smokes.py"), "--list"])
        _run([sys.executable, str(SCRIPTS / "run_gui_smokes.py"), "--list"])

    if not options.skip_background:
        if options.skip_static:
            _run([sys.executable, str(SCRIPTS / "make_zip.py")])
        _run(
            [
                sys.executable,
                str(SCRIPTS / "run_background_smokes.py"),
                "--blender",
                options.blender,
            ]
        )

    if not options.skip_gui:
        if options.skip_static and options.skip_background:
            _run([sys.executable, str(SCRIPTS / "make_zip.py")])
        _run(
            [
                sys.executable,
                str(SCRIPTS / "run_gui_smokes.py"),
                "--blender",
                options.blender,
            ]
        )

    print("CI suite passed", flush=True)


if __name__ == "__main__":
    main()

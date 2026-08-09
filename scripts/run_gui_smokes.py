from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DIST = ROOT / "dist"
ARTIFACTS = ROOT / "artifacts"


ADDONS = ROOT / "addons"


def discover_gui() -> list[tuple[str, Path, Path]]:
    targets: list[tuple[str, Path, Path]] = []
    for script in sorted(ADDONS.glob("*/tests/ui_smoke_test.py")):
        package_id = script.parents[1].name
        targets.append((f"gui:{package_id}", script, DIST / f"{package_id}.zip"))
    return targets


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    env.setdefault("GALLIUM_DRIVER", "llvmpipe")
    return env


def _run(blender: str, script: Path, zip_path: Path, artifacts: Path, geometry: str) -> None:
    script_rel = str(script.relative_to(ROOT)).replace("\\", "/")
    zip_rel = str(zip_path.relative_to(ROOT)).replace("\\", "/")
    artifacts.mkdir(parents=True, exist_ok=True)
    artifacts_rel = str(artifacts.relative_to(ROOT)).replace("\\", "/")
    package_id = script.parents[1].name
    result_path = artifacts / f"{package_id}_ui_result.txt"
    if result_path.exists():
        result_path.unlink()

    try:
        width, height = (int(value) for value in geometry.lower().split("x", 1))
    except (TypeError, ValueError):
        raise SystemExit(f"Invalid GUI geometry: {geometry!r}; expected WIDTHxHEIGHT") from None

    blender_command = [
        blender,
        "--enable-event-simulate",
        "--factory-startup",
        "--no-window-focus",
        "--window-geometry",
        "0",
        "0",
        str(width),
        str(height),
        "--python",
        script_rel,
        "--",
        "--zip",
        zip_rel,
        "--artifacts",
        artifacts_rel,
    ]
    if shutil.which("xvfb-run"):
        command = [
            "xvfb-run",
            "-a",
            "-s",
            "-screen 0 1920x1080x24",
            *blender_command,
        ]
    else:
        command = blender_command
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=_env(), check=False)
    if not result_path.exists():
        raise SystemExit(
            f"{script.name} produced no result file at {result_path} "
            f"(blender exit={completed.returncode})"
        )
    status_line = result_path.read_text(encoding="utf-8").splitlines()[0].strip()
    if status_line != "PASS":
        detail = result_path.read_text(encoding="utf-8").strip()
        raise SystemExit(f"{script.name} failed:\n{detail}")
    if completed.returncode not in (0, None):
        # quit_blender usually exits 0; non-zero still fails the suite.
        print(f"warning: blender exit code {completed.returncode} after PASS", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and run Blender GUI smoke tests under Xvfb.")
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=ARTIFACTS,
        help="Directory for screenshots and failure dumps",
    )
    parser.add_argument(
        "--window-geometry",
        action="append",
        default=None,
        help="GUI window size as WIDTHxHEIGHT; may be repeated (default: 1024x900 and 1920x1080)",
    )
    options = parser.parse_args()

    targets = discover_gui()
    if options.list:
        for label, script, zip_path in targets:
            print(f"{label}\t{script.name}\t{zip_path.name}")
        return

    if not targets:
        print("No GUI smoke tests discovered", flush=True)
        return

    artifacts = options.artifacts if options.artifacts.is_absolute() else ROOT / options.artifacts
    artifacts.mkdir(parents=True, exist_ok=True)

    for _, _, zip_path in targets:
        if not zip_path.exists():
            raise SystemExit(f"Missing {zip_path}; run scripts/make_zip.py first")

    geometries = options.window_geometry or ["1024x900", "1920x1080"]
    for label, script, zip_path in targets:
        for geometry in geometries:
            run_artifacts = artifacts / geometry.replace("x", "_")
            print(f"==> {label} ({geometry})", flush=True)
            _run(options.blender, script, zip_path, run_artifacts, geometry)

    print(f"GUI smokes passed: {len(targets) * len(geometries)}", flush=True)


if __name__ == "__main__":
    main()

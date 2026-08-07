"""Discover and run documentation screenshot scripts under Xvfb."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DIST = ROOT / "dist"
DEFAULT_OUTPUT = ROOT / "artifacts" / "doc-screenshots"
RESULT_NAME = "doc_screenshot_result.txt"


def discover(only: list[str] | None = None) -> list[tuple[str, Path, Path]]:
    targets: list[tuple[str, Path, Path]] = []
    for script in sorted(SCRIPTS.glob("*_doc_screenshot.py")):
        package_id = script.name.removesuffix("_doc_screenshot.py")
        if only and package_id not in only:
            continue
        targets.append((package_id, script, DIST / f"{package_id}.zip"))
    return targets


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    env.setdefault("GALLIUM_DRIVER", "llvmpipe")
    return env


def _run(
    blender: str,
    package_id: str,
    script: Path,
    zip_path: Path,
    output_dir: Path,
    geometry: str,
) -> None:
    try:
        width, height = (int(value) for value in geometry.lower().split("x", 1))
    except (TypeError, ValueError):
        raise SystemExit(f"Invalid window geometry: {geometry!r}; expected WIDTHxHEIGHT") from None

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / RESULT_NAME
    if result_path.exists():
        result_path.unlink()

    script_rel = str(script.relative_to(ROOT)).replace("\\", "/")
    zip_rel = str(zip_path.relative_to(ROOT)).replace("\\", "/")
    output_rel = str(output_dir.relative_to(ROOT)).replace("\\", "/")

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
        "--output",
        output_rel,
        "--package-id",
        package_id,
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
    detail = result_path.read_text(encoding="utf-8").strip()
    status_line = detail.splitlines()[0].strip()
    if status_line != "PASS":
        raise SystemExit(f"{script.name} failed:\n{detail}")
    if completed.returncode not in (0, None):
        print(f"warning: blender exit code {completed.returncode} after PASS", flush=True)
    print(f"OK {package_id}: {detail}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture documentation screenshots under Xvfb.")
    parser.add_argument("--blender", default="blender")
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="Package id to capture; may be repeated",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Root directory for PNG outputs (default: artifacts/doc-screenshots)",
    )
    parser.add_argument(
        "--window-geometry",
        default="1920x1080",
        help="GUI window size as WIDTHxHEIGHT (default: 1920x1080)",
    )
    options = parser.parse_args()

    targets = discover(options.only)
    if options.list:
        for package_id, script, zip_path in targets:
            print(f"{package_id}\t{script.name}\t{zip_path.name}")
        return

    if not targets:
        raise SystemExit("No *_doc_screenshot.py entries found")

    output_root = options.output if options.output.is_absolute() else ROOT / options.output
    for package_id, script, zip_path in targets:
        if not zip_path.exists():
            raise SystemExit(f"Missing {zip_path}; run scripts/make_zip.py first")
        print(f"==> doc-screenshot:{package_id} ({options.window_geometry})", flush=True)
        _run(
            options.blender,
            package_id,
            script,
            zip_path,
            output_root / package_id,
            options.window_geometry,
        )

    print(f"Doc screenshots captured: {len(targets)}", flush=True)


if __name__ == "__main__":
    main()

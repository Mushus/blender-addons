from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DIST = ROOT / "dist"
PACKAGES_JSON = ROOT / "release" / "packages.json"


def _stable_packages() -> list[dict]:
    catalog = json.loads(PACKAGES_JSON.read_text(encoding="utf-8"))
    return [package for package in catalog["packages"] if package.get("status") == "stable"]


def _suite_id() -> str:
    catalog = json.loads(PACKAGES_JSON.read_text(encoding="utf-8"))
    return str(catalog["suite_id"])


def discover_lifecycle() -> list[tuple[str, Path, str]]:
    """Return (label, zip_path, module_name) for lifecycle smoke."""
    targets: list[tuple[str, Path, str]] = []
    for package in _stable_packages():
        package_id = package["id"]
        targets.append((f"lifecycle:{package_id}", DIST / f"{package_id}.zip", package_id))
    suite = _suite_id()
    targets.append((f"lifecycle:{suite}", DIST / f"{suite}.zip", suite))
    return targets


def discover_functional() -> list[tuple[str, Path, Path]]:
    """Return (label, script_path, zip_path) for tool functional smoke scripts."""
    packages = {package["id"] for package in _stable_packages()}
    targets: list[tuple[str, Path, Path]] = []
    for script in sorted(SCRIPTS.glob("*_smoke_test.py")):
        if script.name == "blender_smoke_test.py":
            continue
        if "_ui_" in script.stem or script.stem.endswith("_ui_smoke_test"):
            continue
        package_id = script.name.removesuffix("_smoke_test.py")
        targets.append((f"functional:{package_id}", script, DIST / f"{package_id}.zip"))

    covered = {label.split(":", 1)[1] for label, _, _ in targets}
    missing = sorted(packages - covered)
    if missing:
        raise SystemExit(
            "Stable packages missing scripts/<id>_smoke_test.py: " + ", ".join(missing)
        )
    extra = sorted(covered - packages)
    if extra:
        raise SystemExit(
            "Smoke scripts without a stable package in release/packages.json: " + ", ".join(extra)
        )
    return targets


def _run(blender: str, script: Path, script_args: list[str]) -> None:
    command = [
        blender,
        "--background",
        "--factory-startup",
        "--python",
        str(script.relative_to(ROOT)).replace("\\", "/"),
        "--",
        *script_args,
    ]
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and run background Blender smoke tests.")
    parser.add_argument(
        "--blender",
        default="blender",
        help="Blender executable (default: blender on PATH, as inside the Docker image)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print discovered tests and exit",
    )
    options = parser.parse_args()

    lifecycle = discover_lifecycle()
    functional = discover_functional()

    if options.list:
        for label, zip_path, module in lifecycle:
            print(f"{label}\t{zip_path.name}\t{module}")
        for label, script, zip_path in functional:
            print(f"{label}\t{script.name}\t{zip_path.name}")
        return

    for _, zip_path, _ in lifecycle:
        if not zip_path.exists():
            raise SystemExit(f"Missing {zip_path}; run scripts/make_zip.py first")
    for _, _, zip_path in functional:
        if not zip_path.exists():
            raise SystemExit(f"Missing {zip_path}; run scripts/make_zip.py first")

    lifecycle_script = SCRIPTS / "blender_smoke_test.py"
    for label, zip_path, module in lifecycle:
        print(f"==> {label}", flush=True)
        _run(
            options.blender,
            lifecycle_script,
            ["--zip", str(zip_path.relative_to(ROOT)).replace("\\", "/"), "--module", module],
        )

    for label, script, zip_path in functional:
        print(f"==> {label}", flush=True)
        _run(
            options.blender,
            script,
            ["--zip", str(zip_path.relative_to(ROOT)).replace("\\", "/")],
        )

    print(
        f"Background smokes passed: {len(lifecycle)} lifecycle + {len(functional)} functional",
        flush=True,
    )


if __name__ == "__main__":
    main()

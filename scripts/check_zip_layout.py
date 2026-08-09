from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scaffold_bundle import package_uses_scaffold_host
from zip_utils import archive_names, iter_files

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PACKAGES_JSON = ROOT / "release" / "packages.json"
SCAFFOLD_HOST = ROOT / "scaffold" / "embedded_host"


def _stable_packages(catalog: dict) -> list[dict]:
    selected = [package for package in catalog["packages"] if package.get("status") == "stable"]
    if not selected:
        raise SystemExit("No stable packages in release/packages.json")
    return selected


def _expected_under(source: Path, zip_prefix: str) -> set[str]:
    # Packager ignores any leftover local embedded_host/; scaffold host is injected instead.
    expected = {
        f"{zip_prefix}/{path.relative_to(source).as_posix()}"
        for path in iter_files(source)
        if "embedded_host" not in path.relative_to(source).parts
    }
    if package_uses_scaffold_host(source):
        if not SCAFFOLD_HOST.is_dir():
            raise SystemExit(f"Missing scaffold host: {SCAFFOLD_HOST}")
        expected |= {
            f"{zip_prefix}/embedded_host/{path.relative_to(SCAFFOLD_HOST).as_posix()}"
            for path in iter_files(SCAFFOLD_HOST)
        }
    return expected


def _assert_contains(zip_path: Path, expected: set[str]) -> None:
    if not zip_path.exists():
        raise SystemExit(f"Missing {zip_path}")
    names = archive_names(zip_path)
    missing = sorted(expected - names)
    if missing:
        raise SystemExit(f"{zip_path}: missing {missing}")
    extra_tests = [name for name in names if "/tests/" in name or name.endswith("/tests") or "_test.py" in name]
    if extra_tests:
        raise SystemExit(f"{zip_path}: forbidden test files included in package: {extra_tests}")


def main() -> None:
    catalog = json.loads(PACKAGES_JSON.read_text(encoding="utf-8"))
    packages = _stable_packages(catalog)
    suite_id = str(catalog["suite_id"])

    for package in packages:
        package_id = package["id"]
        source = ROOT / package["source"]
        if not source.is_dir():
            raise SystemExit(f"Missing package source: {source}")
        if not isinstance(package.get("extension"), dict):
            raise SystemExit(f"{package_id}: missing extension metadata in release/packages.json")
        expected = _expected_under(source, package_id)
        expected.add(f"{package_id}/blender_manifest.toml")
        _assert_contains(DIST / f"{package_id}.zip", expected)

    suite_zip = DIST / f"{suite_id}.zip"
    suite_expected = {
        f"{suite_id}/__init__.py",
        f"{suite_id}/packages.json",
        f"{suite_id}/addons/__init__.py",
    }
    for package in packages:
        source = ROOT / package["source"]
        name = Path(package["source"]).name
        suite_expected |= _expected_under(source, f"{suite_id}/addons/{name}")
        suite_expected.add(f"{suite_id}/addons/{name}/blender_manifest.toml")
    _assert_contains(suite_zip, suite_expected)

    print("ZIP layout check passed")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_manifest import (
    build_manifest_dict,
    package_website,
    parse_bl_info,
    write_manifest,
)
from scaffold_bundle import bundle_scaffold_into_package
from zip_utils import iter_files

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"
PACKAGES_JSON = ROOT / "release" / "packages.json"
SCAFFOLD_ROOT = ROOT / "scaffold"


def _write_extension_manifest(package: dict, package_dir: Path, catalog: dict) -> None:
    extension_meta = package.get("extension")
    if not isinstance(extension_meta, dict):
        raise SystemExit(f"{package['id']}: missing extension metadata in release/packages.json")
    defaults = catalog.get("extension_defaults") or {}
    if not isinstance(defaults, dict):
        raise SystemExit("release/packages.json extension_defaults must be an object")
    bl_info = parse_bl_info(package_dir / "__init__.py")
    manifest = build_manifest_dict(
        package_id=package["id"],
        bl_info=bl_info,
        extension_meta=extension_meta,
        defaults=defaults,
        website=package_website(package["id"]),
    )
    write_manifest(package_dir, manifest)


def _stable_packages(catalog: dict, package_ids: list[str] | None) -> list[dict]:
    selected = [
        package
        for package in catalog["packages"]
        if package.get("status") == "stable"
        and (not package_ids or package["id"] in package_ids)
    ]
    if not selected:
        raise SystemExit("No stable packages selected.")
    return selected


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_files(source_dir):
            archive.write(path, path.relative_to(source_dir.parent).as_posix())


def make_zips(
    *,
    package_ids: list[str] | None = None,
    suite_package_ids: list[str] | None = None,
    skip_suite: bool = False,
) -> list[Path]:
    catalog = json.loads(PACKAGES_JSON.read_text(encoding="utf-8"))
    selected = _stable_packages(catalog, package_ids)
    suite_selected = selected
    if suite_package_ids:
        suite_selected = _stable_packages(catalog, suite_package_ids)
    if not skip_suite and not suite_selected:
        raise SystemExit("No stable packages selected for the suite.")

    if DIST.exists():
        shutil.rmtree(DIST)
    if BUILD.exists():
        shutil.rmtree(BUILD)
    DIST.mkdir(parents=True)
    BUILD.mkdir(parents=True)

    created: list[Path] = []

    if not skip_suite:
        suite_id = str(catalog["suite_id"])
        suite_dir = BUILD / suite_id
        (suite_dir / "addons").mkdir(parents=True)
        shutil.copy2(ROOT / "__init__.py", suite_dir / "__init__.py")
        shutil.copy2(PACKAGES_JSON, suite_dir / "packages.json")
        shutil.copy2(ROOT / "addons" / "__init__.py", suite_dir / "addons" / "__init__.py")
        for package in suite_selected:
            source = ROOT / package["source"]
            dest = suite_dir / "addons" / Path(package["source"]).name
            shutil.copytree(
                source,
                dest,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    "*.pyo",
                    ".DS_Store",
                    "Thumbs.db",
                    "tests",
                    "embedded_host",
                ),
            )
            bundle_scaffold_into_package(dest, SCAFFOLD_ROOT)
            _write_extension_manifest(package, dest, catalog)
        zip_path = DIST / f"{suite_id}.zip"
        _zip_directory(suite_dir, zip_path)
        created.append(zip_path)

    for package in selected:
        package_id = package["id"]
        package_dir = BUILD / package_id
        shutil.copytree(
            ROOT / package["source"],
            package_dir,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "*.pyo",
                ".DS_Store",
                "Thumbs.db",
                "tests",
                "embedded_host",
            ),
        )
        bundle_scaffold_into_package(package_dir, SCAFFOLD_ROOT)
        _write_extension_manifest(package, package_dir, catalog)
        zip_path = DIST / f"{package_id}.zip"
        _zip_directory(package_dir, zip_path)
        created.append(zip_path)

    shutil.rmtree(BUILD)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Build add-on ZIP packages from release/packages.json.")
    parser.add_argument("--package-id", action="append", dest="package_ids", default=[])
    parser.add_argument("--suite-package-id", action="append", dest="suite_package_ids", default=[])
    parser.add_argument("--skip-suite", action="store_true")
    options = parser.parse_args()
    created = make_zips(
        package_ids=options.package_ids or None,
        suite_package_ids=options.suite_package_ids or None,
        skip_suite=options.skip_suite,
    )
    for path in created:
        print(path)


if __name__ == "__main__":
    main()

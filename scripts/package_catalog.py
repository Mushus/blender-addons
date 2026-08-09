from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Canonical per-package file name. Keep one name to avoid ambiguity.
PACKAGE_JSON_NAME = "addon.json"


def _load_pyproject_defaults(root: Path = ROOT) -> tuple[str, str, dict]:
    """Return (suite_id, blender_target, extension_defaults) from pyproject.toml.

    Uses tomllib/tomli when available, falls back to regex for minimal fields.
    """
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    # Try tomllib (3.11+) or tomli
    data: dict | None = None
    try:
        import tomllib  # type: ignore

        with pyproject.open("rb") as f:
            data = tomllib.load(f)
    except ModuleNotFoundError:
        try:
            import tomli  # type: ignore

            with pyproject.open("rb") as f:
                data = tomli.load(f)
        except ModuleNotFoundError:
            data = None
    except Exception:
        data = None

    if data is not None:
        tool = data.get("tool", {}).get("blender-addons", {})
        suite_id = str(tool.get("suite_id", "blender_addon_suite"))
        blender_target = str(tool.get("blender_target", "4.2"))
        ext_defaults = tool.get("extension_defaults", {})
        if not isinstance(ext_defaults, dict):
            raise SystemExit("pyproject.toml [tool.blender-addons.extension_defaults] must be a table")
        return suite_id, blender_target, ext_defaults

    # Fallback: regex extraction for the limited keys we need.
    def _extract_string(key: str) -> str | None:
        m = re.search(rf'{re.escape(key)}\s*=\s*"([^"]*)"', text)
        return m.group(1) if m else None

    def _extract_license() -> list[str] | None:
        m = re.search(r'license\s*=\s*\[(.*?)\]', text, flags=re.DOTALL)
        if not m:
            return None
        inner = m.group(1)
        return re.findall(r'"([^"]*)"', inner)

    suite_id = _extract_string("suite_id") or "blender_addon_suite"
    blender_target = _extract_string("blender_target") or "4.2"
    # maintainer is inside [tool.blender-addons.extension_defaults]
    maint = None
    # Find the extension_defaults section block
    sec = re.search(
        r"\[tool\.blender-addons\.extension_defaults\](.*?)(?:\n\[|\Z)", text, flags=re.DOTALL
    )
    if sec:
        block = sec.group(1)
        m2 = re.search(r'maintainer\s*=\s*"([^"]*)"', block)
        if m2:
            maint = m2.group(1)
        lic = _extract_license()
        # _extract_license searches whole file; ensure it's inside this block by re-searching block
        lm = re.search(r'license\s*=\s*\[(.*?)\]', block, flags=re.DOTALL)
        lic_block = re.findall(r'"([^"]*)"', lm.group(1)) if lm else None
        ext_defaults: dict = {}
        if maint:
            ext_defaults["maintainer"] = maint
        if lic_block:
            ext_defaults["license"] = lic_block
        elif lic:
            ext_defaults["license"] = lic
        if not ext_defaults:
            ext_defaults = {"maintainer": "Mushus", "license": ["SPDX:GPL-3.0-or-later"]}
        return suite_id, blender_target, ext_defaults

    return suite_id, blender_target, {"maintainer": "Mushus", "license": ["SPDX:GPL-3.0-or-later"]}


def _load_package_file(pkg_dir: Path) -> dict:
    path = pkg_dir / PACKAGE_JSON_NAME
    if not path.exists():
        # Back-compat: also accept package.json
        alt = pkg_dir / "package.json"
        if alt.exists():
            path = alt
        else:
            raise SystemExit(f"Missing {PACKAGE_JSON_NAME} in {pkg_dir} (expected {path})")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"Invalid JSON in {path}: {e}") from e
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must be a JSON object")
    return data


def load_catalog(root: Path = ROOT) -> dict:
    """Build catalog dict compatible with old release/packages.json shape."""
    suite_id, blender_target, extension_defaults = _load_pyproject_defaults(root)

    addons_root = root / "addons"
    if not addons_root.is_dir():
        raise SystemExit(f"Missing addons directory: {addons_root}")

    packages: list[dict] = []
    for entry in sorted(addons_root.iterdir()):
        if not entry.is_dir():
            continue
        # Skip non-addon dirs (e.g., __pycache__)
        pkg_json = entry / PACKAGE_JSON_NAME
        alt_json = entry / "package.json"
        if not pkg_json.exists() and not alt_json.exists():
            continue
        data = _load_package_file(entry)
        pkg_id = str(data.get("id") or entry.name)
        # Validate required fields
        status = str(data.get("status") or "stable")
        group_id = data.get("group_id")
        group_label = data.get("group_label")
        extension = data.get("extension")
        if not isinstance(extension, dict):
            raise SystemExit(f"{pkg_id}: missing extension metadata in {entry / PACKAGE_JSON_NAME}")
        # Build package entry matching old catalog shape
        pkg: dict = {
            "id": pkg_id,
            "source": f"addons/{entry.name}",
            "status": status,
            "group_id": group_id,
            "group_label": group_label,
            "extension": extension,
        }
        # Preserve optional per-package overrides if present
        if "blender_target" in data:
            pkg["blender_target"] = data["blender_target"]
        if "maintainer" in data or "license" in data:
            # Allow per-package extension_defaults override via top-level keys (rare)
            pass
        # Keep any extra keys that might be used elsewhere (e.g., custom fields)
        for k in ("tags", "tagline", "permissions"):
            if k in data:
                pkg[k] = data[k]
        packages.append(pkg)

    if not packages:
        raise SystemExit(f"No packages found in {addons_root} (expected {PACKAGE_JSON_NAME} per addon)")

    # Sort by id for determinism (old file was ordered)
    packages.sort(key=lambda p: p["id"])

    return {
        "suite_id": suite_id,
        "blender_target": blender_target,
        "extension_defaults": extension_defaults,
        "packages": packages,
    }


def load_stable_packages(catalog: dict, package_ids: list[str] | None = None) -> list[dict]:
    selected = [
        p for p in catalog.get("packages", []) if p.get("status") == "stable" and (not package_ids or p["id"] in package_ids)
    ]
    if not selected:
        raise SystemExit("No stable packages selected.")
    return selected

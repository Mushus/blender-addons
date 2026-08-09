"""Build Blender extension manifests (blender_manifest.toml) from bl_info + catalog."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

_TAGLINE_TRAILING_PUNCT = re.compile(r"[.!?。]+$")


def parse_bl_info(init_path: Path) -> dict[str, Any]:
    content = init_path.read_text(encoding="utf-8")
    match = re.search(r"bl_info\s*=\s*\{(.*?)\n\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError(f"bl_info not found in {init_path}")
    body = match.group(1)

    def string_field(key: str) -> str:
        found = re.search(rf'"{key}"\s*:\s*"([^"]*)"', body)
        if not found:
            raise ValueError(f'bl_info["{key}"] not found in {init_path}')
        return found.group(1)

    def tuple_field(key: str) -> tuple[int, ...]:
        found = re.search(rf'"{key}"\s*:\s*\(([^)]*)\)', body)
        if not found:
            raise ValueError(f'bl_info["{key}"] not found in {init_path}')
        parts = [int(part.strip()) for part in found.group(1).split(",") if part.strip()]
        if not parts:
            raise ValueError(f'bl_info["{key}"] is empty in {init_path}')
        return tuple(parts)

    return {
        "name": string_field("name"),
        "description": string_field("description"),
        "version": tuple_field("version"),
        "blender": tuple_field("blender"),
        "author": string_field("author"),
    }


def format_semver(version: tuple[int, ...]) -> str:
    """SemVer numeric identifiers must not include leading zeros."""
    if len(version) != 3:
        raise ValueError(f"extension version must be 3-part, got {version}")
    return ".".join(str(part) for part in version)


def format_blender_version(version: tuple[int, ...]) -> str:
    if len(version) < 2:
        raise ValueError(f"blender version too short: {version}")
    major, minor = version[0], version[1]
    patch = version[2] if len(version) > 2 else 0
    # Extensions Platform requires Blender 4.2+.
    if (major, minor, patch) < (4, 2, 0):
        return "4.2.0"
    return f"{major}.{minor}.{patch}"


def tagline_from_description(description: str) -> str:
    text = description.strip()
    text = _TAGLINE_TRAILING_PUNCT.sub("", text).strip()
    if not text:
        raise ValueError("extension tagline is empty")
    if len(text) > 64:
        raise ValueError(f"extension tagline exceeds 64 chars: {text!r}")
    return text


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_string_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(v) for v in values) + "]"


def build_manifest_dict(
    *,
    package_id: str,
    bl_info: dict[str, Any],
    extension_meta: dict[str, Any],
    defaults: dict[str, Any],
    website: str | None,
) -> dict[str, Any]:
    maintainer = str(extension_meta.get("maintainer") or defaults.get("maintainer") or bl_info["author"])
    license_values = extension_meta.get("license") or defaults.get("license")
    if not isinstance(license_values, list) or not license_values:
        raise ValueError(f"{package_id}: extension license must be a non-empty list")
    tags = extension_meta.get("tags")
    if not isinstance(tags, list) or not tags:
        raise ValueError(f"{package_id}: extension.tags must be a non-empty list")
    permissions = extension_meta.get("permissions")
    if permissions is not None and not isinstance(permissions, dict):
        raise ValueError(f"{package_id}: extension.permissions must be a table")

    if extension_meta.get("tagline"):
        tagline = tagline_from_description(str(extension_meta["tagline"]))
    else:
        tagline = tagline_from_description(bl_info["description"])

    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "id": package_id,
        "version": format_semver(bl_info["version"]),
        "name": bl_info["name"],
        "tagline": tagline,
        "maintainer": maintainer,
        "type": "add-on",
        "license": [str(item) for item in license_values],
        "blender_version_min": format_blender_version(bl_info["blender"]),
        "tags": [str(tag) for tag in tags],
    }
    if website:
        manifest["website"] = website
    if permissions:
        cleaned: dict[str, str] = {}
        for key, reason in permissions.items():
            text = str(reason).strip()
            text = _TAGLINE_TRAILING_PUNCT.sub("", text).strip()
            if not text:
                raise ValueError(f"{package_id}: empty permission reason for {key}")
            if len(text) > 64:
                raise ValueError(f"{package_id}: permission reason exceeds 64 chars for {key}")
            cleaned[str(key)] = text
        manifest["permissions"] = cleaned
    return manifest


def render_manifest_toml(manifest: dict[str, Any]) -> str:
    lines = [
        f"schema_version = {_toml_string(manifest['schema_version'])}",
        f"id = {_toml_string(manifest['id'])}",
        f"version = {_toml_string(manifest['version'])}",
        f"name = {_toml_string(manifest['name'])}",
        f"tagline = {_toml_string(manifest['tagline'])}",
        f"maintainer = {_toml_string(manifest['maintainer'])}",
        f"type = {_toml_string(manifest['type'])}",
        f"license = {_toml_string_array(manifest['license'])}",
        f"blender_version_min = {_toml_string(manifest['blender_version_min'])}",
        f"tags = {_toml_string_array(manifest['tags'])}",
    ]
    if website := manifest.get("website"):
        lines.append(f"website = {_toml_string(website)}")
    lines.append("")
    permissions = manifest.get("permissions")
    if permissions:
        lines.append("[permissions]")
        for key in sorted(permissions):
            lines.append(f"{key} = {_toml_string(permissions[key])}")
        lines.append("")
    return "\n".join(lines)


def write_manifest(package_dir: Path, manifest: dict[str, Any]) -> Path:
    path = package_dir / "blender_manifest.toml"
    path.write_text(render_manifest_toml(manifest), encoding="utf-8", newline="\n")
    return path


def package_website(package_id: str, *, site_origin: str = "https://mushus.github.io/blender-addons") -> str:
    return f"{site_origin.rstrip('/')}/addons/{package_id.replace('_', '-')}/"


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, f"sha256:{digest.hexdigest()}"


def index_entry_from_manifest(
    manifest: dict[str, Any],
    *,
    archive_url: str,
    archive_size: int,
    archive_hash: str,
) -> dict[str, Any]:
    entry = {
        "schema_version": manifest["schema_version"],
        "id": manifest["id"],
        "name": manifest["name"],
        "tagline": manifest["tagline"],
        "version": manifest["version"],
        "type": manifest["type"],
        "maintainer": manifest["maintainer"],
        "license": list(manifest["license"]),
        "blender_version_min": manifest["blender_version_min"],
        "tags": list(manifest["tags"]),
        "archive_url": archive_url,
        "archive_size": archive_size,
        "archive_hash": archive_hash,
    }
    if website := manifest.get("website"):
        entry["website"] = website
    if permissions := manifest.get("permissions"):
        entry["permissions"] = dict(permissions)
    return entry

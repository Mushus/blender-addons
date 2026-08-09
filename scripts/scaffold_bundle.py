"""Vendor scaffold modules into an add-on package and rewrite imports.

Repo sources import ``scaffold.embedded_host``. Solo / suite ZIPs must be
self-contained, so packaging copies the tree to ``<package>/embedded_host``
and rewrites imports to package-relative forms that honor ``__package__``
(including ``blender_addon_suite.addons.<tool>``).

Rewrites are textual (prefix substitution) so comments and formatting stay intact.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

SCAFFOLD_HOST_IMPORT = "scaffold.embedded_host"
VENDOR_HOST_NAME = "embedded_host"

_FROM_IMPORT_RE = re.compile(
    r"^(\s*)from\s+scaffold\.embedded_host((?:\.[\w]+)*)\s+import\s+",
    re.MULTILINE,
)
_BARE_IMPORT_RE = re.compile(
    r"^(\s*)import\s+scaffold\.embedded_host((?:\.[\w]+)*)\s*(#.*)?$",
    re.MULTILINE,
)


def package_uses_scaffold_host(source_dir: Path) -> bool:
    for path in source_dir.rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if SCAFFOLD_HOST_IMPORT in text:
            return True
    return False


def vendor_embedded_host(package_dir: Path, scaffold_root: Path) -> None:
    """Copy canonical host into ``package_dir/embedded_host``."""
    src = scaffold_root / "embedded_host"
    if not src.is_dir():
        raise FileNotFoundError(f"Missing scaffold host: {src}")
    dest = package_dir / VENDOR_HOST_NAME
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db"),
    )


def _relative_level(package_dir: Path, file_path: Path) -> int:
    rel_parent = file_path.parent.relative_to(package_dir)
    return 1 + len(rel_parent.parts)


def rewrite_scaffold_imports(source: str, *, package_dir: Path, file_path: Path) -> str:
    """Rewrite scaffold.embedded_host imports/strings for a vendored package."""
    if SCAFFOLD_HOST_IMPORT not in source:
        return source

    level = _relative_level(package_dir, file_path)
    dots = "." * level

    def repl_from(match: re.Match[str]) -> str:
        return f"{match.group(1)}from {dots}{VENDOR_HOST_NAME}{match.group(2)} import "

    def repl_import(match: re.Match[str]) -> str:
        suffix = match.group(2) or ""
        comment = match.group(3) or ""
        parts = [p for p in suffix.split(".") if p]
        if not parts:
            return f"{match.group(1)}from {dots} import {VENDOR_HOST_NAME}{comment}"
        if len(parts) == 1:
            return f"{match.group(1)}from {dots}{VENDOR_HOST_NAME} import {parts[0]}{comment}"
        parent = VENDOR_HOST_NAME + "." + ".".join(parts[:-1])
        return f"{match.group(1)}from {dots}{parent} import {parts[-1]}{comment}"

    text = _FROM_IMPORT_RE.sub(repl_from, source)
    text = _BARE_IMPORT_RE.sub(repl_import, text)

    # String literals used by _qualname / import_module (longest prefix first).
    for quote in ("'", '"'):
        text = text.replace(
            f"{quote}{SCAFFOLD_HOST_IMPORT}.",
            f"{quote}{VENDOR_HOST_NAME}.",
        )
        text = text.replace(
            f"{quote}{SCAFFOLD_HOST_IMPORT}{quote}",
            f"{quote}{VENDOR_HOST_NAME}{quote}",
        )

    if SCAFFOLD_HOST_IMPORT in text:
        raise RuntimeError(
            f"Unresolved {SCAFFOLD_HOST_IMPORT!r} after rewrite in {file_path}"
        )
    return text


def rewrite_package_tree(package_dir: Path) -> list[Path]:
    """Rewrite all non-test Python files under package_dir. Returns changed paths."""
    changed: list[Path] = []
    for path in sorted(package_dir.rglob("*.py")):
        rel_parts = path.relative_to(package_dir).parts
        if "tests" in rel_parts:
            continue
        if rel_parts and rel_parts[0] == VENDOR_HOST_NAME:
            continue
        original = path.read_text(encoding="utf-8")
        if SCAFFOLD_HOST_IMPORT not in original:
            continue
        updated = rewrite_scaffold_imports(original, package_dir=package_dir, file_path=path)
        if updated != original:
            path.write_text(updated, encoding="utf-8", newline="\n")
            changed.append(path)
    return changed


def bundle_scaffold_into_package(package_dir: Path, scaffold_root: Path) -> bool:
    """Vendor + rewrite when the package sources reference scaffold.embedded_host.

    Returns True when bundling ran.
    """
    if not package_uses_scaffold_host(package_dir):
        return False
    vendor_embedded_host(package_dir, scaffold_root)
    rewrite_package_tree(package_dir)
    return True

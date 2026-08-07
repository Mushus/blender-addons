from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

SKIP_DIR_NAMES = frozenset({"__pycache__", ".git"})
SKIP_FILE_NAMES = frozenset({".DS_Store", "Thumbs.db"})
SKIP_SUFFIXES = frozenset({".pyc", ".pyo"})


def should_skip(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    if path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False


def iter_files(root: Path) -> Iterator[Path]:
    """Yield files under root, skipping build junk."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or should_skip(path.relative_to(root)):
            continue
        yield path


def archive_names(archive_path: Path) -> set[str]:
    with zipfile.ZipFile(archive_path) as archive:
        return {
            name.replace("\\", "/")
            for name in archive.namelist()
            if name and not name.endswith("/")
        }


def extract_zip(archive_path: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            relative_name = entry.filename.replace("\\", "/")
            target = (root / relative_name).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe ZIP entry: {entry.filename}")
            if entry.is_dir() or relative_name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))

from __future__ import annotations

import zipfile
from pathlib import Path


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

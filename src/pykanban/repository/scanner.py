from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanResult:
    """Result of scanning a project folder."""

    changed_paths: list[Path]
    deleted_paths: list[Path]
    conflict_paths: list[Path]
    mtime_cache: dict[Path, float]


def scan_project_folder(
    project_folder: Path, mtime_cache: dict[Path, float]
) -> ScanResult:
    """Scan a project folder and detect changes."""
    previous = mtime_cache or {}
    current: dict[Path, float] = {}
    changed: list[Path] = []

    for path in project_folder.rglob("*.md"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        current[path] = mtime
        if previous.get(path) != mtime:
            changed.append(path)

    deleted = [path for path in previous if path not in current]
    conflict = list(project_folder.rglob(".sync-conflict-*"))

    return ScanResult(
        changed_paths=changed,
        deleted_paths=deleted,
        conflict_paths=conflict,
        mtime_cache=current,
    )

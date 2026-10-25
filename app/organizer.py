"""Filesystem operations. Never deletes, never overwrites, never leaves the watched root."""
from __future__ import annotations

import shutil
from pathlib import Path

from .llm import CATEGORIES


class UnsafePathError(ValueError):
    pass


def safe_join(root: Path, rel: str) -> Path:
    """Join rel onto root and make sure the result stays inside root."""
    root_r = root.resolve()
    target = (root_r / rel)
    if target.is_symlink():
        raise UnsafePathError(f"refusing to touch symlink: {rel}")
    resolved = target.resolve()
    if resolved != root_r and root_r not in resolved.parents:
        raise UnsafePathError(f"path escapes the watched folder: {rel}")
    return resolved


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for i in range(1, 10_000):
        candidate = path.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not find a free name for {path.name}")


def plan_destination(category: str, clean_name: str, ext: str) -> str:
    if category not in CATEGORIES:
        raise UnsafePathError(f"unknown category: {category}")
    return f"{category}/{clean_name}{ext.lower()}"


def apply_move(root: Path, src_rel: str, dst_rel: str) -> str:
    src = safe_join(root, src_rel)
    if not src.is_file():
        raise FileNotFoundError(src_rel)
    dst = unique_path(safe_join(root, dst_rel))
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return dst.relative_to(root.resolve()).as_posix()


def undo_move(root: Path, src_rel: str, dst_rel: str) -> str:
    current = safe_join(root, dst_rel)
    if not current.is_file():
        raise FileNotFoundError(dst_rel)
    original = unique_path(safe_join(root, src_rel))
    shutil.move(str(current), str(original))
    return original.relative_to(root.resolve()).as_posix()

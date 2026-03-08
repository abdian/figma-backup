"""
Utility helpers -- shared functions used across all modules.
"""

import json
from pathlib import Path


def safe_name(name: str) -> str:
    """Sanitize a string for safe use as a directory or file name.

    Replaces any character that isn't alphanumeric, space, dash, or
    underscore with an underscore.
    """
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()


def human_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable string (e.g. '4.2 MB')."""
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


def save_json(path: Path, data: dict):
    """Write a dict as pretty-printed JSON to the given path.

    Creates parent directories if they don't exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dir_size(path: Path) -> int:
    """Calculate total size of all files in a directory tree (bytes)."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0

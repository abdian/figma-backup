"""
Resume module -- manifest-based state persistence for crash-safe backups.

Every backup directory contains a .backup_manifest.json file that tracks
the status of each downloadable item. On restart, incomplete backups can
be detected and resumed from where they stopped.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

from figma_backup.models import BackupItemStatus

logger = logging.getLogger(__name__)
MANIFEST_FILENAME = ".backup_manifest.json"


class ResumeManager:
    """Manages backup state persistence for resume capability.

    The manifest is saved to disk after every status change,
    making it crash-safe -- at most one item's state is lost.
    """

    def __init__(self, backup_root: Path):
        self.backup_root = backup_root
        self.manifest_path = backup_root / MANIFEST_FILENAME
        self.manifest: Optional[Dict] = None

    def has_incomplete_backup(self) -> bool:
        """Check if an incomplete manifest exists in the backup directory."""
        if not self.manifest_path.exists():
            return False
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return not data.get("completed", False)
        except (json.JSONDecodeError, KeyError):
            return False

    def load_manifest(self) -> Dict:
        """Load existing manifest from disk for resuming."""
        try:
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load manifest: {e}")
            self.manifest = None
        return self.manifest

    def create_manifest(self, backup_id: str) -> Dict:
        """Create a fresh manifest for a new backup session."""
        self.manifest = {
            "backup_id": backup_id,
            "started_at": datetime.now().isoformat(),
            "backup_root": str(self.backup_root),
            "items": [],
            "completed": False,
            "stats": {
                "files": 0, "comments": 0, "versions": 0,
                "components": 0, "component_sets": 0, "styles": 0,
                "image_exports": 0, "image_fills": 0, "thumbnails": 0,
                "errors": 0,
            },
        }
        self.save()
        return self.manifest

    def save(self):
        """Persist current manifest state to disk."""
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=2, default=str),
            encoding="utf-8",
        )

    def register_item(self, item_type: str, file_key: str):
        """Add an item to the manifest for tracking (skips duplicates)."""
        for item in self.manifest["items"]:
            if item["item_type"] == item_type and item["file_key"] == file_key:
                return
        self.manifest["items"].append({
            "item_type": item_type,
            "file_key": file_key,
            "status": BackupItemStatus.PENDING.value,
            "output_path": None,
            "error_message": None,
            "size_bytes": 0,
        })

    def mark_item(self, item_type: str, file_key: str, status: BackupItemStatus,
                  output_path: str = None, size_bytes: int = 0, error: str = None):
        """Update the status of a tracked item and save to disk."""
        for item in self.manifest["items"]:
            if item["item_type"] == item_type and item["file_key"] == file_key:
                item["status"] = status.value
                if output_path:
                    item["output_path"] = output_path
                if size_bytes:
                    item["size_bytes"] = size_bytes
                if error:
                    item["error_message"] = error
                break
        self.save()

    def get_pending_items(self) -> List[Dict]:
        """Return all items that still need to be processed."""
        return [
            item for item in self.manifest["items"]
            if item["status"] in (BackupItemStatus.PENDING.value, BackupItemStatus.FAILED.value)
        ]

    def mark_completed(self):
        """Mark the entire backup as completed."""
        self.manifest["completed"] = True
        self.save()

    def is_item_done(self, item_type: str, file_key: str) -> bool:
        """Check if a specific item has already been backed up successfully."""
        for item in self.manifest["items"]:
            if (item["item_type"] == item_type and
                item["file_key"] == file_key and
                item["status"] in (BackupItemStatus.COMPLETED.value, BackupItemStatus.SKIPPED.value)):
                return True
        return False

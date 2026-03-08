"""
Data models -- typed structures used across the codebase.
All dataclasses and enums for representing Figma entities and backup state.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class BackupItemStatus(Enum):
    """Status of a single backup item in the manifest."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExportFormat(Enum):
    """Supported image export formats."""
    PNG = "png"
    SVG = "svg"
    PDF = "pdf"


class ApiTier(Enum):
    """Figma API rate limit tiers.

    Each tier has different request limits:
      Tier 1 (10-20 req/min): files, images, versions
      Tier 2 (25-100 req/min): teams, projects, comments
      Tier 3 (50-150 req/min): components, component_sets, styles
    """
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


@dataclass
class FigmaTeam:
    """Represents a Figma team containing projects."""
    id: str
    name: str
    projects: List["FigmaProject"] = field(default_factory=list)


@dataclass
class FigmaProject:
    """Represents a Figma project containing files."""
    id: str
    name: str
    team_id: str
    files: List["FigmaFile"] = field(default_factory=list)


@dataclass
class FigmaFile:
    """Represents a single Figma file within a project."""
    key: str
    name: str
    project_id: str
    last_modified: Optional[str] = None
    thumbnail_url: Optional[str] = None


@dataclass
class BackupItem:
    """Tracks the backup status of a single downloadable resource."""
    item_type: str          # "file_data", "comments", "versions", etc.
    file_key: str           # Figma file key this item belongs to
    status: BackupItemStatus = BackupItemStatus.PENDING
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    size_bytes: int = 0


@dataclass
class BackupManifest:
    """Root state object persisted to disk for resume capability."""
    backup_id: str
    started_at: str
    backup_root: str
    teams: List[Dict] = field(default_factory=list)
    items: List[Dict] = field(default_factory=list)
    completed: bool = False
    stats: Dict[str, int] = field(default_factory=lambda: {
        "files": 0, "comments": 0, "versions": 0,
        "components": 0, "component_sets": 0, "styles": 0,
        "image_exports": 0, "image_fills": 0, "thumbnails": 0,
        "errors": 0,
    })

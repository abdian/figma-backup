"""
Configuration module -- loads settings from .env, environment variables,
and CLI arguments with a defined priority chain.

Priority: CLI args > environment variables > .env file > defaults
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv, find_dotenv


@dataclass
class BackupConfig:
    """All configurable options for the backup process."""
    figma_token: str = ""
    team_ids: List[str] = field(default_factory=list)
    output_dir: str = "figma_backup_output"
    export_formats: List[str] = field(default_factory=lambda: ["png"])
    export_scale: float = 2.0
    include_versions: bool = True
    include_comments: bool = True
    include_components: bool = True
    include_component_sets: bool = True
    include_styles: bool = True
    include_image_fills: bool = True
    include_image_exports: bool = False   # opt-in: can be slow for large files
    compress: bool = False
    interactive: bool = False
    resume: bool = True
    log_file: Optional[str] = None


def load_config(
    token: Optional[str] = None,
    team_ids: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    **cli_overrides,
) -> BackupConfig:
    """Load configuration with priority: CLI args > env vars > .env > defaults."""
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)

    config = BackupConfig()

    # Load from .env / environment variables
    config.figma_token = os.getenv("FIGMA_TOKEN", "")
    env_teams = os.getenv("FIGMA_TEAM_IDS", "")
    if env_teams:
        config.team_ids = [t.strip() for t in env_teams.split(",") if t.strip()]
    config.output_dir = os.getenv("FIGMA_OUTPUT_DIR", config.output_dir)

    # CLI overrides take highest priority
    if token:
        config.figma_token = token
    if team_ids:
        config.team_ids = list(team_ids)
    if output_dir:
        config.output_dir = output_dir

    for key, value in cli_overrides.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)

    return config


def validate_config(config: BackupConfig) -> List[str]:
    """Validate config and return list of error messages. Empty = valid.

    Only the token is required. Team IDs are optional -- if missing,
    the user will be prompted to enter them interactively.
    """
    errors = []
    if not config.figma_token:
        errors.append("FIGMA_TOKEN is required. Set it in .env or pass --token.")
    return errors

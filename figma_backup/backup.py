"""
Backup orchestrator -- coordinates the entire backup pipeline.
Iterates through teams/projects/files, calls the API for each data type,
tracks state via ResumeManager, and displays progress.
"""

import json
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from figma_backup.api import FigmaApiClient
from figma_backup.config import BackupConfig
from figma_backup.models import FigmaTeam, FigmaFile, BackupItemStatus
from figma_backup.resume import ResumeManager
from figma_backup.exporter import export_images, download_image_fills
from rich.prompt import Confirm
from figma_backup.display import (
    console, show_success, show_warning, show_error, show_summary_table,
    confirm_resume, create_backup_progress,
)
from figma_backup.utils import safe_name, save_json, human_size

logger = logging.getLogger(__name__)


def _setup_file_logging(backup_root: Path):
    """Add a file handler so detailed errors go to backup.log instead of console."""
    backup_root.mkdir(parents=True, exist_ok=True)
    log_path = backup_root / "backup.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logging.getLogger().addHandler(file_handler)
    return log_path

def _find_previous_backup(output_dir: Path) -> Optional[Path]:
    """Find the most recent completed backup directory."""
    if not output_dir.exists():
        return None
    for subdir in sorted(output_dir.iterdir(), reverse=True):
        if subdir.is_dir():
            manifest_path = subdir / ".backup_manifest.json"
            if manifest_path.exists():
                try:
                    data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if data.get("completed"):
                        return subdir
                except (json.JSONDecodeError, KeyError):
                    pass
    return None


def _build_previous_index(prev_backup: Path) -> Dict[str, Dict]:
    """Build an index of {file_key: {last_modified, dir_path}} from a previous backup.

    Walks the backup tree looking for file_data.json files, extracts the
    file key and last_modified date from each one. Uses _backup_file_key
    (saved by us) or falls back to manifest items.
    """
    index = {}
    teams_dir = prev_backup / "teams"
    if not teams_dir.exists():
        return index

    # Method 1: Read file_data.json files for _backup_file_key
    for file_data_path in teams_dir.rglob("file_data.json"):
        try:
            data = json.loads(file_data_path.read_text(encoding="utf-8"))
            key = data.get("_backup_file_key", "")
            last_mod = data.get("lastModified", "")
            if key and last_mod:
                index[key] = {
                    "last_modified": last_mod,
                    "dir": str(file_data_path.parent),
                }
        except (json.JSONDecodeError, KeyError):
            pass

    # Method 2: If no keys found, try manifest items
    if not index:
        manifest_path = prev_backup / ".backup_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for item in manifest.get("items", []):
                    if item.get("item_type") == "file_data" and item.get("status") == "completed":
                        key = item["file_key"]
                        output_path = item.get("output_path", "")
                        if output_path:
                            dir_path = str(Path(output_path).parent)
                            index[key] = {"last_modified": "", "dir": dir_path}
            except (json.JSONDecodeError, KeyError):
                pass

    return index


# All data types that can be backed up per file
ITEM_TYPES = [
    "file_data", "comments", "versions", "components",
    "component_sets", "styles", "thumbnail",
    "image_fills", "image_exports",
]


class BackupOrchestrator:
    """Main backup engine that coordinates the full backup pipeline."""

    def __init__(self, config: BackupConfig, client: FigmaApiClient):
        self.config = config
        self.client = client
        self.start_time = time.time()
        self.total_bytes = 0
        self.error_count = 0
        self.log_path = None
        self.prev_index: Dict[str, Dict] = {}
        self.skipped_unchanged = 0

    def run(self, teams: List[FigmaTeam]):
        """Execute the backup for all selected teams.

        Steps:
        1. Check for incomplete previous backup (resume support)
        2. Register all items to be backed up in the manifest
        3. Iterate through files and download each data type
        4. Fetch team-level data (components, styles)
        5. Optionally compress the backup
        6. Show summary
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        backup_root = Path(self.config.output_dir) / timestamp
        resume_mgr = ResumeManager(backup_root)

        # Check for incomplete previous backup in the output directory
        parent = Path(self.config.output_dir)
        resumed = False
        if self.config.resume and parent.exists():
            for subdir in sorted(parent.iterdir(), reverse=True):
                if subdir.is_dir():
                    check_mgr = ResumeManager(subdir)
                    if check_mgr.has_incomplete_backup():
                        if confirm_resume(str(subdir)):
                            backup_root = subdir
                            resume_mgr = check_mgr
                            resume_mgr.load_manifest()
                            if resume_mgr.manifest:
                                resumed = True
                                console.print("  [cyan]Resuming previous backup...[/cyan]")
                            else:
                                console.print("  [yellow]Manifest corrupted, starting fresh...[/yellow]")
                        break

        if not resumed:
            resume_mgr = ResumeManager(backup_root)
            resume_mgr.create_manifest(backup_id=timestamp)

        # Set up file logging so detailed errors go to backup.log
        self.log_path = _setup_file_logging(backup_root)

        # Build index from previous backup for incremental mode
        if not resumed:
            prev_backup = _find_previous_backup(Path(self.config.output_dir))
            if prev_backup and prev_backup != backup_root:
                self.prev_index = _build_previous_index(prev_backup)
                if self.prev_index:
                    console.print(f"  [dim]Found previous backup with {len(self.prev_index)} files for comparison[/dim]")

        # Pre-register every item that needs backing up
        self._register_all_items(resume_mgr, teams)

        total_items = len(resume_mgr.manifest["items"])
        pending_items = len(resume_mgr.get_pending_items())

        if pending_items == 0:
            show_success("All items already backed up!")
            resume_mgr.mark_completed()
            elapsed = time.time() - self.start_time
            show_summary_table(resume_mgr.manifest["stats"], str(backup_root.resolve()), elapsed, self.total_bytes)
            return

        console.print(f"\n  [dim]{pending_items} of {total_items} items to process[/dim]\n")

        # Main backup loop with progress bar
        with create_backup_progress() as progress:
            overall = progress.add_task(
                "[cyan]Overall progress", total=pending_items,
                downloaded="0 B",
            )

            for team in teams:
                team_dir = backup_root / "teams" / safe_name(team.name)
                save_json(team_dir / "team_info.json", {"id": team.id, "name": team.name})

                for project in team.projects:
                    project_dir = team_dir / safe_name(project.name)
                    save_json(project_dir / "project_info.json", {
                        "id": project.id, "name": project.name,
                    })

                    for file in project.files:
                        file_dir = project_dir / safe_name(file.name)
                        self._backup_single_file(
                            file, file_dir, resume_mgr, progress, overall,
                        )

            # Fetch team-level library data (components, styles)
            for team in teams:
                team_dir = backup_root / "teams" / safe_name(team.name)
                self._backup_team_level_data(team, team_dir, resume_mgr)

        # -- Final verification --
        failed_items = [
            item for item in resume_mgr.manifest["items"]
            if item["status"] == BackupItemStatus.FAILED.value
        ]

        if failed_items:
            show_warning(f"{len(failed_items)} item(s) failed. Retrying...")
            # Reset failed items to pending and retry
            for item in failed_items:
                item["status"] = BackupItemStatus.PENDING.value
            resume_mgr.save()
            self.error_count = 0

            with create_backup_progress() as progress:
                retry_task = progress.add_task(
                    "[yellow]Retrying failed items", total=len(failed_items),
                    downloaded=human_size(self.total_bytes),
                )
                for team in teams:
                    for project in team.projects:
                        for file in project.files:
                            # Only retry files that had failures
                            has_failed = any(
                                i for i in failed_items if i["file_key"] == file.key
                            )
                            if has_failed:
                                file_dir = backup_root / "teams" / safe_name(team.name) / safe_name(project.name) / safe_name(file.name)
                                self._backup_single_file(
                                    file, file_dir, resume_mgr, progress, retry_task,
                                )

        # Final status check
        still_failed = [
            item for item in resume_mgr.manifest["items"]
            if item["status"] == BackupItemStatus.FAILED.value
        ]

        resume_mgr.mark_completed()
        elapsed = time.time() - self.start_time

        if self.config.compress:
            self._compress_backup(backup_root)

        if self.skipped_unchanged > 0:
            resume_mgr.manifest["stats"]["unchanged (copied)"] = self.skipped_unchanged

        show_summary_table(resume_mgr.manifest["stats"], str(backup_root.resolve()), elapsed, self.total_bytes)

        if still_failed:
            show_warning(f"{len(still_failed)} item(s) still failed after retry. See: {self.log_path}")
            console.print("  [dim]Tip: Run the tool again to retry failed items (resume mode)[/dim]")
        else:
            show_success("Backup completed successfully! All items verified.")

    def _add_bytes(self, progress, task_id, size: int):
        """Add downloaded bytes to the running total and update progress display."""
        self.total_bytes += size
        progress.update(task_id, downloaded=human_size(self.total_bytes))

    def _log_error(self, item_type: str, file_name: str, file_key: str, error: Exception):
        """Log full error to file, keep console clean."""
        logger.error(f"{item_type} [{file_name}] ({file_key}): {error}")
        self.error_count += 1

    def _register_all_items(self, resume_mgr: ResumeManager, teams: List[FigmaTeam]):
        """Pre-register every downloadable item into the manifest for tracking."""
        for team in teams:
            for project in team.projects:
                for file in project.files:
                    for item_type in ITEM_TYPES:
                        # Skip disabled data types based on config
                        if item_type == "comments" and not self.config.include_comments:
                            continue
                        if item_type == "versions" and not self.config.include_versions:
                            continue
                        if item_type == "components" and not self.config.include_components:
                            continue
                        if item_type == "component_sets" and not self.config.include_component_sets:
                            continue
                        if item_type == "styles" and not self.config.include_styles:
                            continue
                        if item_type == "image_fills" and not self.config.include_image_fills:
                            continue
                        if item_type == "image_exports" and not self.config.include_image_exports:
                            continue

                        if not resume_mgr.is_item_done(item_type, file.key):
                            resume_mgr.register_item(item_type, file.key)
        resume_mgr.save()

    def _backup_single_file(self, file: FigmaFile, file_dir: Path,
                            resume_mgr: ResumeManager, progress, task_id):
        """Back up all data types for a single Figma file.

        Each data type is checked against the manifest before downloading.
        On success, the item is marked COMPLETED; on failure, FAILED.
        Progress bar is advanced after each item regardless of outcome.
        """
        file_dir.mkdir(parents=True, exist_ok=True)
        file_data = None

        # -- Incremental: copy from previous backup if file hasn't changed --
        if self.prev_index and file.key in self.prev_index:
            prev_info = self.prev_index[file.key]
            if file.last_modified and prev_info["last_modified"] == file.last_modified:
                prev_dir = Path(prev_info["dir"])
                if prev_dir.exists():
                    # Copy all files from previous backup
                    copied_size = 0
                    for src_file in prev_dir.iterdir():
                        if src_file.is_file():
                            dst = file_dir / src_file.name
                            shutil.copy2(str(src_file), str(dst))
                            copied_size += src_file.stat().st_size
                    # Copy subdirectories (image_fills, exports)
                    for src_sub in prev_dir.iterdir():
                        if src_sub.is_dir():
                            dst_sub = file_dir / src_sub.name
                            if dst_sub.exists():
                                shutil.rmtree(str(dst_sub))
                            shutil.copytree(str(src_sub), str(dst_sub))
                            for f in src_sub.rglob("*"):
                                if f.is_file():
                                    copied_size += f.stat().st_size
                    # Mark all items as completed
                    for item_type in ITEM_TYPES:
                        if not resume_mgr.is_item_done(item_type, file.key):
                            resume_mgr.mark_item(item_type, file.key, BackupItemStatus.SKIPPED)
                            progress.advance(task_id)
                    self._add_bytes(progress, task_id, copied_size)
                    self.skipped_unchanged += 1
                    resume_mgr.manifest["stats"]["files"] += 1
                    logger.info(f"Unchanged, copied from previous: {file.name} ({file.key})")
                    return

        # -- File content (Tier 1) --
        if not resume_mgr.is_item_done("file_data", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - content")
            try:
                file_data = self.client.get_file(file.key)
                if file_data:
                    file_data["_backup_file_key"] = file.key
                    save_json(file_dir / "file_data.json", file_data)
                    size = (file_dir / "file_data.json").stat().st_size
                    resume_mgr.mark_item("file_data", file.key, BackupItemStatus.COMPLETED,
                                         size_bytes=size)
                    resume_mgr.manifest["stats"]["files"] += 1
                    self._add_bytes(progress, task_id, size)
            except Exception as e:
                self._log_error("file_data", file.name, file.key, e)
                resume_mgr.mark_item("file_data", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

        # -- Comments (Tier 2) --
        if self.config.include_comments and not resume_mgr.is_item_done("comments", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - comments")
            try:
                data = self.client.get_file_comments(file.key)
                if data:
                    comments = data.get("comments", [])
                    save_json(file_dir / "comments.json", data)
                    size = (file_dir / "comments.json").stat().st_size
                    resume_mgr.mark_item("comments", file.key, BackupItemStatus.COMPLETED,
                                         size_bytes=size)
                    resume_mgr.manifest["stats"]["comments"] += len(comments)
                    self._add_bytes(progress, task_id, size)
            except Exception as e:
                self._log_error("comments", file.name, file.key, e)
                resume_mgr.mark_item("comments", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

        # -- Version history (Tier 1) --
        if self.config.include_versions and not resume_mgr.is_item_done("versions", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - versions")
            try:
                data = self.client.get_file_versions(file.key)
                if data:
                    versions = data.get("versions", [])
                    save_json(file_dir / "versions.json", data)
                    size = (file_dir / "versions.json").stat().st_size
                    resume_mgr.mark_item("versions", file.key, BackupItemStatus.COMPLETED,
                                         size_bytes=size)
                    resume_mgr.manifest["stats"]["versions"] += len(versions)
                    self._add_bytes(progress, task_id, size)
            except Exception as e:
                self._log_error("versions", file.name, file.key, e)
                resume_mgr.mark_item("versions", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

        # -- Components (Tier 3) --
        if self.config.include_components and not resume_mgr.is_item_done("components", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - components")
            try:
                data = self.client.get_file_components(file.key)
                if data:
                    components = data.get("meta", {}).get("components", [])
                    save_json(file_dir / "components.json", data)
                    size = (file_dir / "components.json").stat().st_size
                    resume_mgr.mark_item("components", file.key, BackupItemStatus.COMPLETED,
                                         size_bytes=size)
                    resume_mgr.manifest["stats"]["components"] += len(components)
                    self._add_bytes(progress, task_id, size)
            except Exception as e:
                self._log_error("components", file.name, file.key, e)
                resume_mgr.mark_item("components", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

        # -- Component sets (Tier 3) --
        if self.config.include_component_sets and not resume_mgr.is_item_done("component_sets", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - component sets")
            try:
                data = self.client.get_file_component_sets(file.key)
                if data:
                    save_json(file_dir / "component_sets.json", data)
                    size = (file_dir / "component_sets.json").stat().st_size
                    resume_mgr.mark_item("component_sets", file.key, BackupItemStatus.COMPLETED,
                                         size_bytes=size)
                    resume_mgr.manifest["stats"]["component_sets"] += \
                        len(data.get("meta", {}).get("component_sets", []))
                    self._add_bytes(progress, task_id, size)
            except Exception as e:
                self._log_error("component_sets", file.name, file.key, e)
                resume_mgr.mark_item("component_sets", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

        # -- Styles (Tier 3) --
        if self.config.include_styles and not resume_mgr.is_item_done("styles", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - styles")
            try:
                data = self.client.get_file_styles(file.key)
                if data:
                    save_json(file_dir / "styles.json", data)
                    size = (file_dir / "styles.json").stat().st_size
                    resume_mgr.mark_item("styles", file.key, BackupItemStatus.COMPLETED,
                                         size_bytes=size)
                    resume_mgr.manifest["stats"]["styles"] += \
                        len(data.get("meta", {}).get("styles", []))
                    self._add_bytes(progress, task_id, size)
            except Exception as e:
                self._log_error("styles", file.name, file.key, e)
                resume_mgr.mark_item("styles", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

        # -- Thumbnail --
        if not resume_mgr.is_item_done("thumbnail", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - thumbnail")
            thumb_url = file.thumbnail_url
            if not thumb_url and file_data:
                thumb_url = file_data.get("thumbnailUrl", "")
            if thumb_url:
                try:
                    content = self.client.download_binary(thumb_url)
                    if content:
                        thumb_path = file_dir / "thumbnail.png"
                        thumb_path.write_bytes(content)
                        resume_mgr.mark_item("thumbnail", file.key, BackupItemStatus.COMPLETED,
                                             size_bytes=len(content))
                        resume_mgr.manifest["stats"]["thumbnails"] += 1
                        self._add_bytes(progress, task_id, len(content))
                except Exception as e:
                    self._log_error("thumbnail", file.name, file.key, e)
                    resume_mgr.mark_item("thumbnail", file.key, BackupItemStatus.FAILED, error=str(e))
            else:
                resume_mgr.mark_item("thumbnail", file.key, BackupItemStatus.SKIPPED)
            progress.advance(task_id)

        # -- Image fills (Tier 1) --
        if self.config.include_image_fills and not resume_mgr.is_item_done("image_fills", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - image fills")
            try:
                count = download_image_fills(self.client, file.key, file_dir)
                size = sum(f.stat().st_size for f in (file_dir / "image_fills").rglob("*") if f.is_file()) if (file_dir / "image_fills").exists() else 0
                resume_mgr.mark_item("image_fills", file.key, BackupItemStatus.COMPLETED,
                                     size_bytes=size)
                self._add_bytes(progress, task_id, size)
                resume_mgr.manifest["stats"]["image_fills"] += count
            except Exception as e:
                self._log_error("image_fills", file.name, file.key, e)
                resume_mgr.mark_item("image_fills", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

        # -- Image exports (Tier 1, opt-in) --
        if self.config.include_image_exports and not resume_mgr.is_item_done("image_exports", file.key):
            progress.update(task_id, description=f"[cyan]{file.name} - image exports")
            try:
                # Load file_data from disk if not already in memory
                if not file_data:
                    fd_path = file_dir / "file_data.json"
                    if fd_path.exists():
                        file_data = json.loads(fd_path.read_text(encoding="utf-8"))
                if file_data:
                    stats = export_images(
                        self.client, file.key, file_data, file_dir,
                        formats=self.config.export_formats,
                        scale=self.config.export_scale,
                    )
                    total_exported = sum(stats.values())
                    resume_mgr.mark_item("image_exports", file.key, BackupItemStatus.COMPLETED)
                    resume_mgr.manifest["stats"]["image_exports"] += total_exported
                else:
                    resume_mgr.mark_item("image_exports", file.key, BackupItemStatus.SKIPPED)
            except Exception as e:
                self._log_error("image_exports", file.name, file.key, e)
                resume_mgr.mark_item("image_exports", file.key, BackupItemStatus.FAILED, error=str(e))
                resume_mgr.manifest["stats"]["errors"] += 1
            progress.advance(task_id)

    def _backup_team_level_data(self, team: FigmaTeam, team_dir: Path,
                                resume_mgr: ResumeManager):
        """Fetch team-level library data with pagination.

        Downloads published components, component sets, and styles
        that belong to the team library (not individual files).
        """
        # Team components (paginated via cursor)
        if self.config.include_components:
            try:
                all_components = []
                cursor = None
                while True:
                    data = self.client.get_team_components(team.id, cursor=cursor)
                    components = data.get("meta", {}).get("components", [])
                    all_components.extend(components)
                    cursor = data.get("meta", {}).get("cursor", {}).get("after")
                    if not cursor:
                        break
                if all_components:
                    save_json(team_dir / "team_components.json", {"components": all_components})
            except Exception as e:
                logger.error(f"team_components [{team.name}] ({team.id}): {e}")

        # Team component sets (paginated via cursor)
        if self.config.include_component_sets:
            try:
                all_sets = []
                cursor = None
                while True:
                    data = self.client.get_team_component_sets(team.id, cursor=cursor)
                    sets = data.get("meta", {}).get("component_sets", [])
                    all_sets.extend(sets)
                    cursor = data.get("meta", {}).get("cursor", {}).get("after")
                    if not cursor:
                        break
                if all_sets:
                    save_json(team_dir / "team_component_sets.json", {"component_sets": all_sets})
            except Exception as e:
                logger.error(f"team_component_sets [{team.name}] ({team.id}): {e}")

        # Team styles (paginated via cursor)
        if self.config.include_styles:
            try:
                all_styles = []
                cursor = None
                while True:
                    data = self.client.get_team_styles(team.id, cursor=cursor)
                    styles = data.get("meta", {}).get("styles", [])
                    all_styles.extend(styles)
                    cursor = data.get("meta", {}).get("cursor", {}).get("after")
                    if not cursor:
                        break
                if all_styles:
                    save_json(team_dir / "team_styles.json", {"styles": all_styles})
            except Exception as e:
                logger.error(f"team_styles [{team.name}] ({team.id}): {e}")

    def _compress_backup(self, backup_root: Path):
        """Create a zip archive of the completed backup directory."""
        console.print("\n  [dim]Compressing backup...[/dim]")
        archive_path = shutil.make_archive(
            str(backup_root), "zip", str(backup_root.parent), backup_root.name,
        )
        size = Path(archive_path).stat().st_size
        show_success(f"Archive created: {archive_path} ({human_size(size)})")

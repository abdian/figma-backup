"""
Image exporter -- handles exporting Figma frames/pages as PNG, SVG, or PDF,
and downloading image fill assets used in files.
"""

import logging
from pathlib import Path
from typing import List, Dict

from figma_backup.api import FigmaApiClient
from figma_backup.utils import safe_name

logger = logging.getLogger(__name__)

# Max node IDs per API request (Figma limit)
BATCH_SIZE = 50

# Allowed image file extensions for downloaded assets
ALLOWED_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "pdf", "bmp", "tiff"}

def get_exportable_node_ids(file_data: Dict) -> List[str]:
    """Extract top-level page and frame node IDs from file data.

    Walks the document tree: document -> pages -> top-level frames.
    Returns IDs of pages and their direct FRAME/COMPONENT children.
    """
    node_ids = []
    document = file_data.get("document", {})
    for page in document.get("children", []):
        node_ids.append(page["id"])
        for frame in page.get("children", []):
            if frame.get("type") in ("FRAME", "COMPONENT", "COMPONENT_SET"):
                node_ids.append(frame["id"])
    return node_ids


def export_images(
    client: FigmaApiClient,
    file_key: str,
    file_data: Dict,
    output_dir: Path,
    formats: List[str] = None,
    scale: float = 2.0,
) -> Dict[str, int]:
    """Export nodes as images in the specified formats.

    Batches node IDs (max 50 per request) to stay within API limits.
    Returns a dict of {format: count_exported}.
    """
    if formats is None:
        formats = ["png"]

    node_ids = get_exportable_node_ids(file_data)
    if not node_ids:
        return {}

    stats = {}
    exports_dir = output_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    for fmt in formats:
        count = 0
        fmt_dir = exports_dir / fmt
        fmt_dir.mkdir(parents=True, exist_ok=True)

        for i in range(0, len(node_ids), BATCH_SIZE):
            batch = node_ids[i:i + BATCH_SIZE]
            try:
                result = client.get_image_exports(file_key, batch, format=fmt, scale=scale)
            except Exception as e:
                logger.error(f"Image export batch failed: {e}")
                continue

            # Download each rendered image from the returned URLs
            images = result.get("images", {})
            for node_id, url in images.items():
                if not url:
                    continue
                data = client.download_binary(url)
                if data:
                    safe_id = safe_name(node_id.replace(":", "-"))
                    filepath = fmt_dir / f"{safe_id}.{fmt}"
                    filepath.write_bytes(data)
                    count += 1
        stats[fmt] = count
    return stats


def download_image_fills(
    client: FigmaApiClient,
    file_key: str,
    output_dir: Path,
) -> int:
    """Download all image fill assets used in a Figma file.

    Image fills are raster images used as backgrounds, patterns, etc.
    Returns the count of successfully downloaded images.
    """
    try:
        result = client.get_image_fills(file_key)
    except Exception as e:
        logger.error(f"Image fills failed: {e}")
        return 0

    images = result.get("meta", {}).get("images", {})
    if not images:
        return 0

    fills_dir = output_dir / "image_fills"
    fills_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for ref, url in images.items():
        if not url:
            continue
        data = client.download_binary(url)
        if data:
            # Determine file extension from URL or default to png
            url_path = url.split("?")[0]
            if "." in url_path.split("/")[-1]:
                ext = url_path.split(".")[-1].lower()
            else:
                ext = "png"
            # Sanitize ref to prevent path traversal and validate extension
            safe_ref = safe_name(ref)
            if ext not in ALLOWED_IMAGE_EXTS:
                ext = "png"
            filepath = fills_dir / f"{safe_ref}.{ext}"
            filepath.write_bytes(data)
            count += 1
    return count

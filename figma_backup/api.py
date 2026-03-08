"""
Figma API client -- wraps all Figma REST API calls with tier-aware
rate limiting, retry logic, and exponential backoff.

Rate limit tiers:
  Tier 1 (~10 req/min): /files, /images, /versions
  Tier 2 (~30 req/min): /teams, /projects, /comments
  Tier 3 (~50 req/min): /components, /component_sets, /styles
"""

import time
import logging
from typing import Optional, Dict, Any, List

import requests

from figma_backup.models import ApiTier

logger = logging.getLogger(__name__)

# Conservative rate limits per tier (requests per minute)
TIER_LIMITS = {
    ApiTier.TIER_1: 10,
    ApiTier.TIER_2: 30,
    ApiTier.TIER_3: 50,
}


def classify_endpoint(path: str) -> ApiTier:
    """Determine the rate limit tier for a given API path."""
    tier3_keywords = ["/components", "/component_sets", "/styles"]
    for kw in tier3_keywords:
        if kw in path:
            return ApiTier.TIER_3

    tier2_keywords = ["/teams/", "/projects/", "/comments"]
    for kw in tier2_keywords:
        if kw in path:
            return ApiTier.TIER_2

    # Default to most restrictive tier
    return ApiTier.TIER_1


class RateLimiter:
    """Sliding-window rate limiter with one bucket per API tier.

    Tracks timestamps of recent requests and sleeps when the
    bucket is full, ensuring we stay within Figma's rate limits.
    """

    def __init__(self):
        self._buckets: Dict[ApiTier, List[float]] = {
            tier: [] for tier in ApiTier
        }

    def wait_if_needed(self, tier: ApiTier):
        """Block if we've exceeded the rate limit for this tier."""
        limit = TIER_LIMITS[tier]
        window = 60.0  # 1-minute sliding window
        now = time.time()

        # Remove timestamps older than the window
        self._buckets[tier] = [t for t in self._buckets[tier] if now - t < window]
        bucket = self._buckets[tier]

        if len(bucket) >= limit:
            oldest = bucket[0]
            sleep_time = window - (now - oldest) + 0.5  # +0.5s safety margin
            if sleep_time > 0:
                logger.info(f"Rate limit (Tier {tier.value}): sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)

        self._buckets[tier].append(time.time())


class FigmaApiClient:
    """HTTP client for the Figma REST API.

    All API calls go through the get() method which handles:
    - Tier-aware pre-emptive rate limiting
    - 429 (Too Many Requests) retry with Retry-After header
    - Exponential backoff on transient errors
    """

    BASE_URL = "https://api.figma.com/v1"

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({"X-Figma-Token": token})
        self.rate_limiter = RateLimiter()

    def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """Make a GET request with rate limiting and retry logic."""
        url = f"{self.BASE_URL}{path}"
        tier = classify_endpoint(path)

        for attempt in range(max_retries):
            self.rate_limiter.wait_if_needed(tier)
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 60))
                    logger.warning(f"429 on {path}, waiting {wait}s")
                    if attempt < max_retries - 1:
                        time.sleep(wait)
                        continue
                    raise requests.exceptions.HTTPError(f"Rate limited after {max_retries} retries")
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error {path} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise
        return {}

    def download_binary(self, url: str, timeout: int = 120, max_retries: int = 3) -> Optional[bytes]:
        """Download binary content (images, thumbnails) from any URL.

        Uses a plain request (no auth headers) to avoid leaking the
        Figma token to external CDN/S3 hosts.
        Retries with exponential backoff on failure.
        """
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, timeout=timeout)
                resp.raise_for_status()
                return resp.content
            except requests.exceptions.RequestException as e:
                logger.error(f"Binary download (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return None

    # ── Convenience methods for each Figma API endpoint ──

    def get_me(self) -> Dict:
        """Get current user info (GET /me)."""
        return self.get("/me")

    def get_team_projects(self, team_id: str) -> Dict:
        """List all projects in a team (Tier 2)."""
        return self.get(f"/teams/{team_id}/projects")

    def get_project_files(self, project_id: str) -> Dict:
        """List all files in a project (Tier 2)."""
        return self.get(f"/projects/{project_id}/files")

    def get_file(self, file_key: str) -> Dict:
        """Get full file content and metadata (Tier 1)."""
        return self.get(f"/files/{file_key}")

    def get_file_comments(self, file_key: str) -> Dict:
        """Get all comments in a file (Tier 2)."""
        return self.get(f"/files/{file_key}/comments")

    def get_file_versions(self, file_key: str) -> Dict:
        """Get version history of a file (Tier 1)."""
        return self.get(f"/files/{file_key}/versions")

    def get_file_components(self, file_key: str) -> Dict:
        """Get components in a file (Tier 3)."""
        return self.get(f"/files/{file_key}/components")

    def get_file_component_sets(self, file_key: str) -> Dict:
        """Get component sets in a file (Tier 3)."""
        return self.get(f"/files/{file_key}/component_sets")

    def get_file_styles(self, file_key: str) -> Dict:
        """Get styles in a file (Tier 3)."""
        return self.get(f"/files/{file_key}/styles")

    def get_image_fills(self, file_key: str) -> Dict:
        """Get download URLs for all image fills in a file (Tier 1)."""
        return self.get(f"/files/{file_key}/images")

    def get_image_exports(
        self, file_key: str, node_ids: List[str],
        format: str = "png", scale: float = 2.0,
    ) -> Dict:
        """Export specific nodes as images (Tier 1)."""
        return self.get(f"/images/{file_key}", params={
            "ids": ",".join(node_ids),
            "format": format,
            "scale": scale,
        })

    def get_team_components(self, team_id: str, page_size: int = 50, cursor: str = None) -> Dict:
        """Get published components in a team library (Tier 3, paginated)."""
        params: Dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        return self.get(f"/teams/{team_id}/components", params=params)

    def get_team_component_sets(self, team_id: str, page_size: int = 50, cursor: str = None) -> Dict:
        """Get published component sets in a team library (Tier 3, paginated)."""
        params: Dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        return self.get(f"/teams/{team_id}/component_sets", params=params)

    def get_team_styles(self, team_id: str, page_size: int = 50, cursor: str = None) -> Dict:
        """Get published styles in a team library (Tier 3, paginated)."""
        params: Dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        return self.get(f"/teams/{team_id}/styles", params=params)

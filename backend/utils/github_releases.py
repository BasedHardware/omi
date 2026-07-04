import logging
import os
import re
from typing import Any, Dict, List, Optional, cast

from database.redis_db import get_generic_cache, set_generic_cache
from utils.executors import db_executor, run_blocking
from utils.http_client import get_web_fetch_client
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

MAX_PAGES = 20  # Safety cap to prevent runaway pagination


async def get_omi_github_releases(
    cache_key: str, tag_filter: Optional[re.Pattern[str]] = None
) -> Optional[List[Dict[str, Any]]]:
    """Fetch releases from GitHub API with caching.

    When tag_filter is provided, paginates through all pages and returns only
    releases whose tag_name matches the filter. Without tag_filter, returns
    the first page of releases unfiltered (sufficient for desktop releases
    which are always recent).

    Resilience: if GitHub returns errors or an empty list during an upstream
    outage, we fall back to a longer-lived "last known good" cache so the
    macos.omi.me download endpoint keeps serving the previous DMG link.
    """

    lkg_key = f"{cache_key}:lkg"

    cached_releases = await run_blocking(db_executor, get_generic_cache, cache_key)
    if cached_releases is not None:
        return cached_releases

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    github_token = os.getenv('GITHUB_TOKEN')
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    collected: List[Dict[str, Any]] = []
    fetch_failed = False

    try:
        page = 1
        client = get_web_fetch_client()
        while page <= MAX_PAGES:
            url = f"https://api.github.com/repos/BasedHardware/omi/releases?per_page=100&page={page}"
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(
                    "Error fetching GitHub releases page %d: %d %s",
                    page,
                    response.status_code,
                    sanitize(response.text),
                )
                fetch_failed = True
                break

            loaded: object = response.json()
            if not loaded:
                break
            page_releases: List[Dict[str, Any]] = cast(List[Dict[str, Any]], loaded) if isinstance(loaded, list) else []

            if tag_filter:
                for release in page_releases:
                    tag_name = release.get("tag_name", "")
                    if tag_filter.match(tag_name):
                        collected.append(release)
            else:
                collected.extend(page_releases)

            if not tag_filter:
                break

            if len(page_releases) < 100:
                break

            page += 1
    except Exception as exc:
        logger.exception("Exception fetching GitHub releases: %s", sanitize(str(exc)))
        fetch_failed = True

    if fetch_failed or not collected:
        last_known_good = await run_blocking(db_executor, get_generic_cache, lkg_key)
        if last_known_good:
            logger.warning(
                "GitHub releases fetch %s; serving last-known-good cache for %s",
                "failed" if fetch_failed else "returned empty",
                cache_key,
            )
            await run_blocking(db_executor, set_generic_cache, cache_key, last_known_good, ttl=60)
            return last_known_good

        await run_blocking(db_executor, set_generic_cache, cache_key, collected, ttl=60)
        return collected

    await run_blocking(db_executor, set_generic_cache, cache_key, collected, ttl=300)
    await run_blocking(db_executor, set_generic_cache, lkg_key, collected, ttl=86400)
    return collected


def extract_key_value_pairs(markdown_content: str) -> Dict[str, Any]:
    if not markdown_content:
        return {}

    key_value_pattern = re.compile(r'<!-- KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END -->', re.DOTALL)
    key_value_match = key_value_pattern.search(markdown_content)

    if not key_value_match:
        return {}

    key_value_string = key_value_match.group(1).strip()
    lines = key_value_string.split('\n')
    key_value_map: Dict[str, Any] = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split(':', 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()

            if key == 'ota_update_steps':
                key_value_map[key] = [step.strip() for step in value.split(',') if step.strip()]
            elif key == 'changelog':
                key_value_map[key] = [item.strip() for item in value.split('|') if item.strip()]
            else:
                key_value_map[key] = value

    return key_value_map

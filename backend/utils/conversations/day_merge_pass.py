"""Default-off daily-summary seam; decision counts only, no content or mutations.

The future executor must recheck engagement transactionally and use the desktop /
pendant authoritative call link, never infer duplicate audio from wall overlap.
"""

import logging
import os
from collections import Counter

logger = logging.getLogger(__name__)


def engaged(row: dict) -> bool:
    # Unknown engagement is protected. Until an authoritative receipt is wired,
    # every row is link-only; the hook cannot accidentally authorize rewrites.
    return row.get('engagement_unobserved') is not True or any(
        row.get(key)
        for key in (
            'opened_at',
            'edited_at',
            'shared_at',
            'acted_at',
            'is_user_edited',
            'is_shared',
            'user_kept',
        )
    )


def shadow_day(rows: list[dict]) -> dict[str, int]:
    if os.getenv('DEMAND_PROCESSING_DAY_MERGE_SHADOW_ENABLED', 'false').lower() != 'true':
        return {}
    counts = Counter('link_only' if engaged(row) else 'candidate' for row in rows)
    # A candidate is only a review input, never a merge instruction in this PR.
    logger.info(
        'event=demand_day_merge mode=shadow link_only=%s candidate=%s', counts['link_only'], counts['candidate']
    )
    return dict(counts)

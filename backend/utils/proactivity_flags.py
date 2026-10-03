"""Server-side v2 flag authority shared by admission and exclusive mentor dispatch."""

import importlib
import logging
import os
from functools import lru_cache
from typing import Any

from config.proactivity_v2 import ProactivityDenied
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def flag_client() -> Any:
    key = os.getenv('POSTHOG_PROJECT_API_KEY') or os.getenv('POSTHOG_API_KEY')
    if not key:
        raise ProactivityDenied('flag_unavailable')
    return importlib.import_module('posthog').Posthog(
        project_api_key=key,
        host=os.getenv('POSTHOG_HOST', 'https://app.posthog.com'),
        send=False,
        sync_mode=True,
        feature_flags_request_timeout_seconds=2,
    )


def enabled(uid: str) -> bool:
    flags = flag_client().get_feature_variants(uid)
    if not isinstance(flags, dict):
        raise ProactivityDenied('flag_unavailable')
    return flags.get('proactivity_v2') is True


def mentor_pipeline(uid: str) -> str:
    """Resolve one exclusive mentor lane using the admission flag client/cache."""
    pipeline = os.getenv('MENTOR_PIPELINE', 'legacy')
    if pipeline != 'cohort':
        return pipeline
    try:
        return 'v2' if enabled(uid) else 'legacy'
    except Exception:
        record_fallback(
            component='other',
            from_mode='mentor_cohort',
            to_mode='legacy',
            reason='other',
            outcome='recovered',
            log=logger,
        )
        return 'legacy'

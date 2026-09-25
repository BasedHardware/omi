import logging
from posthog import Posthog

logger = logging.getLogger(__name__)

def _safe_emit_posthog_event(event: str, properties: dict):
    try:
        Posthog.capture(event, properties)
    except Exception as e:
        logger.error(f"PostHog event failed: {str(e)}")
"""Best-effort shadow handoff; import/dispatch failure never fails an accepted upload."""

import logging

logger = logging.getLogger(__name__)


async def offer_shadow_upload(**kwargs) -> None:
    # The shadow is best effort: its import or handoff must never fail a legacy upload.
    try:
        from utils.batch_pipeline.shadow_intake import offer_upload

        await offer_upload(**kwargs)
    except Exception as error:
        logger.info('event=batch_shadow_intake outcome=error exception_type=%s', type(error).__name__)

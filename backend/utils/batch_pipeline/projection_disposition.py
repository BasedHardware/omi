"""No-text dispositions share the ordinary transactional projection fences."""

import logging

from database.batch_pipeline_projection_protocol import ProjectionReplay
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def mirror_assignment(store, session):
    # Assignment writes the watermark outside Store.run. Shadow refresh is
    # idempotent and advisory; never replace the authoritative receipt outcome.
    try:
        mirror = getattr(store, 'mirror_assignment', None)
        if mirror is not None:
            mirror(session)
    except Exception:
        logger.warning('event=jobstore_shadow op=refresh outcome=hook_error site=projection_assignment')


def persist_disposition(session, *, quarantined=False):
    # Recheck binding, ledger ownership, predecessor and privacy after planning.
    # A competing assignment receipt wins; never replace it with a no-op.
    try:
        receipt = session.persist_empty(quarantined=True) if quarantined else session.persist_empty(superseded=True)
    except ProjectionReplay as replay:
        return replay.receipt
    if quarantined:
        logger.warning('event=batch_projection action=assignment outcome=ambiguous_generation_quarantined')
        record_fallback(component='sync_dispatch', from_mode='none', to_mode='none', reason='other', outcome='degraded')
    else:
        logger.info('event=batch_projection action=assignment outcome=superseded')
    return receipt

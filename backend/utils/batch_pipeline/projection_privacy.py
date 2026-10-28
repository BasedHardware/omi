"""Bounded control settlement around assignment and follow-up coordinators."""

from functools import wraps
import logging

from config.policy import ProjectionPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_privacy import HOLD_REASONS, hold, resume
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
PRIVACY_HELD = object()


def settle_refusals(*, assignment=False):
    def decorate(method):
        @wraps(method)
        def run(self, segment_id, job, entry, binding, *args, **kwargs):
            if job.get('shadow'):
                return method(self, segment_id, job, entry, binding, *args, **kwargs)
            try:
                hint = job.get('_projection_privacy_refusal')
                if hint:
                    raise BatchPrivacyBlocked(hint)
                if entry.get('projection_privacy_refusal'):
                    policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                    entry = resume(self.store, segment_id, binding, self.clock(), policy=policy)
                return method(self, segment_id, job, entry, binding, *args, **kwargs)
            except BatchPrivacyBlocked as error:
                if error.reason not in HOLD_REASONS:
                    raise
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                if hold(self.store, segment_id, binding, self.clock(), error.reason, policy=policy):
                    logger.warning(
                        'event=batch_projection action=assignment outcome=privacy_held fence_reason=%s',
                        error.reason.value,
                    )
                    record_fallback(
                        component='sync_dispatch',
                        from_mode='batch',
                        to_mode='held',
                        reason='policy',
                        outcome='degraded',
                    )
                return PRIVACY_HELD if assignment else None

        return run

    return decorate

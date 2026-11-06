"""Bounded control settlement around assignment and follow-up coordinators."""

from functools import wraps
import logging

from config.batch_pipeline import projection_privacy_refusal_resume_enabled
from config.policy import ProjectionPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_privacy import HOLD_REASONS, hold, resume
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from utils.batch_pipeline.metrics import (
    PROJECTION_PRIVACY_RESUMES_ATTEMPTED,
    PROJECTION_PRIVACY_RESUMES_SUCCEEDED,
    PROJECTION_PRIVACY_FALLTHROUGHS,
    PROJECTION_PRIVACY_STILL_REFUSED,
)
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
PRIVACY_HELD = object()


def _resume(self, segment_id, binding, policy):
    PROJECTION_PRIVACY_RESUMES_ATTEMPTED.inc()
    entry = resume(self.store, segment_id, binding, self.clock(), policy=policy)
    PROJECTION_PRIVACY_RESUMES_SUCCEEDED.inc()
    return entry


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
                    entry = _resume(self, segment_id, binding, policy)
                return method(self, segment_id, job, entry, binding, *args, **kwargs)
            except BatchPrivacyBlocked as error:
                if error.reason not in HOLD_REASONS:
                    raise
                policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                try:
                    changed = hold(self.store, segment_id, binding, self.clock(), error.reason, policy=policy)
                except ProjectionBlocked as blocked:
                    if (
                        str(blocked) != 'privacy refusal no longer applies'
                        or not projection_privacy_refusal_resume_enabled()
                    ):
                        raise
                    had_refusal = bool(entry.get('projection_privacy_refusal'))
                    if job.get('_projection_privacy_refusal'):
                        # read() supplies settlement-only defaults with this hint.
                        # Never let them authorize assignment: reload/pin through
                        # the ordinary stage-policy transaction before retrying.
                        policy = self.store.policy(segment_id)
                        job = {**job, 'policy_parts': {**job['policy_parts'], 'projection': policy.to_dict()}}
                        job.pop('_projection_privacy_refusal')
                    if had_refusal:
                        entry = _resume(self, segment_id, binding, policy)
                    if not had_refusal:
                        PROJECTION_PRIVACY_FALLTHROUGHS.inc()
                    # One retry only. A new refusal from the wrapped transaction
                    # must escape rather than recursively retrying stale inputs.
                    return method(self, segment_id, job, entry, binding, *args, **kwargs)
                PROJECTION_PRIVACY_STILL_REFUSED.inc()
                if changed:
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

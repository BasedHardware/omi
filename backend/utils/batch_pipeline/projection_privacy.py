"""Bounded control settlement around assignment and follow-up coordinators."""

from functools import wraps
import logging

from config.batch_pipeline import projection_privacy_refusal_resume_enabled
from config.policy import ProjectionPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_privacy import HOLD_REASONS, hold, resume
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from utils.batch_pipeline.metrics import PROJECTION_PRIVACY_RESUMES_ATTEMPTED, PROJECTION_PRIVACY_RESUMES_SUCCEEDED
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
PRIVACY_HELD = object()


def settle_refusals(*, assignment=False):
    def decorate(method):
        @wraps(method)
        def run(self, segment_id, job, entry, binding, *args, **kwargs):
            if job.get('shadow'):
                return method(self, segment_id, job, entry, binding, *args, **kwargs)
            # Retry once without the stale hint. Resume and assignment still
            # perform their ordinary transactional privacy/ownership fences.
            for ignore_hint in (False, True):
                try:
                    hint = job.get('_projection_privacy_refusal')
                    if hint and not ignore_hint:
                        raise BatchPrivacyBlocked(hint)
                    if entry.get('projection_privacy_refusal'):
                        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                        PROJECTION_PRIVACY_RESUMES_ATTEMPTED.inc()
                        entry = resume(self.store, segment_id, binding, self.clock(), policy=policy)
                        PROJECTION_PRIVACY_RESUMES_SUCCEEDED.inc()
                    if ignore_hint:
                        # read() synthesized the hint with settlement-only code
                        # defaults. Assignment must use a durably pinned part;
                        # its wider policy privacy fence remains authoritative.
                        policy = self.store.policy(segment_id)
                        job = {
                            **job,
                            'policy_parts': {**job['policy_parts'], 'projection': policy.to_dict()},
                        }
                        job.pop('_projection_privacy_refusal', None)
                    return method(self, segment_id, job, entry, binding, *args, **kwargs)
                except BatchPrivacyBlocked as error:
                    if error.reason not in HOLD_REASONS:
                        raise
                    policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
                    try:
                        changed = hold(self.store, segment_id, binding, self.clock(), error.reason, policy=policy)
                    except ProjectionBlocked as blocked:
                        if (
                            not ignore_hint
                            and str(blocked) == 'privacy refusal no longer applies'
                            and projection_privacy_refusal_resume_enabled()
                        ):
                            continue
                        raise
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

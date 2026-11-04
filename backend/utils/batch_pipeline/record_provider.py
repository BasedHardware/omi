"""Native record units use C8 provider STT for declared unsupported languages.

Durable capture admission outlives an allowlist rollback. Routing uses its
recorded language, never the current env or a learned primary-language hint.
"""

from dataclasses import replace
import logging

from config.server_batch import UNSUPPORTED
from config.stt_provider_policy import normalized_stt_language
from database.batch_pipeline_intake import admit
from utils.batch_pipeline.language_metrics import record_route
from utils.batch_pipeline.provider_stt_admission import provider_enqueue, resolve_route

logger = logging.getLogger(__name__)


def admit_record_units(store, items, binding, now, *, policy, provider_outbox_factory=None, **kwargs):
    language = normalized_stt_language(binding.language)
    if language not in UNSUPPORTED:
        return admit(store, items, binding, now, policy=policy, **kwargs)
    route = resolve_route(language, byok=policy.provider_reason == 'byok')
    if provider_outbox_factory is None:
        raise ValueError('native provider outbox factory required')
    outbox = provider_outbox_factory()
    wakes = {}
    policy = replace(
        policy,
        stt_route=route.stt_route,
        provider_reason=route.provider_reason,
        provider_service=route.provider_service,
    )
    result = admit(
        store,
        [replace(item, requires_compute_admission=False) for item in items],
        binding,
        now,
        policy=policy,
        enqueue=provider_enqueue(route, outbox, wakes, native_record=True),
        **kwargs,
    )
    # The outbox row commits atomically with the job and binding. A failed wake
    # is swept later, exactly as for ordinary C8 upload admission.
    for row_id, wake_token in wakes.items():
        try:
            outbox.wake(row_id, wake_token)
        except Exception as error:
            logger.warning(
                'event=batch_provider_stt action=wake outcome=deferred exception_type=%s', type(error).__name__
            )
    if wakes:
        record_route('intake', language, 'multilingual')
    return result

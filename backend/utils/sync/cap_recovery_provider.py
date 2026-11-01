"""Fenced provider-result custody across a held-piece ingest/process crash."""

import json
import time
from typing import Callable, Any

from database import sync_cap_recovery
from utils.encryption import encrypt, decrypt
from utils.observability.fallback import record_fallback
from utils.stt.pre_recorded import held_single_attempt


def transcribe(uid: str, context: dict | None, dispatch: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if context is None:
        return dispatch(*args, **kwargs)
    cached = context.get('receipt', {}).get('provider_result')
    if cached:
        result = json.loads(decrypt(cached, uid))
        return result['words'], result['language']
    if not sync_cap_recovery.provider_checkpoint(uid, context, {'provider_started_at': time.time()}):
        raise sync_cap_recovery.RecoveryIngestFenced('held dispatch ownership changed')
    with held_single_attempt():
        words, language = dispatch(*args, **kwargs)
    encoded = encrypt(json.dumps({'words': words, 'language': language}), uid)
    if not sync_cap_recovery.provider_checkpoint(
        uid,
        context,
        {
            **({'provider_result': encoded} if words else {'provider_empty': True}),
            'provider_completed_at': time.time(),
        },
    ):
        raise sync_cap_recovery.RecoveryIngestFenced('held result ownership changed')
    if context.get('receipt', {}).get('provider_cache_omitted'):
        record_fallback(
            component='sync_dispatch', from_mode='cached', to_mode='uncached', reason='other', outcome='degraded'
        )
    return words, language

"""Bounded STT provenance; quantities remain estimated until provider acceptance exists."""

import os
from typing import Any
from utils.byok import get_byok_key


def live_usage_metadata(runtime: Any) -> dict[str, str]:
    if runtime.use_custom_stt:
        return {'funding': 'custom', 'provider': 'unknown', 'source': 'listen'}
    raw = getattr(runtime.stt_service, 'value', runtime.stt_service)
    text = str(raw or '').lower()
    provider = next((p for p in ('deepgram', 'modulate', 'soniox', 'parakeet') if p in text), 'unknown')
    if text.startswith('dg-'):
        provider = 'deepgram'
    self_hosted = os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').lower() == 'true'
    funding = 'byok' if provider == 'deepgram' and not self_hosted and get_byok_key('deepgram') else 'omi'
    # Self-hosted Deepgram has no evidenced per-provider compute card; keep the proxy explicit.
    if provider == 'deepgram' and self_hosted:
        provider = 'unknown'
    return {'funding': funding, 'provider': provider, 'source': 'listen'}

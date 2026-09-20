"""Opt-in listen adapter; legacy receiver/failover remain the default path."""

from __future__ import annotations

import json
import os
import random
from dataclasses import replace
from functools import lru_cache
from typing import Any

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from config.stt_provider_policy import STTServingSurface, default_models_for_surface
from config.stt_routing import Preference, ProviderSpec, RoutingRequest, STREAMING_REGISTRY, rank_candidates
from utils.byok import get_byok_keys
from utils.observability.fallback import record_fallback
from utils.observability.transcription import record_live_stt_failover_accepted
from utils.stt.routing import LiveSTTRoute, TranscriptCallback
from utils.stt.routing_health import RedisHealthStore
from utils.stt.socket import STTSocket
from utils.stt.streaming import (
    STTService,
    process_audio_dg,
    process_audio_modulate,
    process_audio_parakeet,
    process_audio_soniox,
    requested_stt_language,
)
from utils.stt.vad_gate import GatedSTTSocket


@lru_cache(maxsize=4)
def health_store(namespace: str) -> RedisHealthStore:
    client: Any = redis.Redis(
        host=os.getenv('REDIS_DB_HOST') or 'localhost',
        port=int(os.getenv('REDIS_DB_PORT', '6379')),
        username='default',
        password=os.getenv('REDIS_DB_PASSWORD'),
        socket_connect_timeout=0.15,
        socket_timeout=0.15,
        retry=Retry(NoBackoff(), 0),
    )
    return RedisHealthStore(client, namespace=namespace)


def routing_for_listen(host: Any) -> RoutedListenSTT | None:
    mode = os.getenv('STT_ROUTING_MODE', 'legacy').strip().lower()
    if mode not in {'ordered', 'health'} or host.is_multi_channel or host.use_custom_stt or get_byok_keys():
        return None
    language = requested_stt_language(
        host.language,
        host.language.split('-')[0],
        multi_lang_enabled=host.multi_lang_enabled,
        surface=STTServingSurface.STREAMING,
    )
    registry = dict(STREAMING_REGISTRY)
    configured = frozenset(
        provider
        for provider, variable in (
            ('modulate', 'MODULATE_API_KEY'),
            ('soniox', 'SONIOX_API_KEY'),
            ('parakeet', 'HOSTED_PARAKEET_API_URL'),
            ('deepgram_cloud', 'DEEPGRAM_API_KEY'),
        )
        if os.getenv(variable)
    )
    if os.getenv('DEEPGRAM_SELF_HOSTED_ENABLED', '').lower() == 'true':
        for token in ('dg-nova-3', 'dg-nova-2'):
            registry[token] = replace(registry[token], provider='deepgram_self_hosted', cost_class='self_hosted')
        if os.getenv('DEEPGRAM_SELF_HOSTED_URL'):
            configured = configured | {'deepgram_self_hosted'}
    tokens = os.getenv('STT_SERVICE_MODELS', ','.join(default_models_for_surface(STTServingSurface.STREAMING)))
    policy = tuple(Preference(token.strip(), i) for i, token in enumerate(tokens.split(',')) if token.strip())
    raw = os.getenv('STT_ROUTING_POLICY_JSON')
    if raw:
        try:
            rows = json.loads(raw)
            if not isinstance(rows, list) or not 0 < len(rows) <= 16:
                raise ValueError('policy size')
            parsed: list[Preference] = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError('policy row')
                token, priority, weight = row.get('token'), row.get('priority'), row.get('weight', 1.0)
                if not isinstance(token, str) or not isinstance(priority, int) or not isinstance(weight, (float, int)):
                    raise ValueError('policy types')
                if set(row) - {'token', 'priority', 'weight'}:
                    raise ValueError('policy fields')
                parsed.append(Preference(token, priority, weight))
            policy = tuple(parsed)
        except (TypeError, ValueError):
            record_fallback(
                component='stt_selection',
                from_mode='routing_policy',
                to_mode='config_order',
                reason='config_incomplete',
                outcome='degraded',
            )
    selection = rank_candidates(RoutingRequest(language, configured), registry, policy, {}, random.getrandbits(64))
    for provider, reason in selection.skipped:
        record_fallback(
            component='stt_selection', from_mode=provider, to_mode='skipped', reason=reason, outcome='degraded'
        )
    health = None
    if mode == 'health':
        namespace = os.getenv('STT_HEALTH_NAMESPACE', '').strip()
        if namespace and len(namespace) <= 120:
            try:
                health = health_store(namespace)
            except (ValueError, redis.RedisError):
                health = None
        if health is None:
            record_fallback(
                component='stt_selection',
                from_mode='shared_health',
                to_mode='config_order',
                reason='config_incomplete',
                outcome='degraded',
            )
    return RoutedListenSTT(host, LiveSTTRoute(selection.candidates, language=language, health=health))


class RoutedListenSTT:
    def __init__(self, host: Any, route: LiveSTTRoute) -> None:
        self.host = host
        self.route = route
        self.callbacks: tuple[TranscriptCallback, TranscriptCallback, int] | None = None

    async def connect(
        self, callback: TranscriptCallback, sample_rate: int, passthrough_callback: TranscriptCallback | None
    ) -> STTSocket:
        self.callbacks = callback, passthrough_callback or callback, sample_rate
        keywords = self.host.vocabulary[:100] if self.host.vocabulary else []

        async def connector(spec: ProviderSpec, transcript: TranscriptCallback) -> STTSocket | None:
            if spec.service == 'modulate':
                return await process_audio_modulate(transcript, sample_rate, self.route.language)
            if spec.service == 'soniox':
                return await process_audio_soniox(transcript, sample_rate, self.route.language)
            connect = process_audio_parakeet if spec.service == 'parakeet' else process_audio_dg
            return await connect(
                transcript,
                self.route.language,
                sample_rate,
                1,
                model=spec.model,
                keywords=keywords,
                is_active=lambda: self.host.state.active,
            )

        def sink(spec: ProviderSpec) -> TranscriptCallback:
            return (passthrough_callback or callback) if spec.service in {'modulate', 'soniox'} else callback

        socket, spec = await self.route.connect(connector, callback, callback_for_provider=sink)
        self.host.stt_service, self.host.stt_model = STTService(spec.service), spec.model
        return socket

    async def replace_dead_socket(self, receiver: Any) -> bool:
        if not self.callbacks or not self.host.state.active or self.host.state.stt_terminal_failure:
            return False
        previous = receiver.stt_socket
        callback, passthrough_callback, sample_rate = self.callbacks
        try:
            raw = await self.connect(callback, sample_rate, passthrough_callback)
        except Exception:
            return False
        receiver.stt_socket = (
            GatedSTTSocket(
                raw,
                gate=receiver.vad_gate,
                passthrough_audio=self.host.stt_service in {STTService.modulate, STTService.soniox},
            )
            if receiver.vad_gate and not getattr(raw, 'manages_vad', False)
            else raw
        )
        record_live_stt_failover_accepted(
            provider=self.host.stt_service.value,
            platform=getattr(getattr(self.host, 'client_device_context', None), 'platform', None),
        )
        if previous is not None:
            try:
                previous.finish()
            except Exception:
                pass  # The retired socket is already dead; content was not discarded.
        return True

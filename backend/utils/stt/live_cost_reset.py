"""Explicit operator action on cost gates only; no account data or serving override."""

from __future__ import annotations

import json
import logging
import re
import uuid

from redis.exceptions import WatchError

from config import live_stt_state
from config.live_stt_registry import registry
from utils.stt.live_gate import GateState, gate_rate

logger = logging.getLogger(__name__)


async def reset_cost_target(
    redis, *, target: str, environment: str, reason: str, stage: int = 100, apply: bool = False
):
    """Dry-run by default. Reset all scopes and audit in one WATCH transaction.

    Stage 0 reverses a mistaken release with a five-minute bench. Stage 100
    clears evidence, never pins health: new provider failures can bench again.
    Run after the rolling deployment completes to avoid old local fault-state
    reconciliation. The endpoint/account namespace is the runtime's own.
    """
    if environment not in {'prod', 'dev', 'local', 'offline'} or live_stt_state.stage() != environment:
        raise ValueError('explicit environment must match the runtime stage')
    if type(stage) is not int or stage not in (0, 100):
        raise ValueError('reset stage must be 0 or 100')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,79}', reason):
        raise ValueError('reason must be a content-free incident/change identifier (1-80 characters)')
    entries = registry()
    entry = next((entry for entry in entries if entry.id == target), None)
    if entry is None:
        raise ValueError('target must name one registered target')
    identity = live_stt_state.state_identity(entries)
    languages = ['all', *sorted(live_stt_state.ROUTED_LANGUAGES)]
    keys = [live_stt_state.cost_key(entry, language) for language in languages]
    audit_id = uuid.uuid4().hex
    audit_key = live_stt_state.cost_key(entry, 'operator-audit:' + audit_id)
    for _ in range(5):
        async with redis.pipeline(transaction=True) as pipe:
            if apply:
                await pipe.watch(*keys)
            values = await pipe.mget(keys) if apply else await redis.mget(keys)
            old = [GateState.decode(json.loads(raw)) if raw else GateState() for raw in values]
            seconds, micros = await redis.time()
            now = float(seconds) + float(micros) / 1_000_000
            if live_stt_state.state_identity(registry()) != identity:
                raise RuntimeError('runtime identity changed; reset aborted')
            # An isolated pod can have a few fault-only generations not yet in
            # Redis. Fence those too, so refresh cannot resurrect its old bench.
            generations = [max(state.generation + 1, int(now * 1_000_000)) for state in old]
            report = {
                'event': 'live_stt_cost_operator_reset',
                'applied': apply,
                'audit_id': audit_id,
                'environment': environment,
                'target': target,
                'stage': stage,
                'reason': reason,
                'timestamp': now,
                'scopes': [
                    {
                        'language': lang,
                        'old_stage': state.stage,
                        'old_generation': state.generation,
                        'generation': generation,
                    }
                    for lang, state, generation in zip(languages, old, generations)
                ],
            }
            if not apply:
                return report
            pipe.multi()
            for key, state, generation in zip(keys, old, generations):
                new = GateState(
                    threshold=gate_rate(),
                    stage=stage,
                    generation=generation,
                    until=now + 300 if stage == 0 else 0,
                    strikes=state.strikes if stage == 0 else 0,
                )
                # Match the serving writer's healthy TTL; benches never expire
                # into a fresh stage-100 state without their recovery trial.
                pipe.set(key, json.dumps(new.encode(), separators=(',', ':')), ex=900 if stage == 100 else None)
            pipe.set(audit_key, json.dumps(report, separators=(',', ':')), ex=30 * 86400)
            logger.warning(
                'live_stt_cost_operator_reset_submit audit_id=%s target=%s stage=%d reason=%s',
                audit_id,
                target,
                stage,
                reason,
            )
            try:
                await pipe.execute()
            except WatchError:
                continue
            logger.warning('live_stt_cost_operator_reset %s', json.dumps(report, separators=(',', ':')))
            return report
    raise RuntimeError('cost gates changed during all five reset attempts; no reset committed')

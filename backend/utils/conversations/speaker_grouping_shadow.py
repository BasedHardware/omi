"""Bounded cached-vector alternatives and content-free comparison receipts.

No I/O or models: persistence uses always-encrypted sidecars in the existing write.
The caller owns profile admission, the incumbent and final transcript publication.
"""

# LIFECYCLE: permanent
from __future__ import annotations

import logging
import json
import time
from collections import defaultdict
from typing import Any, Mapping, cast

from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment

import numpy as np
from prometheus_client import Counter, REGISTRY

from config.speaker_grouping import VARIANTS, configuration
from utils.log_sanitizer import sanitize
from utils.manual_speaker_assignments import (
    apply_manual_assignments,
    manual_assignment_decision,
    manual_rejected_speakers,
)
from utils.observability.fallback import record_fallback
from utils.observability.owner_recognition import surface_label
from utils.stt.conversation_speakers import (
    OWNER_IDENTITY,
    VOICE_MATCH_THRESHOLD,
    SpeakerResolution,
    Identity,
    unit_voice_vector,
    resolve_conversation_speakers,
)
from utils.stt.speaker_match import SPEAKER_MATCH_MIN_EVIDENCE_SECONDS, select_speaker_match
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL

logger = logging.getLogger(__name__)
MAX_SEGMENTS = 256
# Shared by all three variants, including receipt construction.
MAX_SECONDS = 0.30
OUTCOMES = frozenset(
    {
        'owner_same',
        'owner_gained',
        'owner_lost',
        'owner_changed_segments',
        'mixed_proxy',
        'incumbent_mixed_proxy',
        'incumbent_owner_fragmented',
        'owner_fragmented',
        'groups_same',
        'groups_down_1_4',
        'groups_down_5_plus',
        'groups_up_1_4',
        'groups_up_5_plus',
        'correction_agreed',
        'correction_disagreed',
        'correction_negative_skipped',
        'error',
        'budget',
        'missing_provenance',
        'limit',
    }
)


def _shadow_counter() -> Counter:
    try:
        return Counter(
            'omi_speaker_grouping_shadow_total',
            'Cached-evidence grouping comparisons and corrections',
            ['variant', 'outcome'],
        )
    except ValueError:
        collectors = REGISTRY._names_to_collectors  # pyright: ignore[reportPrivateUsage]
        collector = collectors['omi_speaker_grouping_shadow_total']
        return cast(Counter, collector)


SHADOW_TOTAL = _shadow_counter()


def count(variant: str, outcome: str, amount: int = 1) -> None:
    if variant not in VARIANTS or outcome not in OUTCOMES:
        raise ValueError('unbounded grouping label')
    SHADOW_TOTAL.labels(variant=variant, outcome=outcome).inc(amount)


def provider_key(segment: TranscriptSegment) -> tuple[str, int] | None:
    original = segment.provider_speaker
    if original is not None:
        if original.get('id', -1) < 0 or not original.get('scope'):
            return None
        return (f"{original.get('provider') or 'unknown'}\0{original['scope']}", original['id'])
    scope = segment.speaker_id_scope
    if (
        not scope
        or scope.startswith(('conversation:', 'legacy-conversation:'))
        or segment.speaker_id == OMI_SPEAKER_ID_SENTINEL
        or segment.speaker_id is None
        or segment._speaker_id_synthesized  # pyright: ignore[reportPrivateUsage]
    ):
        return None
    return (f'{segment.stt_provider or "unknown"}\0{scope}', segment.speaker_id)


def decisions_for(
    conversation: Conversation, resolution: SpeakerResolution, receipt: Mapping[str, Any]
) -> dict[str, str]:
    # Exercise the actual projection and receipt policy, including preserved capture
    # identities and segment-level edits; no hypothetical label can outrank manual.
    from utils.conversations.speaker_resolution import apply_speaker_resolution

    projected = conversation.model_copy(
        update={'transcript_segments': [s.model_copy() for s in conversation.transcript_segments]}
    )
    apply_speaker_resolution(
        projected,
        resolution.speaker_ids,
        resolution.voice_identities,
        resolution.voice_identity_statuses,
        owner_voiceprint_available=resolution.owner_voiceprint_available,
        contradicted_segment_ids=resolution.contradicted_segment_ids,
    )
    fields = (
        'id',
        'speaker_id',
        'speaker_id_scope',
        'is_user',
        'person_id',
        'speaker_label_source',
        'speaker_identity_status',
        'speaker_match_source',
    )
    rows = apply_manual_assignments(
        [{field: getattr(s, field) for field in fields} for s in projected.transcript_segments], dict(receipt)
    )
    return {
        s['id']: 'user' if s.get('is_user') else f"person:{s['person_id']}" if s.get('person_id') else 'unknown'
        for s in rows
        if s.get('id')
    }


def _proxies(
    segments: list[TranscriptSegment],
    resolution: SpeakerResolution,
    keys: Mapping[str, tuple[str, int]],
    vectors: Mapping[str, Any],
    seconds: Mapping[str, float],
    prints: Mapping[str, Any],
) -> tuple[int, int]:
    normalized = {sid: vector for sid, raw in vectors.items() if (vector := unit_voice_vector(raw)) is not None}
    by_provider = defaultdict(list)
    for s in segments:
        if s.id in normalized and s.id in keys:
            by_provider[keys[s.id]].append(s)
    owner_groups = {key for key, identity in resolution.voice_identities.items() if identity.is_user}
    mixed = 0
    fragmented = 0
    for members in by_provider.values():
        evidence = sum(seconds.get(s.id, 0) for s in members)
        vector = unit_voice_vector(sum((normalized[s.id] * max(s.end - s.start, 1e-3) for s in members)))
        if vector is None or evidence < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS:
            continue  # Missing evidence is not a rejection.
        decision = select_speaker_match(
            {k: float(1 - np.dot(vector, p)) for k, p in prints.items()}, threshold=VOICE_MATCH_THRESHOLD
        )
        if decision.person_id != OWNER_IDENTITY:
            mixed += int(any(resolution.speaker_ids.get(s.id) in owner_groups for s in members))
    # Individually owner-like groups below the acceptance floor: fragmentation proxy,
    # never a new owner decision and never evidence for linking.
    by_group = defaultdict(list)
    for s in segments:
        if s.id in normalized and s.id in resolution.speaker_ids:
            by_group[resolution.speaker_ids[s.id]].append(s)
    for members in by_group.values():
        evidence = sum(seconds.get(s.id, 0) for s in members)
        vector = unit_voice_vector(sum((normalized[s.id] * max(s.end - s.start, 1e-3) for s in members)))
        if vector is not None and evidence < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS:
            decision = select_speaker_match(
                {k: float(1 - np.dot(vector, p)) for k, p in prints.items()}, threshold=VOICE_MATCH_THRESHOLD
            )
            fragmented += int(decision.person_id == OWNER_IDENTITY)
    return mixed, fragmented


def compare_and_select(
    uid: str,
    conversation: Conversation,
    incumbent: SpeakerResolution,
    vectors: Mapping[str, Any],
    *,
    manual_speakers: Mapping[int, Identity],
    voiceprints: Mapping[str, Any],
    embedding_seconds: Mapping[str, float],
    abstained_segment_ids: set[str],
    receipt: Mapping[str, Any],
) -> SpeakerResolution:
    """Failures cannot escape into finalization or replace the incumbent."""
    for segment in conversation.transcript_segments:
        segment.speaker_grouping_shadow = None
        segment.speaker_grouping_shadow_expires_at = None
    config = configuration(uid)
    if not config.shadow and config.mode == 'incumbent':
        return incumbent
    variants = VARIANTS if config.shadow else (config.mode,)
    selected = incumbent
    deadline = time.monotonic() + MAX_SECONDS
    try:
        segments = conversation.transcript_segments
        if len(segments) > MAX_SEGMENTS:
            raise OverflowError('limit')
        keys = {s.id: key for s in segments if s.id and (key := provider_key(s)) is not None}
        if any(
            s.id not in keys
            for s in segments
            if s.speaker_id != OMI_SPEAKER_ID_SENTINEL
            and s.id not in abstained_segment_ids
            and s.speaker_id not in manual_speakers
        ):
            raise LookupError('missing provenance')
        baseline = decisions_for(conversation, incumbent, receipt)
        before = {sid for sid, token in baseline.items() if token == 'user'}
        prints = {k: v for k, p in voiceprints.items() if (v := unit_voice_vector(p)) is not None}
        base_mixed, base_fragments = _proxies(segments, incumbent, keys, vectors, embedding_seconds, prints)
        pending = []
        for variant in variants:
            if time.monotonic() >= deadline:
                raise TimeoutError('grouping budget')
            result = resolve_conversation_speakers(
                segments,
                vectors,
                manual_speakers=manual_speakers,
                voiceprints=voiceprints,
                embedding_seconds=embedding_seconds,
                abstained_segment_ids=abstained_segment_ids,
                grouping=variant,
                provider_keys=keys,
                cross_scope_threshold=config.cross_scope_threshold,
                grouping_deadline=deadline,
            )
            if result is None:
                raise ValueError('no grouping')
            decisions = decisions_for(conversation, result, receipt)
            after = {sid for sid, token in decisions.items() if token == 'user'}
            gained, lost = len(after - before), len(before - after)
            mixed, fragmented = _proxies(segments, result, keys, vectors, embedding_seconds, prints)
            groups = len(set(result.speaker_ids.values()))
            base_groups = len(set(incumbent.speaker_ids.values()))
            delta = groups - base_groups
            bucket = (
                'groups_same'
                if delta == 0
                else f"groups_{'up' if delta > 0 else 'down'}_{'1_4' if abs(delta) <= 4 else '5_plus'}"
            )
            outcome = (
                'owner_same'
                if not gained and not lost
                else 'owner_changed_segments' if gained and lost else 'owner_gained' if gained else 'owner_lost'
            )
            pending.append(
                (
                    variant,
                    result,
                    decisions,
                    dict(
                        variant=variant,
                        outcome=outcome,
                        owner_gained_segments=gained,
                        owner_lost_segments=lost,
                        groups=groups,
                        incumbent_groups=base_groups,
                        group_delta=bucket,
                        mixed_proxy=mixed,
                        incumbent_mixed_proxy=base_mixed,
                        owner_fragmented=fragmented,
                        incumbent_owner_fragmented=base_fragments,
                    ),
                )
            )
        if time.monotonic() >= deadline:
            raise TimeoutError('grouping budget')
        # Publish only a complete comparison. No partial receipt survives failure.
        for variant, result, decisions, summary in pending:
            if variant == config.mode:
                selected = result
            if not config.shadow:
                continue
            count(variant, summary['outcome'])
            count(variant, summary['group_delta'])
            count(variant, 'incumbent_mixed_proxy', base_mixed)
            count(variant, 'incumbent_owner_fragmented', base_fragments)
            count(variant, 'mixed_proxy', summary['mixed_proxy'])
            count(variant, 'owner_fragmented', summary['owner_fragmented'])
            providers = sorted({s.stt_provider or 'unknown' for s in segments})
            source = getattr(conversation.source, 'value', conversation.source)
            surface = surface_label(
                {
                    'source': conversation.source,
                    'transcript_segments': [
                        {'speaker_id_scope': (s.provider_speaker or {}).get('scope', s.speaker_id_scope)}
                        for s in segments
                    ],
                }
            )
            logger.info(
                'event=speaker_grouping_shadow uid=%s conversation=%s provider=%s source=%s surface=%s summary=%s',
                uid,
                conversation.id,
                sanitize(providers),
                sanitize(source),
                surface,
                json.dumps(summary, separators=(',', ':')),
            )
            for segment in segments:
                if segment.id in decisions:
                    segment.speaker_grouping_shadow = {
                        **(segment.speaker_grouping_shadow or {}),
                        variant: decisions[segment.id],
                    }
                    if config.detailed:
                        token = decisions[segment.id]
                        logger.info(
                            'event=speaker_grouping_shadow_segment uid=%s conversation=%s variant=%s segment=%s decision=%s',
                            uid,
                            conversation.id,
                            variant,
                            segment.id,
                            'person' if token.startswith('person:') else 'owner' if token == 'user' else token,
                        )
        return selected
    except Exception as error:
        reason = (
            'budget'
            if isinstance(error, TimeoutError)
            else (
                'limit'
                if isinstance(error, OverflowError)
                else 'missing_provenance' if isinstance(error, LookupError) else 'error'
            )
        )
        for segment in conversation.transcript_segments:
            segment.speaker_grouping_shadow = None
            segment.speaker_grouping_shadow_expires_at = None
        try:
            for variant in variants:
                count(variant, reason)
            record_fallback(
                component='other',
                from_mode='speaker_grouping',
                to_mode='incumbent',
                reason='other',
                outcome='recovered',
                log=logger,
            )
        except Exception:
            logger.warning('event=speaker_grouping_shadow outcome=telemetry_error')
        logger.warning(
            'event=speaker_grouping_shadow uid=%s conversation=%s outcome=%s exception_type=%s',
            uid,
            conversation.id,
            reason,
            type(error).__name__,
        )
        return incumbent


def record_correction(raw: Mapping[str, Any], resolved: list[str]) -> None:
    """Score committed edits against the predictions frozen before the edit.

    This runs after the existing assignment transaction; it never teaches or
    modifies a receipt and counts only explicitly selected surviving segments.
    """
    try:
        selected = set(resolved)
        receipt = raw.get('manual_speaker_assignments') or {}
        rejected = manual_rejected_speakers(receipt)
        for segment in raw.get('transcript_segments') or []:
            if segment.get('id') not in selected:
                continue
            decision = manual_assignment_decision(segment, receipt, rejected)
            negative = bool(decision and decision.get('rejection'))
            target = (
                'user'
                if segment.get('is_user')
                else f"person:{segment['person_id']}" if segment.get('person_id') else 'unknown'
            )
            for variant, token in (segment.get('speaker_grouping_shadow') or {}).items():
                if variant in VARIANTS:
                    outcome = (
                        'correction_negative_skipped'
                        if negative
                        else 'correction_agreed' if token == target else 'correction_disagreed'
                    )
                    count(variant, outcome)
    except Exception as error:
        record_fallback(
            component='other',
            from_mode='speaker_grouping',
            to_mode='incumbent',
            reason='other',
            outcome='recovered',
            log=logger,
        )
        logger.warning('event=speaker_grouping_correction outcome=error exception_type=%s', type(error).__name__)

"""Bounded, opt-in detail translation after the owning route has authorized a read."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Callable

from config.translation import resolve_ondemand_config, resolve_translation_profile, viewed_translation_profile
from database import conversations as conversations_db
from database import users as users_db
from database.translation_admission import release_translation, reservation_is_current, reserve_translation
from utils.translation import VIEWED_REST_CAPACITY, TranslationService, TranslationStatus
from utils.translation_cache import should_persist_translation
from utils.translation_core.planner import TranslationMode
from utils.translation_language import TranslationNeed, classify_translation_need
from utils.transcribe_decisions import is_translation_target


def _revision(segments: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for segment in segments:
        digest.update(str(segment.get('id', '')).encode('utf-8'))
        digest.update(b'\0')
        digest.update(str(segment.get('text', '')).encode('utf-8'))
        digest.update(b'\0')
    return digest.hexdigest()


def _materialization_revision(conversation: dict[str, Any], segments: list[dict[str, Any]]) -> str:
    value = [conversation.get('translation_materializations'), [s.get('translations') for s in segments]]
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode('utf-8')).hexdigest()


def _cursor_secret(uid: str) -> bytes:
    return hmac.new(os.environ['ENCRYPTION_SECRET'].encode('utf-8'), uid.encode('utf-8'), hashlib.sha256).digest()


def _encode_cursor(uid: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
    signed = data + hmac.new(_cursor_secret(uid), data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signed).decode('ascii').rstrip('=')


def _decode_cursor(uid: str, cursor: str) -> dict[str, Any]:
    if len(cursor) > 2048:
        raise ValueError('Invalid translation cursor')
    try:
        signed = base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4))
        data, signature = signed[:-32], signed[-32:]
        if not hmac.compare_digest(signature, hmac.new(_cursor_secret(uid), data, hashlib.sha256).digest()):
            raise ValueError('Invalid translation cursor')
        payload = json.loads(data)
        if not isinstance(payload, dict) or type(payload.get('index')) is not int or payload['index'] < 0:
            raise ValueError('Invalid translation cursor')
        return payload
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        raise ValueError('Invalid translation cursor') from error


def translate_open_page(
    uid: str,
    conversation: dict[str, Any],
    cursor: str | None = None,
    *,
    service: TranslationService | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[dict[str, Any], str, str | None]:
    """Return the same detail shape, a status, and an optional signed cursor."""
    config = resolve_ondemand_config()
    if not config.onopen_enabled or not config.admits(uid):
        return conversation, 'unavailable', None
    if conversation.get('deleted') or conversation.get('is_locked'):
        return conversation, 'unavailable', None
    target = users_db.get_user_language_preference(uid)
    if not target or not is_translation_target(target):
        return conversation, 'unavailable', None
    if not config.spend_configured:
        return conversation, 'deferred', None
    conversation_id = str(conversation.get('id') or '')
    segments = conversation.get('transcript_segments')
    if not conversation_id or not isinstance(segments, list):
        return conversation, 'unavailable', None
    # Selection itself must respect the request deadline (Luna R3): scanning a
    # very long transcript for revision hashing and page selection is bounded
    # here so total on-open work stays within the configured budget. Work past
    # the bound continues through the signed cursor.
    scan_deadline = clock() + config.deadline_seconds
    scan_cap = max(config.max_segments * 8, 400)
    revision = _revision(segments[:scan_cap])
    materialization_revision = _materialization_revision(conversation, segments[:scan_cap])
    policy = 'viewed_v1' if config.gemini_enabled else 'legacy'
    start = 0
    stale_cursor = False
    if cursor:
        payload = _decode_cursor(uid, cursor)
        if (
            payload.get('id'),
            payload.get('target'),
            payload.get('revision'),
            payload.get('policy'),
            payload.get('materialization_revision'),
        ) == (
            conversation_id,
            target,
            revision,
            policy,
            materialization_revision,
        ):
            start = min(payload['index'], len(segments))
        else:
            stale_cursor = True
    deadline = min(clock() + config.deadline_seconds, scan_deadline)
    selected: list[tuple[int, dict[str, Any]]] = []
    chars = 0
    next_index = len(segments)
    oversized = False
    deferred_index: int | None = None
    scan_bounded = min(len(segments), start + scan_cap)
    for index in range(start, scan_bounded):
        if clock() >= deadline:
            next_index = index
            break
        segment = segments[index]
        if not isinstance(segment, dict) or not isinstance(segment.get('text'), str) or not segment.get('id'):
            continue
        text = segment['text']
        if conversations_db.translation_materialization_is_current(uid, conversation, segment, target, policy):
            continue
        need = classify_translation_need(text, target, is_stable=True)
        if need == TranslationNeed.SKIP:
            continue
        if need == TranslationNeed.DEFER:
            deferred_index = index if deferred_index is None else min(deferred_index, index)
            continue
        if len(text) > config.max_chars:
            next_index = index
            oversized = True
            break
        if len(selected) >= config.max_segments or chars + len(text) > config.max_chars:
            next_index = index
            break
        selected.append((index, segment))
        chars += len(text)

    def make_cursor(index: int) -> str:
        return _encode_cursor(
            uid,
            {
                'id': conversation_id,
                'target': target,
                'revision': revision,
                'policy': policy,
                'materialization_revision': _materialization_revision(conversation, segments),
                'index': index,
            },
        )

    if not selected:
        if oversized:
            return conversation, 'deferred', make_cursor(next_index)
        if deferred_index is not None:
            return conversation, 'deferred', make_cursor(deferred_index)
        if next_index < len(segments) or stale_cursor:
            return conversation, 'partial', make_cursor(next_index)
        return conversation, 'complete', None
    if clock() >= deadline:
        return conversation, 'deferred', make_cursor(selected[0][0])
    selected_text = [(str(segment['id']), segment['text']) for _, segment in selected]
    source_revision = hashlib.sha256(repr(selected_text).encode('utf-8')).hexdigest()
    reservation, reason = reserve_translation(
        uid,
        conversation_id,
        target,
        source_revision,
        policy,
        chars + config.max_output_tokens * 4,
        config.uid_daily_chars,
        config.global_daily_chars,
        provider_deadline_seconds=config.deadline_seconds,
    )
    if reservation is None:
        return conversation, 'deferred' if reason != 'redis_unavailable' else 'unavailable', make_cursor(selected[0][0])
    actual_chars = chars
    failed = False
    try:
        profile = viewed_translation_profile(resolve_translation_profile(), config) if policy == 'viewed_v1' else None
        rest_slot = False
        if profile is not None:
            rest_slot = VIEWED_REST_CAPACITY.acquire(blocking=False)
            if not rest_slot:
                return conversation, 'deferred', make_cursor(selected[0][0])
        try:
            outcomes = (service or TranslationService()).translate_outcomes(
                target, selected_text, mode=TranslationMode.whole_text, profile=profile
            )
        finally:
            if rest_slot:
                VIEWED_REST_CAPACITY.release()
        for (index, segment), outcome in zip(selected, outcomes):
            if clock() >= deadline or not reservation_is_current(reservation):
                failed = True
                next_index = min(next_index, index)
                break
            if outcome.status != TranslationStatus.translated or not should_persist_translation(
                segment['text'], outcome.text, outcome.detected_language, target
            ):
                failed = True
                next_index = min(next_index, index)
                continue
            actual_chars += len(outcome.text)
            committed = conversations_db.materialize_translation(
                uid,
                conversation_id,
                str(segment['id']),
                segment['text'],
                target,
                outcome.text,
                policy_version=policy,
                admission_kind='rest',
                reservation=reservation,
            )
            if committed is None:
                failed = True
                next_index = min(next_index, index)
            else:
                segments[index] = committed
        if len(outcomes) != len(selected):
            failed = True
            next_index = min(next_index, selected[0][0])
    except Exception:
        failed = True
        next_index = min(next_index, selected[0][0])
    finally:
        release_translation(reservation, actual_chars)
    if failed:
        return conversation, 'deferred', make_cursor(next_index)
    if deferred_index is not None:
        return conversation, 'deferred', make_cursor(deferred_index)
    if next_index < len(segments) or stale_cursor:
        return conversation, 'partial', make_cursor(next_index)
    return conversation, 'complete', None

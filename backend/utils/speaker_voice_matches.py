"""Read-only, deadline-bounded historical matches using cached voice evidence."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from math import isfinite
from typing import Callable, TypeVar

import numpy as np

from database import conversations as conversations_db
from database import users as users_db
from database import voice_profiles as voice_profiles_db
from models.speaker_labels import VoiceMatch, VoiceMatchesResponse
from models.transcript_segment import legacy_conversation_segment_id
from utils.conversations.speaker_resolution import decode_cache
from utils.executors import db_executor, run_blocking, storage_executor
from utils.manual_speaker_assignments import manual_rejected_speakers
from utils.other.storage import download_speaker_embedding_cache
from utils.speaker_permissions import named_speaker_prompts_allowed
from utils.speaker_tag_prompts.selection import MAX_CLIP_SECONDS, speaker_id_of
from utils.stt.conversation_speakers import (
    MIN_EMBED_SECONDS,
    SPEAKER_MATCH_MARGIN,
    SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
    VOICE_MATCH_THRESHOLD,
    select_speaker_match,
    unit_voice_vector,
    voice_cosine_distance,
)
from utils.stt.voiceprints import usable_person_voiceprint
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL

LOOKBACK = timedelta(days=30)
MAX_CONVERSATIONS = 25
MAX_MATCHES = 5
SCAN_SECONDS = 3.0
T = TypeVar('T')


async def _read(executor: ThreadPoolExecutor, call: Callable[[], T], deadline: float) -> T:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return await asyncio.wait_for(run_blocking(executor, call), timeout=remaining)


def _started_at(conversation: dict) -> datetime | None:
    return voice_profiles_db.as_utc(conversation.get('started_at'))


def _ignored_voices(uid: str) -> set:
    return voice_profiles_db.ignored_voice_keys(voice_profiles_db.get_tag_prompt_state(uid))


def _recent_conversations(uid: str, now: datetime) -> list[dict]:
    conversations = conversations_db.get_conversations(
        uid, limit=MAX_CONVERSATIONS, start_date=now - LOOKBACK, end_date=now
    )
    # The decoded helper queries the existing created_at index. Apply the
    # started_at window and newest-first order to its bounded result here.
    eligible = [
        conversation
        for conversation in conversations[:MAX_CONVERSATIONS]
        if not conversation.get('deleted')
        and not conversation.get('discarded')
        and not conversation.get('is_locked')
        and conversation.get('status') == 'completed'
        and (started := _started_at(conversation)) is not None
        and now - LOOKBACK <= started <= now
    ]
    eligible.sort(key=lambda conversation: _started_at(conversation) or now, reverse=True)
    return eligible


def _conversation_matches(
    uid: str,
    conversation: dict,
    person_id: str,
    voiceprint: np.ndarray,
    ignored: set,
    deadline: float,
    limit: int,
    competitors: dict[str, np.ndarray],
) -> list[VoiceMatch]:
    """One storage worker; never compute embeddings, download audio, or write."""
    conversation_id = conversation['id']
    receipt = conversation.get('manual_speaker_assignments') or {}
    decided_speakers = set(str(key) for key in (receipt.get('speakers') or {}))
    decided_speakers.update(str(key) for key in manual_rejected_speakers(receipt))
    decided_segments = set(receipt.get('segments') or {})
    voices: dict[int, list[dict]] = {}
    for index, raw in enumerate(conversation.get('transcript_segments') or []):
        if time.monotonic() >= deadline:
            return []
        segment = dict(raw)
        segment['id'] = segment.get('id') or legacy_conversation_segment_id(conversation_id, index)
        voices.setdefault(speaker_id_of(segment), []).append(segment)
    candidates = {
        speaker_id: segments
        for speaker_id, segments in voices.items()
        if speaker_id >= 0
        and speaker_id != OMI_SPEAKER_ID_SENTINEL
        and str(speaker_id) not in decided_speakers
        and voice_profiles_db.ignored_voice_key(conversation_id, speaker_id) not in ignored
        and all(
            not segment.get('is_user') and segment.get('person_id') is None and segment['id'] not in decided_segments
            for segment in segments
        )
    }
    if not candidates or time.monotonic() >= deadline:
        return []
    cache = decode_cache(download_speaker_embedding_cache(uid, conversation_id))
    matches = []
    for speaker_id, segments in candidates.items():
        if time.monotonic() >= deadline:
            break
        weighted = []
        evidence = 0.0
        for segment in segments:
            if time.monotonic() >= deadline:
                return matches
            cached = cache.get(segment['id'])
            if cached is None:
                continue
            duration, raw_vector = cached
            if not isfinite(duration) or duration < MIN_EMBED_SECONDS:
                continue
            vector = unit_voice_vector(raw_vector)
            if vector is None or vector.shape != voiceprint.shape:
                continue
            weighted.append(vector * duration)
            evidence += duration
        if evidence < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS:
            continue
        pooled = unit_voice_vector(np.sum(weighted, axis=0))
        if pooled is None:
            continue
        distances = {
            identity: voice_cosine_distance(pooled, vector)
            for identity, vector in competitors.items()
            if vector.shape == pooled.shape
        }
        distances[person_id] = voice_cosine_distance(pooled, voiceprint)
        decision = select_speaker_match(distances, threshold=VOICE_MATCH_THRESHOLD)
        if decision.person_id != person_id:
            continue
        distance = decision.best_distance
        durations = [max(0.0, float(s.get('end') or 0) - float(s.get('start') or 0)) for s in segments]
        longest = segments[max(range(len(segments)), key=lambda index: durations[index])]
        clip_start = max(0.0, float(longest.get('start') or 0))
        clip_end = min(float(longest.get('end') or 0), clip_start + MAX_CLIP_SECONDS)
        if clip_end <= clip_start:
            continue
        matches.append(
            VoiceMatch(
                conversation_id=conversation_id,
                title=(conversation.get('structured') or {}).get('title') or '',
                started_at=conversation['started_at'],
                speaker_id=speaker_id,
                talk_seconds=sum(durations),
                segment_ids=[segment['id'] for segment in segments],
                clip_start=clip_start,
                clip_end=clip_end,
                match_level='strong' if distance < VOICE_MATCH_THRESHOLD - SPEAKER_MATCH_MARGIN else 'likely',
            )
        )
        if len(matches) >= limit:
            break
    return matches


def _competing_voiceprints(uid: str) -> dict[str, np.ndarray]:
    """Called only after the request entitlement; include owner and usable people."""
    prints = {}
    # 'user' is the owner identity that select_speaker_match reserves.
    competitors = [('user', users_db.get_user_speaker_embedding(uid))]
    competitors += [(person.get('id'), usable_person_voiceprint(person)) for person in users_db.get_people(uid) or []]
    for identity, raw in competitors:
        if raw is None:
            continue
        try:
            vector = unit_voice_vector(raw)
        except (TypeError, ValueError):
            # One unusable stored embedding must not 500 the whole scan.
            continue
        if vector is not None:
            prints[identity] = vector
    return prints


async def find_person_voice_matches(uid: str, person_id: str) -> VoiceMatchesResponse:
    deadline = time.monotonic() + SCAN_SECONDS
    now = datetime.now(timezone.utc)
    matches: list[VoiceMatch] = []
    try:
        person = await _read(db_executor, partial(users_db.get_person, uid, person_id), deadline)
        if person is None:
            raise LookupError('Person not found')
        if not await _read(db_executor, partial(named_speaker_prompts_allowed, uid), deadline):
            return VoiceMatchesResponse()
        raw_print = usable_person_voiceprint(person)
        if raw_print is None:
            return VoiceMatchesResponse()
        voiceprint = unit_voice_vector(raw_print)
        if voiceprint is None:
            return VoiceMatchesResponse()
        competitors = await _read(db_executor, partial(_competing_voiceprints, uid), deadline)
        ignored = await _read(db_executor, partial(_ignored_voices, uid), deadline)
        conversations = await _read(db_executor, partial(_recent_conversations, uid, now), deadline)
        for conversation in conversations:
            found = await _read(
                storage_executor,
                partial(
                    _conversation_matches,
                    uid,
                    conversation,
                    person_id,
                    voiceprint,
                    ignored,
                    deadline,
                    MAX_MATCHES - len(matches),
                    competitors,
                ),
                deadline,
            )
            matches.extend(found)
            if len(matches) >= MAX_MATCHES:
                break
    except TimeoutError:
        # Cancelling the await cannot kill an already-running SDK call. That
        # leaf read can finish, but cannot start another conversation scan.
        pass
    return VoiceMatchesResponse(matches=matches)

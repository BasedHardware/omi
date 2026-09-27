"""Speaker tag prompts: serve a small daily set and apply the user's answers.

Answers reuse the manual speaker-assignment transaction (the same receipt the
transcript "Tag speaker" sheet writes), so a prompt answer and a hand edit are
indistinguishable downstream. Voice samples follow the existing quality gates:
other people through ``extract_speaker_samples`` (only when the user allows
saving other people's voices), the owner through a clip that must pass the same
transcription check before it is pooled into the owner's voiceprint.
"""

import asyncio
import hashlib
import json
import logging
import threading
import time
import uuid
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import numpy as np

from database import conversations as conversations_db
from database import redis_db
from database import users as users_db
from database import voice_profiles as voice_profiles_db
from models.speaker_tag_prompts import (
    SpeakerTagPromptAnswer,
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptAnswerResponse,
    SpeakerTagPromptKind,
    SpeakerTagPromptOrigin,
    SpeakerTagPromptQualityOutcome,
    SpeakerTagPromptsResponse,
)
from utils.manual_speaker_assignments import teaching_segment_ids
from utils.text_utils import compute_text_containment
from utils.observability.speaker_tag_prompts import (
    SPEAKER_TAG_PROMPT_ANSWERS,
    SPEAKER_TAG_PROMPT_QUALITY,
    SPEAKER_TAG_PROMPT_REQUESTS,
    SPEAKER_TAG_PROMPT_SETS,
    SPEAKER_TAG_PROMPT_VOICE_SAMPLES,
    SPEAKER_TAG_PROMPTS_SERVED,
    SPEAKER_TAG_PROMPTS_SKIPPED,
    VOICE_PROFILE_SETTING_CHANGES,
)
from utils.product_telemetry import emit_product_event
from utils.executors import (
    ExecutorSaturatedError,
    db_executor,
    run_blocking,
    speaker_tag_verify_executor,
    storage_executor,
    submit_with_context,
    sync_executor,
)
from utils.speaker_identification import extract_speaker_samples
from utils.speaker_sample import verify_and_transcribe_sample, verify_and_transcribe_sample_in_worker
from utils.speaker_tag_prompts.clips import CLIP_SAMPLE_RATE, conversation_clip_pcm, pcm_to_wav
from utils.speaker_tag_prompts.selection import (
    MAX_CLIP_SECONDS,
    MIN_CLIP_SECONDS,
    PROMPT_WINDOW,
    speaker_id_of,
    select_prompts,
)
from utils.stt.speaker_embedding import extract_embedding_from_bytes
from utils.stt.speaker_match import mean_embedding
from utils.subscription import is_paid_plan

logger = logging.getLogger(__name__)

SHOW_COOLDOWN = timedelta(hours=20)
DISMISSED_COOLDOWN = timedelta(days=7)
DISMISSALS_BEFORE_BACKOFF = 3
EMPTY_RECHECK = timedelta(hours=2)
RECENT_CONVERSATION_LIMIT = 30
VERIFY_CACHE_SECONDS = 12 * 60 * 60
VERIFY_ERROR_CACHE_SECONDS = 5 * 60
LIST_VERIFY_BUDGET_SECONDS = 8.0
MIN_EXPECTED_CONTAINMENT = 0.7
_inflight_verifications: Dict[str, Future[Optional[bytes]]] = {}
_inflight_lock = threading.RLock()

ScheduleTask = Callable[..., None]


class TagPromptForbidden(Exception):
    """The answer needs a feature the user's plan does not include."""


class TagPromptInvalid(Exception):
    """The answer does not fit the prompt."""


def named_speaker_prompts_allowed(uid: str) -> bool:
    """Naming other people follows the named speaker-ID entitlement (paid plans).

    "Is this you?" never calls this: the owner check is free for everyone.
    """
    subscription = users_db.get_user_valid_subscription(uid, provision=False)
    return bool(subscription and is_paid_plan(subscription.plan))


def _cooldown_until(state: Dict[str, Any]) -> Optional[datetime]:
    last_shown = voice_profiles_db.as_utc(state.get('last_shown_at'))
    if last_shown is None:
        return None
    streak = int(state.get('consecutive_dismissals') or 0)
    wait = DISMISSED_COOLDOWN if streak >= DISMISSALS_BEFORE_BACKOFF else SHOW_COOLDOWN
    return last_shown + wait


def _verification_cache_key(uid: str, conversation: Mapping[str, Any], start: float, end: float, text: str) -> str:
    # Hash every private field and the current audio manifest. Nothing identifying
    # or transcribed enters Redis keys or metrics labels in plaintext.
    payload = json.dumps(
        [uid, conversation['id'], start, end, text, conversation.get('audio_files'), conversation.get('language')],
        sort_keys=True,
        default=str,
    )
    return 'speaker_tag_clip_v2:' + hashlib.sha256(payload.encode()).hexdigest()


def clip_expected_text(conversation: Mapping[str, Any], start: float, end: float) -> str:
    """The overlapping single-speaker transcript used to check a requested clip."""
    relevant = [
        segment
        for segment in conversation.get('transcript_segments') or []
        if float(segment.get('start') or 0) < end and float(segment.get('end') or 0) > start
    ]
    if not relevant or len({speaker_id_of(segment) for segment in relevant}) != 1:
        return ''
    excerpts = []
    for segment in relevant:
        raw_text = (segment.get('text') or '').strip()
        words = raw_text.split()
        unspaced = len(words) == 1 and len(raw_text) >= 12
        if unspaced:
            words = list(raw_text)
        segment_start = float(segment.get('start') or 0)
        segment_end = float(segment.get('end') or 0)
        duration = segment_end - segment_start
        if duration > 0 and words:
            # Segment boundaries can be much wider than the cut. Keep a small
            # boundary margin for word timing uncertainty, but do not require a
            # ten-second clip to contain a whole minute-long segment.
            first = max(0, int((start - segment_start) / duration * len(words)) - 2)
            last = min(len(words), int((end - segment_start) / duration * len(words)) + 3)
            words = words[first:last]
        excerpts.append(''.join(words) if unspaced else ' '.join(words))
    return ' '.join(excerpts).strip()


def verified_clip_pcm(
    uid: str,
    conversation: Mapping[str, Any],
    start: float,
    end: float,
    expected_text: str,
    pcm: Optional[bytes] = None,
    verification_deadline: Optional[float] = None,
) -> Optional[bytes]:
    """Return playable PCM only after a matching transcription or cached verdict."""
    if not expected_text:
        SPEAKER_TAG_PROMPTS_SKIPPED.labels(reason='verify_failed').inc()
        return None
    if verification_deadline is not None and time.monotonic() >= verification_deadline:
        raise FutureTimeoutError()
    key = _verification_cache_key(uid, conversation, start, end, expected_text)
    cached = redis_db.get_generic_cache(key)
    try:
        pcm = pcm if pcm is not None else conversation_clip_pcm(uid, conversation, start, end)
    except Exception as error:
        logger.warning('speaker tag clip verification failed error_type=%s', type(error).__name__)
        SPEAKER_TAG_PROMPTS_SKIPPED.labels(reason='verify_error').inc()
        return None
    # A legacy file's encoded-size duration can overstate the decoded tail.
    # Reject a truncated cut even if its first seconds happen to transcribe.
    minimum_bytes = max(0, int((end - start - 0.02) * CLIP_SAMPLE_RATE)) * 2
    if not pcm or len(pcm) < minimum_bytes:
        SPEAKER_TAG_PROMPTS_SKIPPED.labels(reason='uncovered').inc()
        return None
    pcm_digest = hashlib.sha256(pcm).hexdigest()
    if verification_deadline is not None and time.monotonic() >= verification_deadline:
        raise FutureTimeoutError()
    if isinstance(cached, dict) and cached.get('pcm_sha256') == pcm_digest:
        if cached.get('valid') is False:
            SPEAKER_TAG_PROMPTS_SKIPPED.labels(reason=cached.get('reason', 'verify_failed')).inc()
            return None
        if cached.get('valid') is True:
            return pcm
    try:
        if verification_deadline is None:
            _transcript, valid, reason = asyncio.run(
                verify_and_transcribe_sample(
                    pcm_to_wav(pcm), CLIP_SAMPLE_RATE, expected_text, language=conversation.get('language')
                )
            )
        else:
            _transcript, valid, reason = verify_and_transcribe_sample_in_worker(
                pcm_to_wav(pcm), CLIP_SAMPLE_RATE, expected_text, conversation.get('language'), verification_deadline
            )
    except Exception:
        SPEAKER_TAG_PROMPTS_SKIPPED.labels(reason='verify_error').inc()
        redis_db.set_generic_cache(
            key, {'pcm_sha256': pcm_digest, 'valid': False, 'reason': 'verify_error'}, ttl=VERIFY_ERROR_CACHE_SECONDS
        )
        return None
    if verification_deadline is not None and time.monotonic() >= verification_deadline:
        raise FutureTimeoutError()
    if valid:
        valid = bool(_transcript) and compute_text_containment(expected_text, _transcript) >= MIN_EXPECTED_CONTAINMENT
    if not valid:
        is_error = reason.startswith('transcription_failed')
        SPEAKER_TAG_PROMPTS_SKIPPED.labels(reason='verify_error' if is_error else 'verify_failed').inc()
        redis_db.set_generic_cache(
            key,
            {'pcm_sha256': pcm_digest, 'valid': False, 'reason': 'verify_error' if is_error else 'verify_failed'},
            ttl=VERIFY_ERROR_CACHE_SECONDS if is_error else VERIFY_CACHE_SECONDS,
        )
        return None
    redis_db.set_generic_cache(key, {'pcm_sha256': pcm_digest, 'valid': True}, ttl=VERIFY_CACHE_SECONDS)
    return pcm


def _submit_list_verification(
    uid: str, conversation: Mapping[str, Any], start: float, end: float, expected_text: str, deadline: float
) -> Future[Optional[bytes]]:
    """Share identical checks and reject distinct work when the small pool is full."""
    key = _verification_cache_key(uid, conversation, start, end, expected_text)
    with _inflight_lock:
        existing = _inflight_verifications.get(key)
        if existing is not None:
            return existing
        future = submit_with_context(
            speaker_tag_verify_executor,
            verified_clip_pcm,
            uid,
            conversation,
            start,
            end,
            expected_text,
            verification_deadline=deadline,
        )
        _inflight_verifications[key] = future

        def clear(done: Future[Optional[bytes]]) -> None:
            with _inflight_lock:
                if _inflight_verifications.get(key) is done:
                    del _inflight_verifications[key]

        future.add_done_callback(clear)
        return future


def get_prompts(uid: str, now: Optional[datetime] = None) -> SpeakerTagPromptsResponse:
    now = voice_profiles_db.as_utc(now) or datetime.now(timezone.utc)
    settings, owner_has_voice = voice_profiles_db.get_voice_profile_context(uid)
    save_others = settings['save_other_voice_profiles']
    if not settings['speaker_tag_prompts_enabled']:
        SPEAKER_TAG_PROMPT_REQUESTS.labels(status='disabled').inc()
        return SpeakerTagPromptsResponse(status='disabled', save_other_voice_profiles=save_others)

    state = voice_profiles_db.get_tag_prompt_state(uid)
    first_time = not state.get('first_shown_at')
    cooldown_until = _cooldown_until(state)
    if cooldown_until and cooldown_until > now:
        SPEAKER_TAG_PROMPT_REQUESTS.labels(status='cooldown').inc()
        return SpeakerTagPromptsResponse(
            status='cooldown',
            first_time=first_time,
            save_other_voice_profiles=save_others,
            next_eligible_at=cooldown_until,
        )
    last_empty = voice_profiles_db.as_utc(state.get('last_empty_check_at'))
    if last_empty is not None and last_empty + EMPTY_RECHECK > now:
        SPEAKER_TAG_PROMPT_REQUESTS.labels(status='recently_checked').inc()
        return SpeakerTagPromptsResponse(
            status='no_candidates',
            first_time=first_time,
            save_other_voice_profiles=save_others,
            next_eligible_at=last_empty + EMPTY_RECHECK,
        )

    named_allowed = named_speaker_prompts_allowed(uid)
    conversations = conversations_db.get_conversations(
        # created_at >= started_at, so this existing indexed range is a superset of conversations that
        # started in the window; selection then applies the started_at bound.
        uid,
        limit=RECENT_CONVERSATION_LIMIT,
        start_date=now - PROMPT_WINDOW,
        end_date=now,
    )
    people = {person['id']: person.get('name') or '' for person in users_db.get_people(uid) if person.get('id')}
    deadline = time.monotonic() + LIST_VERIFY_BUDGET_SECONDS
    timed_out = False

    def verify_in_budget(conversation: Mapping[str, Any], prompt: Any, _expected: str) -> bool:
        nonlocal timed_out
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            return False
        try:
            future = _submit_list_verification(
                uid,
                conversation,
                prompt.clip_start,
                prompt.clip_end,
                clip_expected_text(conversation, prompt.clip_start, prompt.clip_end),
                deadline,
            )
            return future.result(timeout=remaining) is not None
        except FutureTimeoutError:
            timed_out = True
            return False
        except ExecutorSaturatedError:
            timed_out = True
            return False
        except Exception as error:
            logger.warning('speaker tag list verification failed error_type=%s', type(error).__name__)
            timed_out = True
            return False

    prompts = select_prompts(
        conversations,
        now=now,
        owner_has_voice=owner_has_voice,
        named_allowed=named_allowed,
        answered=voice_profiles_db.answered_prompt_ids(state, now),
        people=people,
        verify=verify_in_budget,
        on_skip=lambda reason: SPEAKER_TAG_PROMPTS_SKIPPED.labels(reason=reason).inc(),
    )
    if not prompts:
        if not timed_out:
            voice_profiles_db.mark_tag_prompts_empty(uid, now)
        SPEAKER_TAG_PROMPT_REQUESTS.labels(status='no_candidates').inc()
        return SpeakerTagPromptsResponse(
            status='no_candidates', first_time=first_time, save_other_voice_profiles=save_others
        )
    SPEAKER_TAG_PROMPT_REQUESTS.labels(status='ok').inc()
    for prompt in prompts:
        SPEAKER_TAG_PROMPTS_SERVED.labels(kind=prompt.kind.value).inc()
    return SpeakerTagPromptsResponse(prompts=prompts, first_time=first_time, save_other_voice_profiles=save_others)


def mark_shown(uid: str, prompt_count: int, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    first_time = voice_profiles_db.record_tag_prompts_shown(uid, now)
    SPEAKER_TAG_PROMPT_SETS.labels(event='shown').inc()
    emit_product_event(
        uid=uid,
        event='Speaker Tag Prompts Shown',
        properties={'prompt_count': prompt_count, 'first_time': first_time},
    )
    return first_time


def mark_dismissed(uid: str, now: Optional[datetime] = None) -> int:
    streak = voice_profiles_db.record_tag_prompts_dismissed(uid, now or datetime.now(timezone.utc))
    SPEAKER_TAG_PROMPT_SETS.labels(event='dismissed').inc()
    return streak


def update_settings(uid: str, updates: Dict[str, bool], source: Optional[str]) -> Dict[str, bool]:
    before = voice_profiles_db.get_voice_profile_settings(uid)
    voice_profiles_db.set_voice_profile_settings(uid, updates)
    after = {**before, **updates}
    for key, value in updates.items():
        if before.get(key) == value:
            continue
        VOICE_PROFILE_SETTING_CHANGES.labels(setting=key, enabled=str(value).lower(), source=source or 'settings').inc()
        emit_product_event(
            uid=uid,
            event='Voice Profile Setting Changed',
            properties={'setting': key, 'enabled': value, 'source': source or 'settings'},
        )
    return after


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------

_ALLOWED_ANSWERS = {
    SpeakerTagPromptKind.owner_check: {
        SpeakerTagPromptAnswer.me,
        SpeakerTagPromptAnswer.not_me,
        SpeakerTagPromptAnswer.person,
        SpeakerTagPromptAnswer.new_person,
        SpeakerTagPromptAnswer.someone_else,
        SpeakerTagPromptAnswer.skip,
    },
    SpeakerTagPromptKind.confirm_person: {
        SpeakerTagPromptAnswer.me,
        SpeakerTagPromptAnswer.person,
        SpeakerTagPromptAnswer.new_person,
        SpeakerTagPromptAnswer.someone_else,
        SpeakerTagPromptAnswer.skip,
    },
    SpeakerTagPromptKind.identify: {
        SpeakerTagPromptAnswer.me,
        SpeakerTagPromptAnswer.person,
        SpeakerTagPromptAnswer.new_person,
        SpeakerTagPromptAnswer.someone_else,
        SpeakerTagPromptAnswer.skip,
    },
}
_NAMED_ANSWERS = {SpeakerTagPromptAnswer.person, SpeakerTagPromptAnswer.new_person}


def quality_outcome(
    origin: SpeakerTagPromptOrigin,
    answer: SpeakerTagPromptAnswer,
    *,
    person_id: Optional[str],
    suggested_person_id: Optional[str],
    person_enrolled: bool,
) -> SpeakerTagPromptQualityOutcome:
    """Map one answer to a bounded quality observation (see models)."""
    Q = SpeakerTagPromptQualityOutcome
    if answer == SpeakerTagPromptAnswer.skip:
        return Q.skipped
    if origin == SpeakerTagPromptOrigin.auto_user:
        return Q.owner_auto_confirmed if answer == SpeakerTagPromptAnswer.me else Q.owner_auto_rejected
    if origin == SpeakerTagPromptOrigin.auto_person:
        if answer == SpeakerTagPromptAnswer.person and person_id and person_id == suggested_person_id:
            return Q.person_auto_confirmed
        return Q.person_auto_corrected
    if answer == SpeakerTagPromptAnswer.me:
        return Q.owner_missed
    if answer == SpeakerTagPromptAnswer.not_me:
        return Q.owner_unmatched_not_owner
    if answer in _NAMED_ANSWERS:
        return Q.person_missed_known if person_enrolled else Q.person_not_enrolled
    return Q.unknown_voice


def _resolve_person(uid: str, request: SpeakerTagPromptAnswerRequest) -> Tuple[str, Dict[str, Any]]:
    if request.answer == SpeakerTagPromptAnswer.person:
        if not request.person_id:
            raise TagPromptInvalid('person_id is required')
        found: Optional[Dict[str, Any]] = users_db.get_person(uid, request.person_id)
        if not found:
            raise LookupError('Person not found')
        return request.person_id, found
    name = (request.name or '').strip()
    if len(name) < 2:
        raise TagPromptInvalid('name is required')
    existing = users_db.get_person_by_name(uid, name)
    if existing:
        return existing['id'], existing
    now = datetime.now(timezone.utc)
    person_id = str(uuid.uuid4())
    person: Dict[str, Any] = {'id': person_id, 'name': name, 'created_at': now, 'updated_at': now}
    users_db.create_person(uid, person)
    return person_id, person


def apply_answer(
    uid: str,
    request: SpeakerTagPromptAnswerRequest,
    schedule: Optional[ScheduleTask] = None,
    now: Optional[datetime] = None,
) -> SpeakerTagPromptAnswerResponse:
    """Apply one answer. ``schedule(fn, **kwargs)`` runs slow voice work after the response."""
    now = now or datetime.now(timezone.utc)
    answer = request.answer
    if answer not in _ALLOWED_ANSWERS[request.kind]:
        raise TagPromptInvalid(f'{answer.value} is not a valid answer for {request.kind.value}')
    needs_named = request.kind != SpeakerTagPromptKind.owner_check or answer in _NAMED_ANSWERS
    if needs_named and not named_speaker_prompts_allowed(uid):
        raise TagPromptForbidden('Naming other people needs a paid plan')

    person_id: Optional[str] = None
    person_enrolled = False
    voice_sample_queued = False
    if answer in _NAMED_ANSWERS:
        person_id, person = _resolve_person(uid, request)
        person_enrolled = bool(person.get('speaker_embedding'))

    clears_auto_label = request.origin != SpeakerTagPromptOrigin.unnamed and answer in {
        SpeakerTagPromptAnswer.not_me,
        SpeakerTagPromptAnswer.someone_else,
    }
    if answer == SpeakerTagPromptAnswer.me:
        conversation, resolved = _assign(uid, request, is_user=True, person_id=None, train=False)
        if schedule is not None:
            assigned = set(resolved) & {s.get('id') for s in conversation.get('transcript_segments') or []}
            segment_ids = [sid for sid in request.segment_ids if sid in assigned]
            if segment_ids:
                schedule(
                    store_owner_voice_sample,
                    uid=uid,
                    conversation_id=request.conversation_id,
                    segment_ids=segment_ids,
                )
                voice_sample_queued = True
    elif person_id is not None:
        settings = voice_profiles_db.get_voice_profile_settings(uid)
        train = settings['save_other_voice_profiles']
        conversation, resolved = _assign(uid, request, is_user=False, person_id=person_id, train=train)
        if not train:
            SPEAKER_TAG_PROMPT_VOICE_SAMPLES.labels(target='person', outcome='disabled_by_user').inc()
        elif schedule is not None:
            schedule(
                extract_speaker_samples,
                uid=uid,
                person_id=person_id,
                conversation_id=request.conversation_id,
                segment_ids=teaching_segment_ids(conversation.get('transcript_segments') or [], resolved),
            )
            SPEAKER_TAG_PROMPT_VOICE_SAMPLES.labels(target='person', outcome='queued').inc()
            voice_sample_queued = True
    elif clears_auto_label:
        # The automatic label was wrong: record an explicit "not the owner / not them".
        _assign(uid, request, is_user=False, person_id=None, train=False)

    outcome = quality_outcome(
        request.origin,
        answer,
        person_id=person_id,
        suggested_person_id=request.suggested_person_id,
        person_enrolled=person_enrolled,
    )
    voice_profiles_db.record_tag_prompt_answered(uid, request.prompt_id, now)
    SPEAKER_TAG_PROMPT_ANSWERS.labels(kind=request.kind.value, answer=answer.value).inc()
    SPEAKER_TAG_PROMPT_QUALITY.labels(outcome=outcome.value).inc()
    emit_product_event(
        uid=uid,
        event='Speaker Tag Prompt Answered',
        properties={
            'kind': request.kind.value,
            'origin': request.origin.value,
            'answer': answer.value,
            'quality_outcome': outcome.value,
            'first_time': request.first_time,
            'voice_sample_queued': voice_sample_queued,
        },
    )
    return SpeakerTagPromptAnswerResponse(
        person_id=person_id, quality_outcome=outcome, voice_sample_queued=voice_sample_queued
    )


def _assign(
    uid: str,
    request: SpeakerTagPromptAnswerRequest,
    *,
    is_user: bool,
    person_id: Optional[str],
    train: bool,
) -> Tuple[Dict[str, Any], List[str]]:
    """Label the whole diarized speaker in that conversation, like "apply to all" in the tag sheet."""
    raw, resolved, _removed, _before = conversations_db.assign_conversation_speaker(
        uid,
        request.conversation_id,
        person_id=person_id,
        is_user=is_user,
        speaker_id=request.speaker_id,
        use_for_speech_training=train,
    )
    return raw, resolved


# ---------------------------------------------------------------------------
# Owner voice sample
# ---------------------------------------------------------------------------


def _pool(vectors: List[List[float]]) -> List[float]:
    centroid = mean_embedding([np.asarray(vector, dtype=np.float32).reshape(1, -1) for vector in vectors])
    return centroid.flatten().tolist()


def owner_clip_window(conversation: Dict[str, Any], segment_ids: List[str]) -> Optional[Tuple[float, float, str]]:
    """The confirmed stretch, if it is still the owner's and long enough: (start, end, text)."""
    wanted = set(segment_ids)
    chosen = [
        segment
        for segment in conversation.get('transcript_segments') or []
        if segment.get('id') in wanted and segment.get('is_user')
    ]
    if not chosen or len(chosen) != len(wanted):
        return None
    speaker_ids = {speaker_id_of(segment) for segment in chosen}
    if len(speaker_ids) != 1:
        return None
    speaker_id = speaker_ids.pop()
    chosen.sort(key=lambda segment: float(segment.get('start') or 0))
    start = float(chosen[0].get('start') or 0)
    end = max(float(segment.get('end') or 0) for segment in chosen)
    if end - start < MIN_CLIP_SECONDS:
        return None
    if end - start > MAX_CLIP_SECONDS:
        center = (start + end) / 2
        start, end = center - MAX_CLIP_SECONDS / 2, center + MAX_CLIP_SECONDS / 2
    others = [
        segment
        for segment in conversation.get('transcript_segments') or []
        if float(segment.get('start') or 0) < end
        and float(segment.get('end') or 0) > start
        and speaker_id_of(segment) != speaker_id
    ]
    if others:
        return None
    text = ' '.join(
        (segment.get('text') or '').strip()
        for segment in chosen
        # Overlapping, not contained: the quality gate checks the clip's words are contained in this
        # text, so a cropped long segment must still contribute its words.
        if float(segment.get('start') or 0) < end and float(segment.get('end') or 0) > start
    ).strip()
    if not text:
        return None
    return start, end, text


async def store_owner_voice_sample(uid: str, conversation_id: str, segment_ids: List[str]) -> str:
    """Verify a "That's me" clip and pool it into the owner's voiceprint. Returns the outcome label.

    The outcome is attributable: beyond the Prometheus counter, one log line
    names the outcome with the conversation id (never the uid). The
    2026-09-25 incident left a client-side "succeeded=true" answer with no
    owner_voice_confirmation and no trace beyond an unlabeled counter; the
    recording session id is not on this path (prompts are answered after the
    socket closed), so the conversation id is the join key.
    """
    outcome = 'error'
    try:
        conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not conversation:
            outcome = 'clip_not_clean'
            return outcome
        window = owner_clip_window(conversation, segment_ids)
        if window is None:
            outcome = 'clip_not_clean'
            return outcome
        start, end, text = window
        pcm = await run_blocking(storage_executor, conversation_clip_pcm, uid, conversation, start, end)
        if not pcm:
            outcome = 'no_audio'
            return outcome
        wav = pcm_to_wav(pcm)
        language = conversation.get('language') or await run_blocking(
            db_executor, users_db.get_user_language_preference, uid
        )
        _, is_valid, reason = await verify_and_transcribe_sample(wav, CLIP_SAMPLE_RATE, text, language=language)
        if not is_valid:
            outcome = 'transient_failure' if reason.startswith('transcription_failed') else 'rejected_quality'
            return outcome
        embedding = await run_blocking(sync_executor, extract_embedding_from_bytes, wav, 'owner_confirmation.wav')
        if not np.isfinite(embedding).all() or not np.any(embedding):
            outcome = 'rejected_embedding'
            return outcome
        await run_blocking(
            db_executor,
            voice_profiles_db.add_owner_voice_confirmation,
            uid,
            embedding.flatten().tolist(),
            _pool,
            conversation_id=conversation_id,
        )
        outcome = 'stored'
        return outcome
    except Exception as error:
        logger.error('speaker tag prompt owner sample failed error_type=%s', type(error).__name__)
        return outcome
    finally:
        SPEAKER_TAG_PROMPT_VOICE_SAMPLES.labels(target='owner', outcome=outcome).inc()
        logger.info(
            'speaker tag prompt owner sample outcome=%s conversation=%s',
            outcome,
            conversation_id,
        )

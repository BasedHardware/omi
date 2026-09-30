import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from models.speaker_tag_prompts import (
    SpeakerTagPromptAnswer as A,
    SpeakerTagPromptAnswerRequest,
    SpeakerTagPromptKind as K,
    SpeakerTagPromptOrigin as O,
    SpeakerTagPromptQualityOutcome as Q,
)
from utils import executors
from utils import speaker_sample
from utils.speaker_tag_prompts import service
from utils.stt import pre_recorded
from utils.executors import ExecutorSaturatedError, MonitoredThreadPoolExecutor

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


class World:
    def __init__(self, monkeypatch, *, paid=True, save_others=True, prompts_enabled=True, state=None):
        self.assignments = []
        self.scheduled = []
        self.answered = []
        self.events = []
        self.people = {'p1': {'id': 'p1', 'name': 'Sam', 'speaker_embedding': [0.1]}}
        self.created = []
        self.state = state or {}
        self.settings = {'speaker_tag_prompts_enabled': prompts_enabled, 'save_other_voice_profiles': save_others}
        db = service.voice_profiles_db
        monkeypatch.setattr(service, 'named_speaker_prompts_allowed', lambda uid: paid)
        monkeypatch.setattr(db, 'get_voice_profile_settings', lambda uid: dict(self.settings))
        monkeypatch.setattr(db, 'get_voice_profile_context', lambda uid: (dict(self.settings), True))
        monkeypatch.setattr(db, 'get_tag_prompt_state', lambda uid: dict(self.state))
        monkeypatch.setattr(db, 'record_tag_prompt_answered', lambda uid, pid, now: self.answered.append(pid))
        monkeypatch.setattr(db, 'mark_tag_prompts_empty', lambda uid, now: self.state.update(last_empty_check_at=now))
        monkeypatch.setattr(service.users_db, 'get_person', lambda uid, pid: self.people.get(pid))
        monkeypatch.setattr(service.users_db, 'get_person_by_name', lambda uid, name: None)
        monkeypatch.setattr(service.users_db, 'create_person', lambda uid, data: self.created.append(data) or data)
        monkeypatch.setattr(service.users_db, 'get_people', lambda uid: list(self.people.values()))
        monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: [])
        monkeypatch.setattr(
            service, 'emit_product_event', lambda **kwargs: self.events.append((kwargs['event'], kwargs['properties']))
        )

        def assign(uid, conversation_id, **kwargs):
            self.assignments.append(kwargs)
            segments = [{'id': 's1', 'start': 0, 'end': 9}, {'id': 's2', 'start': 9, 'end': 12}]
            return {'transcript_segments': segments}, ['s1', 's2'], [], []

        monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)

    def schedule(self, fn, **kwargs):
        self.scheduled.append((fn, kwargs))


def _request(kind, origin, answer, **extra):
    payload = dict(
        prompt_id='pid',
        kind=kind,
        origin=origin,
        conversation_id='c1',
        speaker_id=1,
        segment_ids=['s1'],
        answer=answer,
    )
    payload.update(extra)
    return SpeakerTagPromptAnswerRequest(**payload)


def test_thats_me_labels_owner_and_queues_owner_voice_sample(monkeypatch):
    world = World(monkeypatch, paid=False)
    response = service.apply_answer('u', _request(K.owner_check, O.unnamed, A.me), world.schedule, NOW)
    assert world.assignments == [
        {'person_id': None, 'is_user': True, 'speaker_id': 1, 'use_for_speech_training': False}
    ]
    assert world.scheduled[0][0] is service.store_owner_voice_sample
    assert response.voice_sample_queued and response.quality_outcome == Q.owner_missed
    assert world.answered == ['pid']
    name, properties = world.events[-1]
    assert name == 'Speaker Tag Prompt Answered'
    assert set(properties) == {'kind', 'origin', 'answer', 'quality_outcome', 'first_time', 'voice_sample_queued'}


def test_free_user_cannot_name_other_people(monkeypatch):
    world = World(monkeypatch, paid=False)
    with pytest.raises(service.TagPromptForbidden):
        service.apply_answer('u', _request(K.identify, O.unnamed, A.person, person_id='p1'), world.schedule, NOW)
    with pytest.raises(service.TagPromptForbidden):
        service.apply_answer('u', _request(K.owner_check, O.unnamed, A.new_person, name='Ana'), world.schedule, NOW)
    assert world.assignments == []


def test_naming_a_person_teaches_voice_when_allowed(monkeypatch):
    world = World(monkeypatch)
    response = service.apply_answer('u', _request(K.identify, O.unnamed, A.person, person_id='p1'), world.schedule, NOW)
    assert world.assignments[0]['person_id'] == 'p1' and world.assignments[0]['use_for_speech_training'] is True
    fn, kwargs = world.scheduled[0]
    assert fn is service.extract_speaker_samples and kwargs['segment_ids'] == ['s1', 's2']
    assert response.quality_outcome == Q.person_missed_known


def test_saving_other_voices_off_labels_without_teaching(monkeypatch):
    world = World(monkeypatch, save_others=False)
    response = service.apply_answer('u', _request(K.identify, O.unnamed, A.new_person, name='Ana'), world.schedule, NOW)
    assert world.created and world.created[0]['name'] == 'Ana'
    assert world.assignments[0]['use_for_speech_training'] is False
    assert world.scheduled == [] and not response.voice_sample_queued
    assert response.quality_outcome == Q.person_not_enrolled


def test_rejecting_an_automatic_label_clears_it(monkeypatch):
    world = World(monkeypatch)
    response = service.apply_answer('u', _request(K.owner_check, O.auto_user, A.not_me), world.schedule, NOW)
    assert world.assignments == [
        {'person_id': None, 'is_user': False, 'speaker_id': 1, 'use_for_speech_training': False}
    ]
    assert response.quality_outcome == Q.owner_auto_rejected


def test_unknown_voice_and_skip_write_nothing(monkeypatch):
    world = World(monkeypatch)
    service.apply_answer('u', _request(K.identify, O.unnamed, A.someone_else), world.schedule, NOW)
    service.apply_answer('u', _request(K.identify, O.unnamed, A.skip), world.schedule, NOW)
    assert world.assignments == [] and world.answered == ['pid', 'pid']


def test_invalid_answer_for_kind(monkeypatch):
    world = World(monkeypatch)
    with pytest.raises(service.TagPromptInvalid):
        service.apply_answer('u', _request(K.identify, O.unnamed, A.not_me), world.schedule, NOW)


@pytest.mark.parametrize(
    'origin,answer,person_id,suggested,enrolled,expected',
    [
        (O.auto_user, A.me, None, None, False, Q.owner_auto_confirmed),
        (O.auto_user, A.person, 'p1', None, True, Q.owner_auto_rejected),
        (O.auto_person, A.person, 'p1', 'p1', True, Q.person_auto_confirmed),
        (O.auto_person, A.person, 'p2', 'p1', True, Q.person_auto_corrected),
        (O.auto_person, A.me, None, 'p1', False, Q.person_auto_corrected),
        (O.unnamed, A.me, None, None, False, Q.owner_missed),
        (O.unnamed, A.not_me, None, None, False, Q.owner_unmatched_not_owner),
        (O.unnamed, A.person, 'p1', None, True, Q.person_missed_known),
        (O.unnamed, A.new_person, 'p9', None, False, Q.person_not_enrolled),
        (O.unnamed, A.someone_else, None, None, False, Q.unknown_voice),
        (O.auto_person, A.skip, None, 'p1', False, Q.skipped),
    ],
)
def test_quality_outcome_table(origin, answer, person_id, suggested, enrolled, expected):
    outcome = service.quality_outcome(
        origin, answer, person_id=person_id, suggested_person_id=suggested, person_enrolled=enrolled
    )
    assert outcome == expected


def test_prompts_respect_disabled_and_daily_cooldown(monkeypatch):
    world = World(monkeypatch, prompts_enabled=False)
    assert service.get_prompts('u', NOW).status == 'disabled'

    world = World(monkeypatch, state={'first_shown_at': NOW, 'last_shown_at': NOW - timedelta(hours=3)})
    response = service.get_prompts('u', NOW)
    assert response.status == 'cooldown' and response.first_time is False
    assert response.next_eligible_at == NOW - timedelta(hours=3) + service.SHOW_COOLDOWN


def test_repeated_dismissals_back_off_to_a_week(monkeypatch):
    world = World(monkeypatch, state={'last_shown_at': NOW - timedelta(days=2), 'consecutive_dismissals': 3})
    response = service.get_prompts('u', NOW)
    assert response.status == 'cooldown'
    assert response.next_eligible_at == NOW - timedelta(days=2) + service.DISMISSED_COOLDOWN


def test_empty_scan_is_remembered(monkeypatch):
    world = World(monkeypatch)
    first = service.get_prompts('u', NOW)
    assert first.status == 'no_candidates' and first.first_time is True
    calls = []
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *a, **k: calls.append(1) or [])
    second = service.get_prompts('u', NOW + timedelta(minutes=30))
    assert second.status == 'no_candidates' and calls == []
    assert world.state['last_empty_check_at'] == NOW


def test_owner_clip_window_keeps_text_of_a_long_segment_cropped_to_the_clip():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 30, 'is_user': True, 'speaker_id': 0, 'text': 'one long owner turn'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a']) == (10.0, 20.0, 'one long owner turn')


def test_clip_verification_cache_reuses_verdict_and_invalidates_on_audio_change(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    checks = []
    downloads = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(
        service,
        'conversation_clip_pcm',
        lambda *args: downloads.append(1) or b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5),
    )

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(expected_text)
        return ('one two three four five', True, 'ok')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    for _ in range(2):
        assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five')
    assert len(checks) == 1 and len(downloads) == 2
    row['audio_files'][0]['duration'] = 21.0
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five')
    assert len(checks) == 2


def test_positive_cache_never_authorizes_different_clip_bytes(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    pcm = [b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5)]
    checks = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: pcm[0])

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(1)
        return ('matching words', len(checks) == 1, 'ok' if len(checks) == 1 else 'text_mismatch')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'matching words') == pcm[0]
    pcm[0] = b'\x02\x00' * (service.CLIP_SAMPLE_RATE * 5)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'matching words') is None
    assert len(checks) == 2


def test_clip_verification_rejects_mismatch_and_caches_negative(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    checks = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: b'\x00\x00' * (service.CLIP_SAMPLE_RATE * 5))

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(1)
        return ('unrelated words', False, 'text_mismatch: containment=0.00')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert len(checks) == 1
    assert list(cache.values())[0]['valid'] is False


def test_negative_cache_rechecks_changed_pcm_under_same_manifest(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    cache = {}
    pcm = [b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5)]
    checks = []
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.__setitem__(key, value))
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: pcm[0])

    async def verify(audio, sample_rate, expected_text, language=None):
        checks.append(1)
        return (
            'one two three four five' if len(checks) == 2 else 'wrong speech elsewhere',
            len(checks) == 2,
            'ok' if len(checks) == 2 else 'text_mismatch',
        )

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    for _ in range(2):
        assert service.verified_clip_pcm('u', row, 1, 6, 'one two three four five') is None
    assert len(checks) == 1
    pcm[0] = b'\x02\x00' * (service.CLIP_SAMPLE_RATE * 5)
    assert service.verified_clip_pcm('u', row, 1, 6, 'one two three four five') == pcm[0]
    assert len(checks) == 2


def test_clip_match_rejects_short_subset_of_long_expected_text(monkeypatch):
    row = {'id': 'c1', 'audio_files': []}
    pcm = b'\x01\x00' * (service.CLIP_SAMPLE_RATE * 5)
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda *args, **kwargs: None)

    async def verify(audio, sample_rate, expected_text, language=None):
        return ('one two three four five', True, 'ok')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 0, 5, 'one two three four five', pcm) == pcm
    assert (
        service.verified_clip_pcm('u', row, 0, 5, 'one two three four five six seven eight nine ten eleven twelve', pcm)
        is None
    )
    assert service.verified_clip_pcm('u', row, 0, 5, 'completely different spoken words today', pcm) is None


def test_clip_expected_text_trims_long_segment_to_clip_window():
    row = {
        'transcript_segments': [
            {
                'speaker_id': 0,
                'start': 0,
                'end': 20,
                'text': 'one two three four five six seven eight nine ten eleven twelve',
            }
        ]
    }
    text = service.clip_expected_text(row, 0, 10)
    assert text.startswith('one two')
    assert 'twelve' not in text

    cjk = {
        'transcript_segments': [
            {'speaker_id': 0, 'start': 0, 'end': 20, 'text': '今天我们一起讨论如何安排下周的工作会议和项目计划'}
        ]
    }
    assert len(service.clip_expected_text(cjk, 0, 10)) < len(cjk['transcript_segments'][0]['text'])


def test_prompt_list_verification_budget_returns_without_empty_cooldown(monkeypatch):
    world = World(monkeypatch)
    started = NOW - timedelta(hours=1)
    row = {
        'id': 'slow',
        'started_at': started,
        'status': 'completed',
        'audio_files': [{'chunk_timestamps': [started.timestamp()], 'duration': 20.0}],
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 0, 'start': 0, 'end': 10, 'text': 'one two three four five six seven eight'}
        ],
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *args, **kwargs: [row])
    monkeypatch.setattr(service, 'LIST_VERIFY_BUDGET_SECONDS', 0.02)
    release = threading.Event()
    started_verify = threading.Event()

    def slow_verify(*args, **kwargs):
        started_verify.set()
        release.wait(timeout=1)
        return None

    monkeypatch.setattr(service, 'verified_clip_pcm', slow_verify)
    for shared in (executors.postprocess_executor, executors.sync_executor, executors.storage_executor):
        monkeypatch.setattr(
            shared, 'submit', lambda *args, **kwargs: pytest.fail('verification used a shared executor')
        )
    try:
        began = time.monotonic()
        response = service.get_prompts('u', NOW)
        assert time.monotonic() - began < 0.5
        assert started_verify.is_set()
        assert response.status == 'no_candidates'
        assert 'last_empty_check_at' not in world.state
    finally:
        release.set()


def test_list_verification_pool_is_bounded_and_dedupes_inflight(monkeypatch):
    pool = MonitoredThreadPoolExecutor(name='tag-test', max_workers=1, max_queue_size=1)
    monkeypatch.setattr(service, 'speaker_tag_verify_executor', pool)
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_verify(uid, row, start, end, text, *, verification_deadline):
        calls.append(row['id'])
        started.set()
        release.wait(timeout=2)
        return b'valid'

    monkeypatch.setattr(service, 'verified_clip_pcm', slow_verify)
    deadline = time.monotonic() + 1
    try:
        row = {'id': 'same', 'audio_files': [{'duration': 20}]}
        with ThreadPoolExecutor(max_workers=4) as callers:
            duplicates = list(
                callers.map(
                    lambda _: service._submit_list_verification('u', row, 0, 5, 'same words', deadline), range(4)
                )
            )
        assert started.wait(timeout=1)
        assert all(future is duplicates[0] for future in duplicates)
        assert calls == ['same']

        queued = service._submit_list_verification('u', {'id': 'queued'}, 0, 5, 'other words', deadline)
        assert pool.active_count == 1
        assert pool._work_queue.qsize() == 1
        with pytest.raises(ExecutorSaturatedError):
            service._submit_list_verification('u', {'id': 'rejected'}, 0, 5, 'third words', deadline)
        assert service._submit_list_verification('u', row, 0, 5, 'same words', deadline) is duplicates[0]
    finally:
        release.set()
        pool.shutdown(wait=True)
    assert queued.done()


def test_verification_stt_runs_inline_with_one_budgeted_provider_attempt(monkeypatch):
    def forbidden_shared_pool(*args, **kwargs):
        pytest.fail('verification submitted STT to a shared executor')

    monkeypatch.setattr(speaker_sample, 'run_blocking', forbidden_shared_pool)
    words = [{'text': word, 'speaker': 'SPEAKER_00'} for word in 'one two three four five'.split()]
    monkeypatch.setattr(speaker_sample, 'deepgram_prerecorded_from_bytes', lambda *args, **kwargs: words)
    result = speaker_sample.verify_and_transcribe_sample_in_worker(
        b'wave', 16000, 'one two three four five', None, time.monotonic() + 1
    )
    assert result == ('one two three four five', True, 'ok')

    attempts = []

    class SlowProvider:
        def __init__(self, timeout):
            attempts.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            raise TimeoutError('provider timed out')

    monkeypatch.setenv('MODULATE_API_KEY', 'test-only')
    monkeypatch.setattr(pre_recorded, 'require_provider_environment', lambda _: None)
    monkeypatch.setattr(pre_recorded.httpx, 'Client', SlowProvider)
    with pre_recorded.verification_stt_deadline(time.monotonic() + 0.5):
        with pytest.raises(RuntimeError, match='after 1 attempts'):
            pre_recorded.modulate_prerecorded_from_bytes(b'wave')
    assert len(attempts) == 1
    assert 0 < attempts[0].read <= 0.5

    attempts.clear()
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'https://invalid.example')
    with pre_recorded.verification_stt_deadline(time.monotonic() + 0.5):
        with pytest.raises(RuntimeError, match='after 1 attempts'):
            pre_recorded.parakeet_prerecorded_from_bytes(b'wave')
    assert len(attempts) == 1
    assert 0 < attempts[0].read <= 0.5


def test_truncated_clip_is_rejected_before_transcription(monkeypatch):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: b'\x00\x00' * service.CLIP_SAMPLE_RATE)
    called = []

    async def verify(*args, **kwargs):
        called.append(1)
        return ('one two three four five', True, 'ok')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert called == []


def test_clip_download_error_skips_prompt_without_leaking_content(monkeypatch, caplog):
    row = {'id': 'c1', 'audio_files': [{'chunk_timestamps': [10.0], 'duration': 20.0}]}
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)

    def fail(*args):
        raise RuntimeError('private sample data')

    monkeypatch.setattr(service, 'conversation_clip_pcm', fail)
    assert service.verified_clip_pcm('u', row, 1.0, 6.0, 'one two three four five') is None
    assert 'private sample data' not in caplog.text


def test_get_prompts_excludes_misaligned_merged_sync_audio(monkeypatch):
    World(monkeypatch)
    started = NOW - timedelta(hours=1)
    row = {
        'id': 'merged',
        'started_at': started,
        'status': 'completed',
        'sync_live_target': True,
        'sync_merged_from': ['donor'],
        'audio_files': [{'chunk_timestamps': [started.timestamp(), started.timestamp() + 88.2], 'duration': 92.3}],
        'conversation_audio': {'spans': [{'wall_offset': 0, 'len': 149.4}]},
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 0, 'start': 10.28, 'end': 20.28, 'text': 'Please confirm these spoken words'}
        ],
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversations', lambda *args, **kwargs: [row])
    monkeypatch.setattr(service.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(service.redis_db, 'set_generic_cache', lambda key, value, ttl: None)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *args: b'\x01\x00' * (10 * 16000))
    checked = []

    def verify(audio, sample_rate, expected_text, language, deadline):
        checked.append(expected_text)
        return ('Static and coughing', False, 'text_mismatch: containment=0.00')

    monkeypatch.setattr(service, 'verify_and_transcribe_sample_in_worker', verify)
    response = service.get_prompts('u', NOW)
    assert response.status == 'no_candidates'
    assert checked == ['Please confirm these spoken words']


def test_owner_clip_window_requires_clean_owner_stretch():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 4, 'is_user': True, 'text': 'one two'},
            {'id': 'b', 'start': 4, 'end': 8, 'is_user': True, 'text': 'three four'},
            {'id': 'c', 'start': 8, 'end': 9, 'is_user': False, 'text': 'x'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b']) == (0.0, 8.0, 'one two three four')
    assert service.owner_clip_window(conversation, ['a']) is None  # too short
    assert service.owner_clip_window(conversation, ['a', 'c']) is None  # not all the owner


def test_owner_clip_window_rejects_a_second_diarized_voice_even_labeled_user():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'speaker_id': 0, 'text': 'mine'},
            {'id': 'b', 'start': 3, 'end': 4, 'is_user': True, 'speaker_id': 1, 'text': 'theirs'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a']) is None


def test_owner_clip_window_uses_only_text_inside_the_clip():
    conversation = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 3, 'is_user': True, 'speaker_id': 0, 'text': 'outside before'},
            {'id': 'b', 'start': 5, 'end': 15, 'is_user': True, 'speaker_id': 0, 'text': 'inside clip'},
            {'id': 'c', 'start': 17, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': 'outside after'},
        ]
    }
    assert service.owner_clip_window(conversation, ['a', 'b', 'c']) == (5.0, 15.0, 'inside clip')
    no_inside_text = {
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'speaker_id': 0, 'text': ''},
            {'id': 'b', 'start': 8, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': ''},
        ]
    }
    assert service.owner_clip_window(no_inside_text, ['a', 'b']) is None


def test_owner_sample_verifies_only_text_inside_the_clip(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [
            {'id': 'a', 'start': 0, 'end': 3, 'is_user': True, 'speaker_id': 0, 'text': 'outside before'},
            {'id': 'b', 'start': 5, 'end': 15, 'is_user': True, 'speaker_id': 0, 'text': 'inside clip'},
            {'id': 'c', 'start': 17, 'end': 20, 'is_user': True, 'speaker_id': 0, 'text': 'outside after'},
        ],
    }
    clipped = []
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(
        service,
        'conversation_clip_pcm',
        lambda uid, conv, start, end: clipped.append((start, end)) or b'\x01\x00' * 16000,
    )

    async def verify(wav, rate, text, language=None):
        assert text == 'inside clip'
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[1.0, 0.0]], dtype=np.float32))
    monkeypatch.setattr(
        service.voice_profiles_db, 'add_owner_voice_confirmation', lambda uid, embedding, pool, conversation_id: 1
    )
    assert asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a', 'b', 'c'])) == 'stored'
    assert clipped == [(5.0, 15.0)]


def test_owner_sample_gets_only_prompt_segments_still_assigned(monkeypatch):
    world = World(monkeypatch, paid=False)

    def assign(uid, conversation_id, **kwargs):
        return {'transcript_segments': [{'id': 's1', 'start': 0, 'end': 9}]}, ['s1', 's9'], [], []

    monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)
    response = service.apply_answer(
        'u', _request(K.owner_check, O.unnamed, A.me, segment_ids=['s1', 'stale']), world.schedule, NOW
    )
    fn, kwargs = world.scheduled[0]
    assert fn is service.store_owner_voice_sample and kwargs['segment_ids'] == ['s1']
    assert response.voice_sample_queued


def test_owner_sample_not_queued_when_prompt_segments_are_gone(monkeypatch):
    world = World(monkeypatch, paid=False)

    def assign(uid, conversation_id, **kwargs):
        return {'transcript_segments': [{'id': 's9', 'start': 0, 'end': 9}]}, ['s9'], [], []

    monkeypatch.setattr(service.conversations_db, 'assign_conversation_speaker', assign)
    response = service.apply_answer(
        'u', _request(K.owner_check, O.unnamed, A.me, segment_ids=['s1']), world.schedule, NOW
    )
    assert world.scheduled == [] and not response.voice_sample_queued


def test_owner_sample_is_verified_then_pooled(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [{'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'text': 'hello there friend'}],
    }
    pooled = []
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *a: b'\x01\x00' * 16000)

    async def verify(wav, rate, text, language=None):
        assert text == 'hello there friend' and language == 'en'
        return text, True, 'ok'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(service, 'extract_embedding_from_bytes', lambda *a: np.array([[3.0, 4.0]], dtype=np.float32))
    monkeypatch.setattr(
        service.voice_profiles_db,
        'add_owner_voice_confirmation',
        lambda uid, embedding, pool, conversation_id: pooled.append((embedding, pool([embedding]))) or 1,
    )
    outcome = asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a']))
    assert outcome == 'stored'
    assert pooled[0][0] == [3.0, 4.0]
    assert pooled[0][1] == pytest.approx([0.6, 0.8])


def test_owner_sample_rejected_by_quality_gate_is_not_pooled(monkeypatch):
    conversation = {
        'id': 'c1',
        'language': 'en',
        'transcript_segments': [{'id': 'a', 'start': 0, 'end': 8, 'is_user': True, 'text': 'hi'}],
    }
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid: conversation)
    monkeypatch.setattr(service, 'conversation_clip_pcm', lambda *a: b'\x01\x00' * 16000)

    async def verify(wav, rate, text, language=None):
        return None, False, 'multi_speaker: ratio=0.40'

    monkeypatch.setattr(service, 'verify_and_transcribe_sample', verify)
    monkeypatch.setattr(
        service.voice_profiles_db, 'add_owner_voice_confirmation', lambda *a, **k: pytest.fail('must not pool')
    )
    assert asyncio.run(service.store_owner_voice_sample('u', 'c1', ['a'])) == 'rejected_quality'

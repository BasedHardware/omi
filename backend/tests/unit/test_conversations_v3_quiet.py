"""Quiet edges, exact input identity and bounded summary-only orchestration."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from database import conversations_v3_quiet as attempts
from models.conversation import Conversation
from models.conversation_photo import ConversationPhoto
from utils.conversations.v3 import quiet, summary_input, summary, triggers, service, renewal
from utils.conversations import process_conversation as process
from utils.conversations import transcript_for_llm as transcript
from tests.unit.test_conversations_v3_stream import real_notes_seam

AT = datetime.now(timezone.utc) - timedelta(minutes=1)


def row(**extra):
    return {
        'id': 'c',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT + timedelta(seconds=10),
        'status': 'in_progress',
        'tile_state': 'live',
        'v3_derived': True,
        'kind': 'conversation',
        'transcript_segments': [{'text': 'planning with Alice ' * 110, 'start': 0, 'end': 10, 'is_user': True}],
        'structured': {},
        **extra,
    }


def test_identity_survives_model_round_trip_and_transport_seal():
    original = row()
    model = Conversation(**original)
    assert summary_input.fingerprint(original) == summary_input.fingerprint(model)
    assert summary_input.fingerprint(original) == summary_input.fingerprint(
        {**original, 'status': 'completed', 'audio_files': [{'id': 'seal'}]}
    )


def test_photo_identity_normalizes_stored_optional_none_and_model_defaults():
    photo = ConversationPhoto(id='frame', base64='', description='Planning whiteboard.', created_at=AT)
    original = row(photos=[photo.model_dump()])
    assert summary_input.fingerprint(original) == summary_input.fingerprint(Conversation(**original))


def test_undated_stored_photo_cannot_mint_a_time_dependent_identity():
    with pytest.raises(ValueError, match='photo_capture_time_unavailable'):
        summary_input.fingerprint(row(photos=[{'id': 'frame', 'base64': '', 'description': 'Planning.'}]))


@pytest.mark.parametrize('authority', ['manual', 'auto'])
def test_owner_authority_changes_actual_notes_and_freshness(monkeypatch, authority):
    monkeypatch.setattr(transcript, 'get_user_name', lambda *a, **kw: 'Nik')
    monkeypatch.setattr(transcript, 'serving_for', lambda *a: False)
    original = row()
    segment = original['transcript_segments'][0]
    segment.update(
        speaker_id=0,
        speaker_id_scope='capture:one',
        speaker_label_source='carried' if authority == 'manual' else None,
        speaker_identity_status='user' if authority == 'manual' else 'unknown',
        speaker_match_source=None,
    )
    original.update(
        summary_covers_through=original['finished_at'], summary_input_hash=summary_input.fingerprint(original)
    )
    before, voices = transcript.conversation_transcript_and_speaker_map('u', Conversation(**original))
    assert 'Nik' not in voices.values() and summary.fresh(original)
    segment.update(
        speaker_label_source=authority,
        speaker_identity_status='user',
        speaker_match_source=None if authority == 'manual' else 'conversation_voice',
    )
    after, voices = transcript.conversation_transcript_and_speaker_map('u', Conversation(**original))
    assert 'Nik' in voices.values()
    assert not summary.fresh(original)
    assert summary_input.fingerprint(original) == summary_input.fingerprint(Conversation(**original))


@pytest.mark.parametrize(
    'voice', [{}, {'speaker': 'SPEAKER_378'}, {'speaker_id': 4}, {'speaker_id': 0, 'speaker_id_scope': 'capture:one'}]
)
def test_effective_voice_identity_keeps_legacy_dict_and_model_defaults(voice):
    original = row()
    original['transcript_segments'][0].update(voice)
    assert summary_input.fingerprint(original) == summary_input.fingerprint(Conversation(**original))


@pytest.mark.parametrize('regroup', ['speaker_id_scope', 'speaker_id'])
def test_voice_regrouping_changes_real_notes_transcript_and_freshness(monkeypatch, regroup):
    monkeypatch.setattr(transcript, 'get_user_name', lambda *a, **kw: None)
    monkeypatch.setattr(transcript, 'serving_for', lambda *a: False)
    original = row(
        transcript_segments=[
            {
                'id': 'one',
                'text': 'Friday planning ' * 150,
                'start': 0,
                'end': 10,
                'is_user': False,
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'speaker_id_scope': 'capture:one',
            },
            {
                'id': 'two',
                'text': 'Monday delivery ' * 150,
                'start': 10,
                'end': 20,
                'is_user': False,
                'speaker': 'SPEAKER_00',
                'speaker_id': 0 if regroup == 'speaker_id_scope' else 1,
                'speaker_id_scope': 'capture:two' if regroup == 'speaker_id_scope' else 'capture:one',
            },
        ]
    )
    original.update(
        summary_covers_through=original['finished_at'], summary_input_hash=summary_input.fingerprint(original)
    )
    before, voices = transcript.conversation_transcript_and_speaker_map('u', Conversation(**original))
    assert len(voices) == 2 and summary.fresh(original)
    original['transcript_segments'][1][regroup] = original['transcript_segments'][0][regroup]
    after, voices = transcript.conversation_transcript_and_speaker_map('u', Conversation(**original))
    assert len(voices) == 1 and before != after
    assert not summary.fresh(original)


@pytest.mark.parametrize(
    'change',
    [
        {'finished_at': AT + timedelta(seconds=11)},
        {'started_at': AT - timedelta(seconds=1)},
        {'manual_end': True},
        {'kind': 'media'},
        {'language': 'fr'},
        {'transcript_segments': [{'text': 'same time corrected words', 'start': 0, 'end': 10, 'is_user': True}]},
        {
            'transcript_segments': [
                {'text': 'planning with Alice ' * 110, 'start': 0, 'end': 10, 'person_id': 'alice', 'is_user': False}
            ]
        },
    ],
)
def test_exact_coverage_rejects_changed_window_and_same_time_corrections(change):
    original = row()
    original.update(
        summary_covers_through=original['finished_at'], summary_input_hash=summary_input.fingerprint(original)
    )
    assert summary.fresh(original)
    assert not summary.fresh({**original, **change})
    assert not summary.fresh({**original, 'summary_covers_through': original['finished_at'] + timedelta(seconds=1)})


def test_old_timestamp_only_coverage_does_not_authorize_v3_reuse():
    original = row()
    assert not summary.fresh({**original, 'summary_covers_through': original['finished_at']})
    assert not summary.fresh({'finished_at': AT, 'summary_covers_through': AT + timedelta(seconds=1)})


def test_source_obligation_arms_once_per_content_and_not_per_transport_seal(monkeypatch):
    original = row(recording=True, v3_derived=False)
    snap = SimpleNamespace(to_dict=lambda: original)
    monkeypatch.setattr(attempts.store, 'decode_row', lambda *a, **kw: original)
    patch = attempts.source_patch('u', snap, now=AT)
    assert patch['v3_quiet_due'] == original['finished_at'] + timedelta(seconds=30)
    original.update(patch, status='completed', audio_files=[{'id': 'transport-seal'}])
    assert attempts.source_patch('u', snap, now=AT + timedelta(seconds=20)) == {}
    original['transcript_segments'][0]['text'] += ' corrected'
    assert attempts.source_patch('u', snap, now=AT + timedelta(seconds=20))['v3_quiet_pending']


def test_quiet_names_are_separate_from_manual_end_and_distinct_within_a_minute(monkeypatch):
    sent = []
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://test.invalid')
    monkeypatch.setattr(triggers, 'enqueue_named_task', lambda *a, **kw: sent.append((a, kw)))
    triggers.enqueue('u', at=AT)
    triggers.enqueue('u', at=AT, manual_end_id='r')
    triggers.enqueue('u', at=AT, quiet_recording_id='r', quiet_generation='a' * 64)
    triggers.enqueue('u', at=AT + timedelta(seconds=1), quiet_recording_id='r', quiet_generation='b' * 64)
    triggers.enqueue('u', at=AT, quiet_recording_id='r', quiet_generation='a' * 64)
    assert len({call[0][2] for call in sent}) == 4
    assert sent[2] == sent[4]
    assert sent[2][0][3] == {'uid': 'u', 'quiet_recording_id': 'r', 'quiet_generation': 'a' * 64}
    assert sent[2][1]['schedule_at'] >= AT.timestamp()
    assert sent[2][1]['schedule_at'] < AT.timestamp() + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('exhausted', [False, True])
async def test_quiet_reuses_custom_stt_allowance_before_lease_permit_or_paid_work(monkeypatch, exhausted):
    original = row(uses_custom_stt=True, source='omi', _v3_revision=1)
    calls = []

    async def blocking(pool, fn, *a, **kw):
        if fn is summary.paid_notes_refused:
            assert pool is quiet.db_executor
        return fn(*a, **kw)

    def allowance(uid, **kw):
        assert uid == 'u' and kw == {'uses_custom_stt': True, 'source': 'omi'}
        calls.append('allowance')
        return exhausted

    monkeypatch.setattr(quiet, 'run_blocking', blocking)
    monkeypatch.setattr(renewal, 'run_blocking', blocking)
    monkeypatch.setattr(summary, 'should_skip_omi_paid_postprocessing', allowance)
    monkeypatch.setattr(quiet.leases, 'acquire', lambda *a: calls.append('lease') or 'token')
    monkeypatch.setattr(quiet.leases, 'release', lambda *a: calls.append('release'))
    monkeypatch.setattr(quiet, 'require_generated_compute', lambda *a, **kw: calls.append('admission'))
    monkeypatch.setattr(
        attempts,
        'reserve',
        lambda *a, **kw: calls.append('permit')
        or {
            'row': original,
            'revision': 1,
            'sources': {},
            'input_hash': 'h',
        },
    )
    monkeypatch.setattr(summary, 'write', lambda *a: calls.append('writer') or {'sections': []})
    monkeypatch.setattr(summary.writers, 'store_summary', lambda *a, **kw: calls.append('store'))
    assert await quiet.snapshot('u', original) == ('skipped' if exhausted else 'stored')
    assert calls == (
        ['allowance'] if exhausted else ['allowance', 'lease', 'admission', 'permit', 'writer', 'store', 'release']
    )


@pytest.mark.asyncio
async def test_old_quiet_delivery_does_no_reconcile_or_paid_work(monkeypatch):
    monkeypatch.setattr(attempts, 'obligation', lambda *a: None)
    monkeypatch.setattr(attempts, 'settle', lambda *a: None)
    monkeypatch.setattr(service, 'reconcile', AsyncMock(side_effect=AssertionError('stale wake reconciled')))
    assert await quiet.run('u', 'r', 'old') == 'superseded'


def test_provisional_notes_recompute_at_real_close(real_notes_seam, monkeypatch):
    monkeypatch.setattr(process, 'content_minimum', lambda *a, **kw: None)
    monkeypatch.setattr(process, 'quiet_minimum', lambda *a, **kw: None)
    original = row()
    original.update(
        summary_covers_through=original['finished_at'],
        summary_input_hash=summary_input.fingerprint(original),
        summary_is_snapshot=True,
    )
    model = Conversation(**original)
    with summary.models.notes_mode('u'):
        structured, discarded = process._get_structured('u', 'en', model)
    assert len(real_notes_seam) == 1 and not discarded
    assert structured.sections[0].body_markdown


@pytest.mark.asyncio
async def test_cancelled_quiet_worker_keeps_lease_until_blocking_call_exits(monkeypatch):
    import threading

    entered, resume = threading.Event(), threading.Event()
    held, writes = [], []
    original = row(_v3_revision=1)

    async def blocking(pool, fn, *a, **kw):
        if fn is summary.write:
            return await asyncio.to_thread(fn, *a, **kw)
        return fn(*a, **kw)

    def write(*a):
        entered.set()
        assert resume.wait(3)
        return {'title': 'Snapshot'}

    monkeypatch.setattr(quiet, 'run_blocking', blocking)
    monkeypatch.setattr(renewal, 'run_blocking', blocking)
    monkeypatch.setattr(quiet.leases, 'acquire', lambda *a: held.append('token') or 'token')
    monkeypatch.setattr(quiet.leases, 'release', lambda *a: held.clear())
    monkeypatch.setattr(quiet, 'require_generated_compute', lambda *a, **kw: None)
    monkeypatch.setattr(
        attempts, 'reserve', lambda *a, **kw: {'row': original, 'revision': 1, 'sources': {}, 'input_hash': 'h'}
    )
    monkeypatch.setattr(summary, 'write', write)
    monkeypatch.setattr(summary.writers, 'store_summary', lambda *a, **kw: writes.append(a))
    task = asyncio.create_task(quiet.snapshot('u', original))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.001)
        assert entered.is_set()
        task.cancel()
        await asyncio.sleep(0)
        assert held == ['token'] and not task.done()
    finally:
        resume.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not held and not writes

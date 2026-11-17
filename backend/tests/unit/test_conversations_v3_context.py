"""Synthetic grounding, effective cache identity and account-bound participants."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
import tiktoken
from models.conversation import Conversation
from models.structured import Structured
from utils.conversations.v3 import context, outline, planner, service
from utils.conversations import process_conversation as process, llm_input_dedupe
from database import conversations_v3_context as sources, conversations_v3 as store
from tests.unit.test_conversations_v3_review import builder, source, AT
from tests.unit.test_conversations_v3_stream import real_notes_seam


@pytest.fixture
def context_notes_seam(real_notes_seam, monkeypatch):
    monkeypatch.setattr(process, 'content_minimum', lambda *a, **k: None)
    monkeypatch.setattr(process, 'quiet_minimum', lambda *a, **k: None)
    return real_notes_seam


def token_count(text):
    if hasattr(tiktoken, 'get_encoding'):
        return len(tiktoken.get_encoding('o200k_base').encode(text))
    return len(text.encode('utf-8'))


def conversation(**extra):
    return Conversation(
        id='c',
        created_at=AT,
        started_at=AT,
        finished_at=AT + timedelta(seconds=40),
        transcript_segments=[
            {'text': 'planning with Alice ' * 110, 'start': 0, 'end': 40, 'person_id': 'alice', 'is_user': False}
        ],
        v3_derived=True,
        kind='conversation',
        structured={},
        **extra,
    )


@pytest.mark.parametrize('foreground', [False, True])
def test_every_v3_summary_gets_background_without_agent_loop(context_notes_seam, monkeypatch, foreground):
    seen = []
    monkeypatch.setattr(context, 'summary', lambda *a: 'BACKGROUND CONTEXT profile goals Alice memories')
    monkeypatch.setattr(llm_input_dedupe, 'notes', lambda *a, **kw: (seen.append(kw) or Structured(title='Plan')))
    with service.models.notes_mode('u', foreground=foreground):
        process._get_structured('u', 'en', conversation())
    assert seen[0]['meeting_context'] == 'BACKGROUND CONTEXT profile goals Alice memories'
    assert seen[0]['rich_context_enabled'] is False  # not meeting-like, still grounded


def test_summary_reuses_composer_gather_and_bounds_rendered_tokens(monkeypatch):
    gather = Mock(
        return_value=(
            'profile goals Alice ' * 600,
            'optional background ' * 1000 + '\n\n- [category=fact] ranked account memories ' * 3000,
        )
    )
    monkeypatch.setattr(context.composer_context, 'gather', gather)
    text = context.summary('u', conversation(), 'en', 'UTC')
    args, kwargs = gather.call_args
    assert args[0] == 'u' and args[1][0]['transcript_segments'][0]['person_id'] == 'alice'
    assert kwargs == {'owner': '', 'language': 'en', 'timezone': 'UTC'}
    assert text.startswith('BACKGROUND CONTEXT') and 'profile goals Alice' in text and 'ranked account memories' in text
    assert token_count(text) <= context.SUMMARY_TOKENS


def test_short_and_covered_rows_do_not_retrieve_context(context_notes_seam, monkeypatch):
    monkeypatch.setattr(context, 'summary', lambda *a: pytest.fail('no summary, no context'))
    monkeypatch.setattr(service.models, 'short_tasks', lambda *a: Structured())
    short = conversation().model_copy(update={'transcript_segments': conversation().transcript_segments[:1]})
    short.transcript_segments[0].text = 'useful speech ' * 40
    process._get_structured('u', 'en', short)
    covered = conversation(summary_covers_through=AT + timedelta(seconds=40))
    process._get_structured('u', 'en', covered)


def test_outline_context_is_stretch_bound_today_earlier_and_small():
    group = outline.stretches(
        [source(transcript_segments=[{'text': 'talk', 'start': 0, 'end': 10, 'person_id': 'alice'}])],
        AT + timedelta(hours=1),
    )[0]
    data = (
        {'profile_text': 'personal profile ' * 1000, '_timezone': 'America/Los_Angeles'},
        [{'id': 'alice', 'name': 'Alice'}, {'id': 'bob', 'name': 'Bob'}],
        [
            {'started_at': AT - timedelta(minutes=2), 'title': 'Earlier plan'},
            {'started_at': AT + timedelta(minutes=1), 'title': 'Future plan'},
        ],
    )
    text = context.outline_block(group, data)
    assert 'Alice' in text and 'Bob' not in text and 'Earlier plan' in text and 'Future plan' not in text
    assert token_count(text) <= context.OUTLINE_TOKENS


@pytest.mark.asyncio
async def test_effective_outline_cache_invalidates_prompt_and_context(builder, monkeypatch):
    committed, calls = builder
    cache = []
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': source()}, {}, cache))
    await service.reconcile('u')
    cache[:] = committed[-1][5]
    await service.reconcile('u')
    assert len(calls) == 1
    monkeypatch.setattr(service.outline, 'SYSTEM_PROMPT', service.outline.SYSTEM_PROMPT + '\nNew cut rule')
    await service.reconcile('u')
    assert len(calls) == 2
    cache[:] = committed[-1][5]
    monkeypatch.setattr(context, 'outline_sources', lambda *a: ({'profile_text': 'Changed context'}, [], []))
    await service.reconcile('u')
    assert len(calls) == 3
    cache[:] = committed[-1][5]
    monkeypatch.setattr(context, 'CONTEXT_VERSION', 'next-context-version')
    await service.reconcile('u')
    assert len(calls) == 4


def test_outline_kill_switch_and_fail_empty(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_OUTLINE_CONTEXT', 'off')
    monkeypatch.setattr(context, 'submit_with_context', lambda *a: pytest.fail('kill switch read context'))
    assert context.outline_sources('u', [{}]) == ({}, [], [])
    monkeypatch.delenv('CONVERSATIONS_V3_OUTLINE_CONTEXT')
    monkeypatch.setattr(context, 'submit_with_context', lambda pool, fn: fn())
    monkeypatch.setattr(sources, 'profile', lambda *a: (_ for _ in ()).throw(ValueError('synthetic')))
    assert context.outline_sources('u', [{}]) == ({}, [], [])


def test_earlier_titles_are_same_local_day():
    group = {'lines': [{'start': AT, 'segment': {}}]}
    data = (
        {'_timezone': 'America/Los_Angeles'},
        [],
        [
            {'started_at': AT - timedelta(hours=2), 'title': 'Same local day'},
            {'started_at': AT - timedelta(hours=20), 'title': 'Previous local day'},
        ],
    )
    text = context.outline_block(group, data)
    assert 'Same local day' in text and 'Previous local day' not in text


def test_non_v3_notes_do_not_gather_v3_context(context_notes_seam, monkeypatch):
    monkeypatch.setattr(context, 'summary', lambda *a: pytest.fail('legacy context changed'))
    process._get_structured('u', 'en', conversation().model_copy(update={'v3_derived': False}))


def test_explicit_background_override_keeps_owner_corrections(context_notes_seam, monkeypatch):
    monkeypatch.setattr(context, 'summary', lambda *a: pytest.fail('override retrieved twice'))
    monkeypatch.setattr(process, 'rich_notes_inputs', lambda *a, **k: (None, '\nConfirmed correction', False, (), 0))
    seen = []
    monkeypatch.setattr(llm_input_dedupe, 'notes', lambda *a, **kw: (seen.append(kw) or Structured(title='Plan')))
    process._get_structured('u', 'en', conversation(), meeting_context_override='BACKGROUND CONTEXT explicit')
    assert seen[0]['meeting_context'] == 'BACKGROUND CONTEXT explicit\nConfirmed correction'


def test_outline_title_read_is_owner_scoped_bounded_and_hides_capture_rows(monkeypatch):
    from tests.support.firestore_shape_recorder import RecordingFirestore
    from utils.other.list_budget import ListReadBudget

    db = RecordingFirestore()
    docs = []
    for name, extra in [
        ('keep', {}),
        ('capture', {'recording': True}),
        ('hidden', {'home_hidden': True}),
        ('deleted', {'deleted': True}),
        ('locked', {'is_locked': True}),
        ('private', {'data_protection_level': 'private'}),
        ('absorbed', {'sync_merged_into': 'other'}),
    ]:
        docs.append(
            db.snapshot(f'users/u/conversations/{name}', {'started_at': AT, 'structured': {'title': name}, **extra})
        )
    db.queue_results(docs)
    monkeypatch.setattr(sources.conversations, 'prepare_conversation_for_read', lambda row, *a, **k: row)
    rows = sources.earlier_titles(
        'u',
        AT - timedelta(hours=1),
        AT + timedelta(hours=1),
        ListReadBudget(deadline_monotonic=10**30, max_documents=53),
        firestore_client=db,
    )
    assert rows == [{'started_at': AT, 'title': 'keep'}]
    shape = db.shapes[-1]
    assert shape.collection_path == 'users/u/conversations'


@pytest.mark.asyncio
async def test_context_change_alone_never_schedules_summary_rewrite(builder, monkeypatch):
    committed, calls = builder
    existing, cache = {}, []
    recording = source(transcript_segments=[{'text': 'greenhouse plan ' * 160, 'start': 0, 'end': 10}])
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': recording}, existing, cache))
    await service.reconcile('u')
    row = committed[-1][4][0]
    row.update(
        status='completed', tile_state='done', v3_process_pending=False, summary_covers_through=row['finished_at']
    )
    existing[row['id']] = row
    cache[:] = committed[-1][5]
    monkeypatch.setattr(context, 'outline_sources', lambda *a: ({'profile_text': 'Updated life context'}, [], []))
    await service.reconcile('u')
    assert len(calls) == 2  # a changed outline context is evaluated
    rebuilt = committed[-1][4][0]
    assert rebuilt['v3_process_pending'] is False and rebuilt['tile_state'] == 'done'
    assert rebuilt.get('v3_rewrites', 0) == 0


@pytest.mark.asyncio
async def test_late_speech_rewrite_drops_old_summary_coverage(builder, monkeypatch):
    from datetime import datetime

    committed, _calls = builder

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AT + timedelta(minutes=10)

    monkeypatch.setattr(service, 'datetime', Clock)
    existing, cache = {}, []
    recording = source(transcript_segments=[{'text': 'greenhouse plan ' * 160, 'start': 0, 'end': 10}])
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': recording}, existing, cache))
    await service.reconcile('u')
    row = committed[-1][4][0]
    row.update(
        status='completed', tile_state='done', v3_process_pending=False, summary_covers_through=row['finished_at']
    )
    existing[row['id']] = row
    cache[:] = committed[-1][5]
    # Late transcription adds well over 10% more words inside the summarized window.
    recording['transcript_segments'].append({'text': 'late detail ' * 80, 'start': 4, 'end': 8})
    await service.reconcile('u')
    rebuilt = committed[-1][4][0]
    assert rebuilt['v3_rewrites'] == 1 and rebuilt['v3_process_pending'] is True
    assert rebuilt['summary_covers_through'] is None


@pytest.mark.asyncio
async def test_late_audio_metadata_gives_a_finished_conversation_its_pieces(builder, monkeypatch):
    from datetime import datetime

    committed, _calls = builder

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AT + timedelta(minutes=10)

    monkeypatch.setattr(service, 'datetime', Clock)
    existing, cache = {}, []
    recording = source(transcript_segments=[{'text': 'greenhouse plan ' * 160, 'start': 0, 'end': 10}])
    monkeypatch.setattr(store, 'load', lambda *a, **kw: ({'r': recording}, existing, cache))
    await service.reconcile('u')
    row = committed[-1][4][0]
    assert row['recording_pieces'] == []
    row.update(status='completed', tile_state='done', v3_process_pending=False)
    existing[row['id']] = row
    cache[:] = committed[-1][5]
    # The sync pipeline writes audio metadata after the window was already reconciled.
    recording['audio_files'] = [{'id': 'f', 'duration': 10, 'chunk_timestamps': [AT.timestamp()]}]
    await service.reconcile('u')
    rebuilt = committed[-1][4][0]
    assert rebuilt['id'] == row['id']
    assert rebuilt['recording_pieces'] == [{'recording_id': 'r', 'audio_file_id': 'f', 'start': 0.0, 'end': 10.0}]

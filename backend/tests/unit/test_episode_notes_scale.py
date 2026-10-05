"""Synthetic scale receipts: no production documents or external providers."""

import json
from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from config.episode_notes import episode_notes_cohort
from models.episode_extraction import EpisodeStructuredExtraction
from utils.conversations.episode_compaction import compact_episode_items
from utils.conversations.episode_evidence import EvidenceItem, render_episode_evidence
from utils.llm.notes_observability import NotesRun


@pytest.mark.parametrize('value', ['', 'bad', 'nan', 'inf', '-1', '101', '0'])
def test_ramp_fails_closed(monkeypatch, value):
    monkeypatch.setenv('MEETING_NOTES_EPISODE_EVIDENCE_PERCENT', value)
    assert not episode_notes_cohort('invented-owner')
    assert not episode_notes_cohort(None)


def test_sticky_nested_uid_cohorts(monkeypatch):
    groups = []
    for share in (1, 10, 50, 100):
        monkeypatch.setenv('MEETING_NOTES_EPISODE_EVIDENCE_PERCENT', str(share))
        group = {str(uid) for uid in range(1000) if episode_notes_cohort(str(uid))}
        assert group == {str(uid) for uid in range(1000) if episode_notes_cohort(str(uid))}
        groups.append(group)
    assert all(left <= right for left, right in zip(groups, groups[1:]))
    assert len(groups[-1]) == 1000


def test_compaction_keeps_speech_changes_id_and_time_and_bounds_incidental_screens():
    speech = EvidenceItem(id='speech:1', source_kind='speech', actor='Ari', content='Discuss the pricing proposal.')
    screens = [
        EvidenceItem(id=f'screen:{i}', source_kind='screen_ocr', time=str(i), content=content)
        for i, content in enumerate(
            [
                'Window chrome\nAri joined\nPricing proposal',
                '  Window   chrome\nAri joined\nPricing proposal\nAri left the call',
                'Window chrome\nAri joined\nPricing proposal\nAri left the call',
                *['Unrelated invented document ' + str(i) + ' z' * 3000 for i in range(20)],
            ]
        )
    ]
    items = compact_episode_items([speech, *screens])
    assert items[0] is speech
    assert next(item for item in items if item.id == 'screen:1').content == 'Ari left the call'
    assert next(item for item in items if item.id == 'screen:1').time == '1'
    assert all(item.id != 'screen:2' for item in items)
    assert sum(len(item.content) for item in items[1:]) < 14000
    assert len(render_episode_evidence(items)) < len(render_episode_evidence([speech, *screens])) / 10


def test_compaction_retains_changed_participants_even_with_same_summary():
    items = [
        EvidenceItem(
            id=f'screen:{i}',
            source_kind='screen_frame',
            content=json.dumps(
                {
                    'summary': 'Active call',
                    'visible_names': names,
                    'role': 'meeting',
                }
            ),
        )
        for i, names in enumerate([['Ari'], ['Ari', 'Bo']])
    ]
    assert len(compact_episode_items(items)) == 2


def test_short_generation_keys_expand_into_existing_claim_shape():
    result = EpisodeStructuredExtraction.model_validate(
        {
            'title': 'Approval',
            'note_claims': [
                {'t': 'Approval', 'p': '/title', 'e': ['evidence:0'], 'v': 'inferred'},
            ],
        }
    ).to_structured()
    claim = result.note_claims[0].model_dump()
    assert claim['text'] == 'Approval' and claim['target'] == '/title'
    assert claim['evidence_ids'] == ['evidence:0'] and claim['provenance'] == 'inferred'
    assert 't' not in claim and 'private' not in claim


def test_receipt_is_content_free_and_counts_cache_and_retries(caplog):
    run = NotesRun('episode')
    model = SimpleNamespace(
        invoke=lambda messages: SimpleNamespace(
            content='DO NOT LOG',
            usage_metadata={
                'input_tokens': 100,
                'output_tokens': 30,
                'input_token_details': {'cache_read': 80},
            },
        )
    )
    run.invoke(model, ['DO NOT LOG'])
    run.invoke(model, ['DO NOT LOG'])
    run.violations.add('missing_claims')
    with caplog.at_level('INFO'):
        run.emit()
    assert 'input_tokens=200' in caplog.text and 'cached_tokens=160' in caplog.text
    assert 'retry_count=1' in caplog.text and 'missing_claims' in caplog.text
    assert 'DO NOT LOG' not in caplog.text


@pytest.fixture(scope='module')
def runtime():
    from testing.import_isolation import stub_modules

    with stub_modules({}):
        from utils.llm import conversation_processing
        from utils.conversations import meeting_notes_wiring, meeting_context_pack, render

        yield conversation_processing, meeting_notes_wiring, meeting_context_pack, render


def test_list_and_search_omit_claims_detail_keeps_them(runtime):
    _, _, _, render = runtime
    from models.conversation import Conversation

    note = EpisodeStructuredExtraction.model_validate(
        {
            'title': 'Approval',
            'note_claims': [
                {'t': 'Approval', 'p': '/title', 'e': ['speech:1'], 'v': 'said'},
            ],
        }
    ).to_structured()
    raw = {'id': 'invented', 'structured': note.model_dump(mode='json')}
    before = len(json.dumps(raw, separators=(',', ':')).encode())
    projected = render.redact_conversation_for_list(raw)
    assert 'note_claims' not in projected['structured']
    assert before > len(json.dumps(projected, separators=(',', ':')).encode())
    detail = Conversation(
        id='invented', created_at=datetime.now(timezone.utc), started_at=None, finished_at=None, structured=note
    ).model_dump(mode='json')
    assert detail['structured']['note_claims'][0]['text'] == 'Approval'


def test_production_rich_reads_identical_with_episode_no_n_plus_one(runtime, monkeypatch):
    _, wiring, pack, _ = runtime
    from models.calendar_context import CalendarMeetingContext, MeetingParticipant
    from utils.conversations.meeting_context_render import PriorMeetingNote

    reads = Counter()
    documents = Counter()

    def source(name, count, result):
        def read(*args, **kwargs):
            reads[name] += 1
            documents[name] += count
            return result

        return read

    monkeypatch.setattr(pack, 'load_people_documents', source('people', 2, []))
    monkeypatch.setattr(pack, 'resolve_owner_identity', source('profile', 1, ('Owner', [])))
    monkeypatch.setattr(
        pack,
        '_gather_prior_meetings',
        source('prior', 3, (PriorMeetingNote(title='Prior', date_label='Earlier', gist='Discuss pricing'),)),
    )
    monkeypatch.setattr(pack, '_gather_goals', source('goals', 1, ('Plan pricing',)))
    monkeypatch.setattr(pack, '_gather_memories', source('memories', 4, ('Ari discusses pricing',)))
    monkeypatch.setattr(
        pack,
        '_gather_screen_rows',
        source('screen', 80, tuple({'ocrText': 'Ari joined', 'timestamp': str(i)} for i in range(80))),
    )
    monkeypatch.setattr(wiring, '_screen_frame_evidence', source('frames', 0, ()))
    calendar = CalendarMeetingContext(
        calendar_event_id='fake',
        title='Pricing',
        start_time=datetime.now(timezone.utc),
        duration_minutes=30,
        participants=[MeetingParticipant(name='Ari')],
    )
    conversation = SimpleNamespace(
        id='invented',
        source='desktop',
        external_data={'conversation_role': 'meeting'},
        transcript_segments=[],
        started_at=calendar.start_time,
        finished_at=calendar.start_time,
    )
    results = []
    for episode in (False, True):
        reads.clear()
        documents.clear()
        wiring.rich_notes_inputs(
            'invented',
            conversation,
            calendar,
            'UTC',
            include_background=True,
            include_screen_text=True,
            **({'evidence_items': []} if episode else {}),
        )
        results.append((dict(reads), dict(documents)))
    assert results[0] == results[1]
    assert all(count == 1 for count in results[1][0].values())
    assert sum(results[1][1].values()) == 91


def test_long_fallback_background_reuses_ocr_query(runtime, monkeypatch):
    _, wiring, sources, _ = runtime
    from utils.conversations.meeting_context_render import MeetingContextPack
    from utils.conversations.meeting_participants import MeetingRoster

    calls = []
    pack = MeetingContextPack(
        screen_rows=({'appName': 'Browser', 'windowTitle': 'Pricing', 'ocrText': 'Pricing draft'},)
    )
    monkeypatch.setattr(sources, 'gather_meeting_context_pack', lambda *a, **k: calls.append(k) or pack)
    evidence = []
    background = wiring._rich_meeting_context_block(
        'invented',
        SimpleNamespace(),
        MeetingRoster(entries=(), display_title=None, title_is_window_title=False),
        [],
        'UTC',
        include_screen_text=True,
        evidence_items=evidence,
    )
    assert len(calls) == 1 and calls[0]['preserve_screen_rows']
    assert 'Pricing draft' in background
    assert 'Pricing draft' in evidence[0].content

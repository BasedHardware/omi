"""Batch abstention is missing attribution, never another person or the wearer."""

from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from models.speaker_evidence import SpeakerCandidate, SpeakerEvidence, VoiceCluster
from models.transcript_segment import TranscriptSegment
from tests.unit.fixtures.speaker_abstention import speaker_cases
from utils.speakers.display import developer_speaker_names, display_participants

FLAG = 'SPEAKER_ABSTENTION_UNKNOWN_LABEL_ENABLED'


@pytest.fixture(autouse=True)
def _default_on(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


@pytest.fixture(scope='module', autouse=True)
def _warm_imports():
    for module in (
        'utils.conversations.render',
        'utils.conversations.transcript_for_llm',
        'utils.conversations.mcp_transcript_search',
        'utils.episodes.incremental',
        'utils.review',
    ):
        import_module(module)


@pytest.mark.parametrize('case', speaker_cases())
def test_labels_participants_and_storage(case):
    rows, ids = speaker_cases()[case]
    before = deepcopy(rows)
    display = display_participants(rows, resolution={'status': 'capture', 'participant_speaker_ids': ids})
    expected = {
        'one-voice': ['Speaker A', 'Unknown speaker', 'Unknown speaker'],
        'two-voices': ['Speaker A', 'Unknown speaker', 'Speaker B', 'Unknown speaker'],
        'wearer': ['You', 'Unknown speaker', 'Unknown speaker'],
        'mixed-epochs': ['Speaker A', 'Unknown speaker', 'Speaker B', 'Unknown speaker'],
        'point-keys': ['Speaker A', 'Unknown speaker', 'Unknown speaker'],
        'historical-fallback': ['Speaker A', 'Unknown speaker', 'Unknown speaker'],
    }[case]
    assert [display.label(row) for row in rows] == expected
    assert developer_speaker_names(rows, names={}, owner_name='You') == expected
    assert len(display.participants) == len(rows)  # distinct gap correction/provenance keys
    assert sum(p.countable for p in display.participants) == len(ids)
    # Acceptance metric: distinct attributed labels shown minus participant_speaker_ids == 0.
    labels_shown = {display.label(row) for row in rows} - {'Unknown speaker'}
    assert len(labels_shown) - len(ids) == 0
    assert rows == before


@pytest.mark.parametrize(
    'marker',
    [
        {'speaker': 'BATCH_UNASSIGNED_part_gap'},
        {'speaker_match_source': 'batch_abstention'},
        {'speaker_identity_status': 'batch_abstention'},
        {'identity_status': 'batch_abstention'},
    ],
)
def test_each_marker_overrides_stale_person_and_wearer(marker):
    row = dict(id='gap', speaker_id=99, is_user=True, person_id='p', speaker_label_source='carried', **marker)
    display = display_participants([row], names={'p': 'Ada'}, resolution={'status': 'resolved'})
    assert display.label(row) == 'Unknown speaker'
    assert display.for_segment(row).name is None
    assert not display.for_segment(row).countable
    assert developer_speaker_names([NS(**row)], names={'p': 'Ada'}, owner_name='You') == ['Unknown speaker']


def test_stale_evidence_cannot_merge_gaps_into_a_person():
    rows, _ = speaker_cases()['one-voice']
    evidence = SpeakerEvidence(
        status='resolved',
        policy_version='test',
        clusters=[
            VoiceCluster(
                id='voice',
                segment_ids=[row['id'] for row in rows],
                speech_seconds=18,
                candidates=[
                    SpeakerCandidate(
                        person_id='owner',
                        name='You',
                        probability=0.99,
                        band='confident',
                        source='voice',
                        label_eligible=True,
                    )
                ],
            )
        ],
    )
    display = display_participants(rows, evidence=evidence)
    assert [display.label(row) for row in rows] == ['You', 'Unknown speaker', 'Unknown speaker']
    assert len({display.for_segment(row).key for row in rows}) == 3
    assert sum(p.countable for p in display.participants) == 1


@pytest.mark.parametrize('gap_position', range(3))
def test_real_letters_ignore_gap_position_and_episode_ledger(gap_position):
    rows, _ = speaker_cases()['two-voices']
    voices = [rows[0], rows[2]]
    gap = rows[1]
    voices.insert(gap_position, gap)
    for kwargs in ({}, {'voice_order': [], 'defer_short_voices': True}):
        display = display_participants(voices, **kwargs)
        assert display.label(rows[0]) == 'Speaker A'
        assert display.label(rows[2]) == 'Speaker B'
        assert display.label(gap) == 'Unknown speaker'
        assert developer_speaker_names(voices, names={}, owner_name='You') == [display.label(r) for r in voices]
        if 'voice_order' in kwargs:
            assert len(display.voice_order) == 2


def test_many_gaps_never_spend_overflow_slots_or_collapse_keys():
    rows, _ = speaker_cases()['one-voice']
    rows += [dict(rows[1], id=f'gap-{i}', speaker_id=i, speaker=f'BATCH_UNASSIGNED_part_{i}') for i in range(3, 20)]
    display = display_participants(rows, voice_order=[], defer_short_voices=True)
    assert display.label(rows[0]) == 'Speaker A'
    assert {display.label(row) for row in rows[1:]} == {'Unknown speaker'}
    assert len(display.voice_order) == 1
    assert len(display.participants) == len(rows)


@pytest.mark.parametrize('disabled', ['false', '0', 'off', 'no'])
@pytest.mark.parametrize('case', speaker_cases())
def test_kill_switch_restores_old_labels(monkeypatch, disabled, case):
    rows, _ = speaker_cases()[case]
    monkeypatch.setenv(FLAG, disabled)
    expected = {
        'one-voice': ['Speaker A', 'Speaker B', 'Speaker C'],
        'two-voices': ['Speaker A', 'Speaker B', 'Speaker C', 'Speaker D'],
        'wearer': ['You', 'Speaker A', 'Speaker B'],
        'mixed-epochs': ['Speaker A', 'Speaker B', 'Speaker C', 'Speaker D'],
        'point-keys': ['Speaker A', 'Speaker B', 'Speaker C'],
        'historical-fallback': ['Speaker A', 'Speaker B', 'Speaker B'],
    }[case]
    assert [display_participants(rows).label(row) for row in rows] == expected
    assert developer_speaker_names(rows, names={}, owner_name='You') == expected


@pytest.mark.parametrize('preserve', [False, True])
def test_conversation_api_including_developer_values(monkeypatch, preserve):
    from utils.conversations import render

    monkeypatch.setattr(render, 'get_user_name', lambda *_a, **_kw: None)
    for rows, ids in speaker_cases().values():
        conversation = {
            'transcript_segments': rows,
            'speaker_resolution': {'status': 'capture', 'participant_speaker_ids': ids},
        }
        render.populate_speaker_names('fictional', [conversation], preserve_api_values=preserve)
        expected = (
            developer_speaker_names(rows, names={}, owner_name='User')
            if preserve
            else [display_participants(rows).label(row) for row in rows]
        )
        assert [row['speaker_name'] for row in rows] == expected
        assert expected.count('Unknown speaker') == 2


@pytest.mark.parametrize('case', speaker_cases())
def test_all_server_consumers(monkeypatch, case):
    from utils import review
    from utils.conversations import transcript_for_llm as llm
    from utils.conversations.analytics import build_conversation_analytics
    from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
    from utils.episodes import incremental

    rows, ids = speaker_cases()[case]
    segments = [TranscriptSegment(**row) for row in rows]
    conversation = NS(
        id='fictional',
        transcript_segments=segments,
        speaker_resolution={'status': 'capture', 'participant_speaker_ids': ids},
    )
    monkeypatch.setattr(llm, 'get_user_name', lambda *_a, **_kw: 'You')
    monkeypatch.setattr(llm, 'serving_for', lambda *_a: False)
    monkeypatch.setattr(incremental, 'shadow_or_serve', lambda *_a: False)
    monkeypatch.setattr(
        review.conversations,
        'get_conversation',
        lambda *_a: {'transcript_segments': rows, 'started_at': datetime(2026, 11, 1, tzinfo=timezone.utc)},
    )
    monkeypatch.setattr(review.conversations, 'is_visible_conversation', lambda *_a: True)
    prompt = NS(
        conversation_id='fictional',
        segment_ids=[rows[1]['id']],
        id='prompt',
        excerpt=rows[1]['text'],
        conversation_title='Fictional garden plan',
        clip_start=6,
        clip_end=12,
        candidates=[],
    )
    review_item = review._speaker_item('fictional', prompt)
    assert review_item.speaker.context[1].speaker_label == 'Unknown speaker'
    candidate = NS(
        workstream_id=None,
        candidate_id='task',
        created_at=datetime.now(timezone.utc),
        task_change=NS(description='Bring tools', due_at=None),
        evidence_refs=[NS(kind=NS(value='conversation'), id='fictional', transcript_segment_ids=[rows[1]['id']])],
    )
    assert review._task_item('fictional', candidate).task.evidence.speaker_label == 'Unknown speaker'
    snippets = build_transcript_match_snippets(rows, 'seedlings')
    assert any('[unassigned speech]: The seedlings arrive Friday.' in snippet['text'] for snippet in snippets)
    assert any(snippet['speaker_label'] == '[unassigned speech]' for snippet in snippets)
    outputs = [
        llm.render_cluster_transcript(rows, names={})[0],
        llm.conversation_transcript_and_speaker_map('fictional', conversation)[0],
        llm.memory_transcript_from_segments(segments),
        TranscriptSegment.segments_as_string(segments),
        incremental.render_moment(rows, voice_order=[]).text,
    ]
    if case == 'wearer':
        for output in (outputs[2], outputs[3], outputs[4]):
            assert [line.split(': ', 1)[0] for line in output.splitlines() if ': ' in line] == [
                'You',
                '[unassigned speech]',
                '[unassigned speech]',
            ]
        for output in outputs[:2]:
            assert [line.split('] ', 1)[1] for line in output.splitlines() if line.startswith('[turn-')] == [
                rows[0]['text'],
                '[unassigned speech] ' + rows[1]['text'],
                '[unassigned speech] ' + rows[2]['text'],
            ]
    for output in outputs:
        assert '[unassigned speech]' in output
        assert 'Unknown speaker' not in output
        assert 'Speaker C' not in output and 'Speaker D' not in output
        for row in rows:
            assert output.count(row['text']) == 1
    analytics = build_conversation_analytics(conversation, {})
    assert analytics.speaker_count == len(ids)
    assert len(analytics.speakers) == len(rows)
    assert sum(s.speaker == 'Unknown speaker' for s in analytics.speakers) == 2
    assert analytics.total_seconds == sum(row['end'] - row['start'] for row in rows)


@pytest.mark.parametrize('case', speaker_cases())
def test_exact_api_mcp_llm_snapshots_and_raw_inventory(case):
    from tests.unit.fixtures.speaker_abstention_outputs import snapshot

    root = Path(__file__).resolve().parent / 'fixtures/speaker_abstention_snapshots'
    expected = json.loads((root / f'{case}.json').read_text())
    actual = snapshot(case)
    assert actual == expected
    assert actual['before']['inventory'] == actual['after']['inventory']
    assert actual['after']['label_participant_delta'] == 0
    for state in ('before', 'after'):
        rows = actual[state]['api']['transcript_segments']
        for text in ('llm_plain', 'llm_compact', 'llm_legacy_compact'):
            for row in rows:
                assert actual[state][text].count(row['text']) == 1
        assert len(actual[state]['mcp_segments']) == len(rows)
    keys = [r['speaker_key'] for r in actual['after']['mcp_segments']]
    assert len(keys) == len(set(keys))
    for row, projected in zip(actual['after']['api']['transcript_segments'], actual['after']['mcp_segments']):
        if row['speaker'].startswith('BATCH_UNASSIGNED_'):
            assert projected['speaker_label'] == '[unassigned speech]'
            assert actual['after']['llm_bindings'][projected['speaker_key']] is None
            assert actual['after']['llm_legacy_bindings'][projected['speaker_key']] is None


def test_llm_normalizers_preserve_unassigned_semantics():
    from utils.conversations.shared_chat import build_bounded_transcript
    from utils.conversations.smart_merge_state import transcript_lines
    from utils.conversations.transcript_chunks import build_transcript_chunks
    from utils.speakers.display import prompt_speaker_map, sanitize_speaker_text

    rows, _ = speaker_cases()['one-voice']
    for text in (
        build_bounded_transcript(rows, max_chars=5000),
        '\n'.join(transcript_lines(rows)),
        build_transcript_chunks(rows, None)[0]['text'],
    ):
        assert text.count('[unassigned speech]') == 2
        assert 'Unknown speaker' not in text
        for row in rows:
            assert text.count(row['text']) == 1
        assert sanitize_speaker_text(text).count('[unassigned speech]') == 2
        assert prompt_speaker_map(text, {0: None, 1: None, 2: None})[0].count('[unassigned speech]') == 2


def test_stale_wearer_receipts_cannot_name_or_group_gap_projections(monkeypatch):
    from utils.conversations import transcript_for_llm as llm
    from utils.conversations.analytics import build_conversation_analytics
    from utils.mcp_server.helpers import bounded_transcript_segments, conversation_participants

    rows, ids = speaker_cases()['wearer']
    for row in rows[1:]:
        row.update(is_user=True, person_id='stale-person', speaker_label_source='carried')
    before = deepcopy(rows)
    segments = [TranscriptSegment(**r) for r in rows]
    conversation = NS(
        id='fictional',
        transcript_segments=segments,
        speaker_resolution={'status': 'capture', 'participant_speaker_ids': ids},
    )
    analytics = build_conversation_analytics(conversation, {'stale-person': 'Ada'})
    assert analytics.speaker_count == 1
    assert len(analytics.speakers) == 3
    for row in analytics.speakers:
        if row.speaker == 'Unknown speaker':
            assert not row.is_user and row.person_id is None
    projected = bounded_transcript_segments(rows, max_segments=10, max_chars=5000, extra_keys=('speaker_name',))[0]
    participants = conversation_participants({'transcript_segments': rows})['participants']
    assert len(participants) == 1 and participants[0]['is_user']
    assert len(projected) == 3
    for gap in projected[1:]:
        assert gap['speaker_label'] == '[unassigned speech]'
        assert not gap['is_user'] and gap['person_id'] is None
    monkeypatch.setattr(llm, 'get_user_name', lambda *_a, **_kw: 'You')
    labels = llm.conversation_action_item_speaker_labels('fictional', conversation)
    assert [r['speaker_role'] for r in labels[1:]] == ['unknown', 'unknown']
    assert rows == before


def test_evidence_cluster_containing_only_abstentions_has_no_identity_or_slots(monkeypatch):
    from utils.speakers import display as policy

    rows = speaker_cases()['one-voice'][0][1:]
    before = deepcopy(rows)
    evidence = SpeakerEvidence(
        status='resolved',
        policy_version='test',
        clusters=[
            VoiceCluster(
                id='gaps-only',
                segment_ids=[r['id'] for r in rows],
                speech_seconds=12,
                candidates=[
                    SpeakerCandidate(
                        person_id='owner',
                        name='You',
                        probability=0.99,
                        band='confident',
                        source='voice',
                        label_eligible=True,
                    )
                ],
            )
        ],
    )
    trips = []
    monkeypatch.setattr(policy, 'record_count_guard', lambda: trips.append(True))
    display = display_participants(rows, evidence=evidence, voice_order=[], defer_short_voices=True)
    assert [display.label(r) for r in rows] == ['Unknown speaker', 'Unknown speaker']
    assert [display.prompt_label(r) for r in rows] == ['[unassigned speech]', '[unassigned speech]']
    assert len(display.participants) == 2
    assert sum(p.countable for p in display.participants) == 0
    assert sum(p.speech_seconds for p in display.participants) == 12
    assert not display.voice_order and not trips
    assert rows == before


def test_marker_only_gaps_with_shared_raw_id_keep_per_segment_keys():
    rows = [
        dict(
            id=f'gap-{i}',
            speaker_id=-1,
            speaker_id_scope='final:batch',
            is_user=False,
            speaker_match_source='batch_abstention',
        )
        for i in range(2)
    ]
    display = display_participants(rows)
    assert [display.label(r) for r in rows] == ['Unknown speaker', 'Unknown speaker']
    assert len({display.for_segment(r).key for r in rows}) == 2
    assert [display.for_segment(dict(r)).key for r in rows] == [display.for_segment(r).key for r in rows]


@pytest.mark.parametrize('roles_enabled', [True, False])
def test_speaker_map_never_takes_owner_from_abstention(monkeypatch, roles_enabled):
    from utils.conversations import transcript_for_llm as llm

    monkeypatch.setenv('SPEAKER_ROLE_PROJECTION_ENABLED', str(roles_enabled).lower())
    rows = speaker_cases()['one-voice'][0]
    for row in rows[1:]:
        row.update(is_user=True, speaker_label_source='carried')
    segments = [TranscriptSegment(**r) for r in rows]
    mapping = llm._speaker_map(segments, 'You', {})
    assert len(mapping.clusters) == 3
    assert all(not cluster.owner for cluster in mapping.clusters)
    assert all(name is None for name in mapping.values())


def test_mcp_roster_excludes_gaps_but_transcripts_keep_every_word(monkeypatch):
    from utils.mcp_server.helpers import bounded_transcript_segments, conversation_participants

    rows, ids = speaker_cases()['one-voice']
    rows[1].update(speaker_id=None, person_id='stale', speaker_label_source='carried')
    payload = {'transcript_segments': rows, 'speaker_resolution': {'status': 'capture', 'participant_speaker_ids': ids}}
    roster = conversation_participants(payload)
    assert len(roster['participants']) == 1
    assert roster['person_ids'] == []
    transcript = bounded_transcript_segments(rows, max_segments=10, max_chars=5000)[0]
    assert [r['text'] for r in transcript] == [r['text'] for r in rows]
    assert len({r['speaker_key'] for r in transcript}) == 3
    monkeypatch.setenv(FLAG, 'false')
    assert len(conversation_participants(payload)['participants']) == 3


@pytest.mark.parametrize('is_user', [False, True])
@pytest.mark.parametrize('source', ['manual', 'carried'])
def test_applied_gap_receipts_win_every_presentation_surface(monkeypatch, is_user, source):
    from utils import review
    from utils.manual_speaker_assignments import apply_manual_assignments
    from utils.conversations import render, transcript_for_llm as llm
    from utils.conversations.analytics import build_conversation_analytics
    from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
    from utils.episodes import incremental, moment_render
    from utils.mcp_server.helpers import bounded_transcript_segments, conversation_participants

    rows, _ = speaker_cases()['one-voice']
    gap = rows[1]
    receipt = {
        'generation': 3,
        'speakers': {
            str(gap['speaker_id']): {
                'generation': 3,
                'person_id': None if is_user else 'ada',
                'is_user': is_user,
                'speaker_id_scope': gap['speaker_id_scope'],
                **({'source': 'carried'} if source == 'carried' else {}),
            }
        },
    }
    rows = apply_manual_assignments(rows, receipt)
    bound = rows[1]
    assert bound['speaker'].startswith('BATCH_UNASSIGNED_')
    assert bound['speaker_match_source'] is None
    assert bound['speaker_label_source'] == source
    assert bound['person_id'] == (None if is_user else 'ada') and bound['is_user'] == is_user
    before = deepcopy(rows)
    names = {'ada': 'Ada'}
    expected_name = 'You' if is_user else 'Ada'
    resolution = {'status': 'capture', 'participant_speaker_ids': [0, 1]}
    display = display_participants(rows, names=names, resolution=resolution)
    assert [display.label(r) for r in rows] == ['Speaker A', expected_name, 'Unknown speaker']
    assert not display.for_segment(bound).is_abstention
    assert sum(p.countable for p in display.participants) == 2
    assert developer_speaker_names(rows, names=names, owner_name='You') == [
        'Speaker A',
        expected_name,
        'Unknown speaker',
    ]
    monkeypatch.setattr(render, 'get_user_name', lambda *_a, **_kw: 'You')
    monkeypatch.setattr(render.users_db, 'get_people_by_ids', lambda *_a: [{'id': 'ada', 'name': 'Ada'}])
    for preserve in (False, True):
        payload = {'transcript_segments': deepcopy(rows), 'speaker_resolution': resolution}
        render.populate_speaker_names('fictional', [payload], preserve_api_values=preserve)
        assert [r['speaker_name'] for r in payload['transcript_segments']] == [
            'Speaker A',
            expected_name,
            'Unknown speaker',
        ]
    monkeypatch.setattr(
        review.conversations,
        'get_conversation',
        lambda *_a: {
            'transcript_segments': rows,
            'speaker_resolution': resolution,
            'started_at': datetime(2026, 11, 1, tzinfo=timezone.utc),
        },
    )
    monkeypatch.setattr(review.conversations, 'is_visible_conversation', lambda *_a: True)
    prompt = NS(
        conversation_id='fictional',
        segment_ids=[bound['id']],
        id='p',
        excerpt=bound['text'],
        conversation_title='Fictional',
        clip_start=6,
        clip_end=12,
        candidates=[],
    )
    # Review intentionally uses generic letters when it has no people lookup.
    review_label = 'You' if is_user else 'Speaker B'
    assert review._speaker_item('fictional', prompt).speaker.context[1].speaker_label == review_label
    candidate = NS(
        workstream_id=None,
        candidate_id='task',
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        task_change=NS(description='Bring tools', due_at=None),
        evidence_refs=[NS(kind=NS(value='conversation'), id='fictional', transcript_segment_ids=[bound['id']])],
    )
    assert review._task_item('fictional', candidate).task.evidence.speaker_label == review_label
    roster = conversation_participants({'transcript_segments': rows, 'speaker_resolution': resolution})['participants']
    assert len(roster) == 2
    assert roster[1]['is_user'] == is_user and roster[1]['person_id'] == (None if is_user else 'ada')
    projected = bounded_transcript_segments(payload['transcript_segments'], max_segments=10, max_chars=5000)[0]
    assert projected[1]['speaker_label'] == expected_name
    assert projected[1]['is_user'] == is_user and projected[1]['person_id'] == (None if is_user else 'ada')
    snippets = build_transcript_match_snippets(rows, 'seedlings')
    assert snippets[0]['speaker_label'] == review_label
    assert '[unassigned speech]: The seedlings' not in snippets[0]['text']
    segments = [TranscriptSegment(**r) for r in rows]
    conversation = NS(id='fictional', transcript_segments=segments, speaker_resolution=resolution)
    analytics = build_conversation_analytics(conversation, names)
    assert analytics.speaker_count == 2 and len(analytics.speakers) == 3
    assert {r.speaker for r in analytics.speakers} == {'Speaker A', expected_name, 'Unknown speaker'}
    monkeypatch.setattr(llm, 'get_user_name', lambda *_a, **_kw: 'You')
    monkeypatch.setattr(llm, 'serving_for', lambda *_a: False)
    monkeypatch.setattr(incremental, 'shadow_or_serve', lambda *_a: False)
    # Episode people names are supplied by the existing trusted name projection.
    episode_rows = moment_render.name_segments(rows, names)
    assert f'{expected_name}: {bound["text"]}' in incremental.render_moment(episode_rows).text
    people = [NS(id='ada', name='Ada')]
    plain = TranscriptSegment.segments_as_string(segments, people=people, user_name='You')
    assert f'{expected_name}: {bound["text"]}' in plain
    # Current carried owner flags remain subject to the existing independent
    # owner-evidence gate in LLM memory input; manual owner decisions are authoritative.
    if source == 'manual' or not is_user:
        for text, mapping in (
            llm.render_cluster_transcript(rows, names=names),
            llm.conversation_transcript_and_speaker_map('fictional', conversation, people=people),
        ):
            assert expected_name in mapping.values()
            assert '[unassigned speech] ' + bound['text'] not in text
        assert f'{expected_name}: {bound["text"]}' in llm.memory_transcript_from_segments(segments, people=people)
        labels = llm.conversation_action_item_speaker_labels('fictional', conversation, people=people)
        assert labels[1]['speaker_label'] == expected_name
        assert labels[1]['speaker_role'] == ('primary_user' if is_user else 'other')
    assert rows == before


@pytest.mark.parametrize('is_user', [False, True])
def test_stale_carried_gap_receipt_does_not_win(is_user):
    from utils.manual_speaker_assignments import apply_manual_assignments

    rows = speaker_cases()['one-voice'][0]
    gap = rows[1]
    gap.update(is_user=is_user, person_id=None if is_user else 'ada', speaker_label_source='carried')
    receipt = {
        'generation': 4,
        'speakers': {
            str(gap['speaker_id']): {
                'generation': 4,
                'speaker_id_scope': 'obsolete-epoch',
                'source': 'carried',
                'person_id': None if is_user else 'ada',
                'is_user': is_user,
            }
        },
    }
    result = apply_manual_assignments(rows, receipt)
    assert result is rows
    display = display_participants(result, names={'ada': 'Ada'})
    assert display.label(gap) == 'Unknown speaker'
    assert not display.for_segment(gap).countable


@pytest.mark.parametrize('model', [False, True])
def test_legacy_carried_defaults_are_not_a_reapplied_receipt(model):
    row = dict(
        id='legacy',
        speaker='BATCH_UNASSIGNED_old',
        speaker_id=-1,
        is_user=True,
        speaker_label_source='carried',
        start=0,
        end=6,
        text='Fictional gap words',
    )
    row = TranscriptSegment(**row) if model else row
    display = display_participants([row])
    assert display.label(row) == 'Unknown speaker'
    assert not display.for_segment(row).countable


def test_speaker_map_preserves_attributed_role_owner_without_raw_owner_flag():
    from utils.conversations import transcript_for_llm as llm
    from utils.conversations.owner_attribution import SpeakerRole, SpeakerRoleMap

    rows = [
        TranscriptSegment(
            id='real', speaker='SPEAKER_00', speaker_id=0, is_user=False, text='Fictional words', start=0, end=6
        )
    ]
    roles = SpeakerRoleMap(
        rows=tuple(rows),
        roles=(SpeakerRole(role='primary_user'),),
        clusters={(None, 0): SpeakerRole(role='primary_user')},
    )
    mapping = llm._speaker_map(rows, 'You', {}, roles=roles)
    assert mapping.clusters[0].owner

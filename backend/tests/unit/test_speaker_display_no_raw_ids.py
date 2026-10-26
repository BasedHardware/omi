"""Presentation contract for 378/379, scoped evidence and over-split diarization."""

from types import SimpleNamespace as NS
import pytest

from utils.speakers.display import DiarizationLabel, display_participants
from models.speaker_evidence import SpeakerEvidence, SpeakerCandidate, VoiceCluster


@pytest.fixture(scope='module', autouse=True)
def _warm_formatter_imports():
    # Imports belong to setup, outside test.sh's per-test CPU correctness budget.
    from importlib import import_module

    for module in (
        'utils.conversations.transcript_for_llm',
        'utils.conversations.render',
        'utils.conversations.mcp_transcript_search',
        'utils.episodes.incremental',
        'utils.review',
        'utils.mcp_server.helpers',
    ):
        import_module(module)


def row(speaker_id=378, **kwargs):
    return dict(id='turn', speaker_id=speaker_id, is_user=False, text='hello', start=0, end=1, **kwargs)


def test_raw_type_cannot_be_formatted():
    label = DiarizationLabel(379)
    with pytest.raises(TypeError):
        str(label)
    with pytest.raises(TypeError):
        f'{label}'
    assert '379' not in repr(label)
    assert label.raw_for_transport == 379
    # Retain the dependency's small-label alphabet contract.
    from utils.speaker_display import SpeakerLabeler

    alphabet = SpeakerLabeler()
    for index in range(30):
        alphabet.label((None, index))
    assert alphabet.label((None, 100)) == 'Speaker AE'


def test_full_conversation_first_appearance_names_scopes_and_owner():
    rows = [row(0) | {'is_user': True}, row(378, person_id='ada'), row(379), row(379, speaker_id_scope='restart')]
    display = display_participants(rows, names={'ada': 'Ada'})
    assert [display.label(r) for r in rows] == ['You', 'Ada', 'Speaker B', 'Speaker C']
    assert display.label(rows[-1]) == 'Speaker C'  # an excerpt never starts again at A
    assert len({display.for_segment(r).key for r in rows}) == 4
    assert sum(p.countable for p in display.participants) == 2


def test_sanity_guard_uses_seconds_without_changing_storage(monkeypatch):
    from utils.speakers import display as display_policy

    trips = []
    monkeypatch.setattr(display_policy, 'record_count_guard', lambda: trips.append(1))
    rows = [row(378) | {'end': 40}, *[row(n) for n in range(400, 417)], row(379, person_id='ada')]
    display = display_participants(rows, names={'ada': 'Ada'}, resolution={'status': 'resolved'})
    assert display.label(rows[0]) == 'Speaker A'
    assert {display.label(r) for r in rows[1:-1]} == {'Others'}
    assert display.label(rows[-1]) == 'Ada'
    assert sum(p.countable for p in display.participants) == 2
    assert len(display.participants) == 3
    assert trips == [1]
    assert rows[1]['speaker_id'] == 400


def test_evidence_policy_eligibility_and_seconds_are_authoritative():
    rows = [row(378), row(379) | {'id': 'second'}]
    evidence = SpeakerEvidence(
        status='resolved',
        policy_version='test',
        clusters=[
            VoiceCluster(
                id='v378',
                segment_ids=['turn'],
                speech_seconds=12,
                candidates=[
                    SpeakerCandidate(person_id='ada', name='Ada', probability=0.99, band='confident', source='roster'),
                ],
            ),
            VoiceCluster(
                id='v379',
                segment_ids=['second'],
                speech_seconds=10,
                candidates=[
                    SpeakerCandidate(
                        person_id='ada', name='Ada', probability=0.9, band='likely', source='voice', label_eligible=True
                    ),
                ],
            ),
        ],
    )
    display = display_participants(rows, evidence=evidence)
    assert display.label(rows[0]) == 'Speaker A'
    assert display.label(rows[1]) == 'likely Ada'
    assert display.for_segment(rows[0]).speech_seconds == 12
    assert all('378' not in p.key and '379' not in p.key for p in display.participants)


@pytest.mark.parametrize('status, count', [('unavailable', 0), ('resolved', 2), ('capture', 2)])
def test_count_only_supported_voices(status, count):
    rows = [row(378), row(379)]
    assert sum(p.countable for p in display_participants(rows, resolution=NS(status=status)).participants) == count


def test_every_transcript_boundary_rejects_high_raw_ids(monkeypatch):
    import json
    from datetime import datetime, timezone
    from models.transcript_segment import TranscriptSegment
    from utils.conversations import transcript_for_llm as llm, render
    from utils.conversations.analytics import build_conversation_analytics
    from utils.conversations.mcp_transcript_search import build_transcript_match_snippets
    from utils.conversations.shared_chat import build_bounded_transcript
    from utils.conversations.smart_merge_state import transcript_lines
    from utils.conversations.transcript_chunks import build_transcript_chunks
    from utils.episodes import incremental, moment_render
    from utils.mcp_server.helpers import conversation_participants, bounded_transcript_segments
    from utils import review

    rows = [row(378) | {'id': 'first'}, row(379) | {'id': 'second'}]
    segments = [TranscriptSegment(**r) for r in rows]
    conversation = NS(
        id='conversation',
        transcript_segments=segments,
        get_transcript=lambda *_a, **kw: TranscriptSegment.segments_as_string(segments, **kw),
    )
    monkeypatch.setattr(llm, 'get_user_name', lambda *_a, **_kw: 'David')
    monkeypatch.setattr(llm, 'serving_for', lambda *_a: False)
    monkeypatch.setattr(incremental, 'shadow_or_serve', lambda *_a: False)
    monkeypatch.setattr(render, 'get_user_name', lambda *_a, **_kw: 'David')
    monkeypatch.setattr(
        review.conversations,
        'get_conversation',
        lambda *_a: {'transcript_segments': rows, 'started_at': datetime(2026, 10, 1, tzinfo=timezone.utc)},
    )
    monkeypatch.setattr(review.conversations, 'is_visible_conversation', lambda *_a: True)
    prompt = NS(
        conversation_id='conversation',
        segment_ids=['second'],
        id='prompt',
        excerpt='hello',
        conversation_title='Title',
        clip_start=0,
        clip_end=1,
        candidates=[],
    )
    review_item = review._speaker_item('uid', prompt)
    candidate = NS(
        workstream_id=None,
        candidate_id='candidate',
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        task_change=NS(description='Follow up', due_at=None),
        evidence_refs=[NS(kind=NS(value='conversation'), id='conversation', transcript_segment_ids=['second'])],
    )
    task_review = review._task_item('uid', candidate)
    payload = {'transcript_segments': [dict(r) for r in rows]}
    render.populate_speaker_names('uid', [payload])
    compact, speaker_map = llm.conversation_transcript_and_speaker_map('uid', conversation)
    evidence_compact, evidence_map = llm.render_cluster_transcript(rows, names={})
    outputs = {
        'normal/notes/chat/exports': TranscriptSegment.segments_as_string(segments),
        'conversation': llm.conversation_transcript_for_llm('uid', conversation),
        'compact': compact,
        'speaker_map': json.dumps(speaker_map),
        'memory': llm.memory_transcript_from_segments(segments),
        'action_labels': json.dumps(llm.conversation_action_item_speaker_labels('uid', conversation)),
        'evidence_notes': evidence_compact,
        'evidence_map': json.dumps(evidence_map),
        'live_notes_and_titles': incremental.render_moment(rows, owner_name='David').text,
        'moment_packet': moment_render.render_segments(rows)[0],
        'review': review_item.model_dump_json(),
        'task_review': task_review.model_dump_json(),
        'api_speaker_names': json.dumps([s['speaker_name'] for s in payload['transcript_segments']]),
        'merge': '\n'.join(transcript_lines(rows)),
        'chunks': json.dumps(build_transcript_chunks(rows, None)),
        'search_snippets': json.dumps(build_transcript_match_snippets(rows, 'hello')),
        'shared_chat': build_bounded_transcript(rows, max_chars=1000),
        'analytics': build_conversation_analytics(conversation, {}).model_dump_json(),
        'mcp_participants': json.dumps(conversation_participants({'transcript_segments': rows})),
        'mcp_segments': json.dumps(bounded_transcript_segments(rows, max_segments=10, max_chars=1000)),
    }
    for site, output in outputs.items():
        assert '378' not in output and '379' not in output and 'SPEAKER_' not in output, (site, output)


def test_live_moments_keep_the_episode_order_and_bound_the_ledger(monkeypatch):
    from utils.episodes import incremental

    monkeypatch.setattr(incremental, 'shadow_or_serve', lambda *_a: False)
    first = incremental.render_moment(
        [dict(row(378), end=5), dict(row(379), end=5)], conversation_id='c', voice_order=[]
    )
    second = incremental.render_moment([dict(row(379), end=5)], conversation_id='c', voice_order=first.voice_order)
    assert second.text == 'Speaker B: hello'
    assert first.voice_order == second.voice_order
    flooded = incremental.render_moment(
        [row(n) for n in range(400, 430)], conversation_id='c', voice_order=first.voice_order
    )
    assert len(flooded.voice_order) <= 9
    assert 'Others' in flooded.text
    assert all('378' not in token and '379' not in token for token in second.voice_order)


def test_many_known_people_do_not_trigger_unnamed_guard(monkeypatch):
    from utils.speakers import display as display_policy

    trips = []
    monkeypatch.setattr(display_policy, 'record_count_guard', lambda: trips.append(1))
    rows = [row(i, person_id=f'p{i}') for i in range(20)] + [row(379)]
    names = {f'p{i}': f'Person {i}' for i in range(20)}
    display = display_participants(rows, names=names)
    assert display.label(rows[-1]) == 'Speaker U'
    assert not trips
    live = display_participants(rows, names=names, voice_order=[])
    assert live.label(rows[-1]) == 'Speaker A'
    assert len(live.voice_order) == 1 and not trips


def test_manual_segment_binding_wins_without_promoting_the_cluster():
    rows = [row(378, person_id='ada', speaker_label_source='manual'), row(378) | {'id': 'other'}]
    evidence = SpeakerEvidence(
        status='resolved', policy_version='test', clusters=[VoiceCluster(id='v0', segment_ids=['turn', 'other'])]
    )
    display = display_participants(rows, names={'ada': 'Ada'}, evidence=evidence)
    assert [display.label(r) for r in rows] == ['Ada', 'Speaker A']


def test_old_live_state_and_model_output_cannot_replay_raw_ids():
    import json
    from datetime import datetime, timezone
    from utils.episodes.state import render_state, parse_update
    from utils.episodes.service import to_wire

    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    episode = {
        'id': 'episode',
        'started_at': now,
        'title': 'Speaker 379 mentions plans',
        'bullets': ['Speaker 378 paid'],
        'people': ['Speaker 379'],
        'speaker_display_order': ['opaque-internal'],
        'moments': [{'id': 'moment', 'conversation_id': 'c', 'started_at': now, 'heading': 'Speaker 378 speaks'}],
    }
    replay = render_state(episode)
    wire = json.dumps(to_wire(episode), default=str)
    parsed = parse_update(
        json.dumps({'title': 'Speaker 379 mentions plans', 'people': ['Speaker 378'], 'bullets': ['Speaker 378 paid']}),
        known_item_ids=[],
    )
    assert parsed.title == 'a speaker mentions plans' and parsed.people == []
    assert all('378' not in text and '379' not in text and 'opaque-internal' not in text for text in (replay, wire))
    assert episode['title'] == 'Speaker 379 mentions plans'  # no historical write


def test_evidence_packet_and_transcript_share_the_capped_keyspace():
    from utils.conversations.transcript_for_llm import render_cluster_transcript
    from utils.llm.speaker_evidence_prompt import render_speaker_evidence

    rows = [row(i) | {'id': f'turn-{index}'} for index, i in enumerate(range(378, 395))]
    evidence = SpeakerEvidence(
        status='resolved',
        policy_version='test',
        clusters=[
            VoiceCluster(id=f'v{i}', speaker_id=i, segment_ids=[r['id']], speech_seconds=1)
            for i, r in zip(range(378, 395), rows)
        ],
    )
    packet = render_speaker_evidence(evidence, [])
    transcript, mapping = render_cluster_transcript(rows, names={}, evidence=evidence)
    assert '"voice": "others"' in packet and set(mapping) == {'others'}
    assert all('378' not in text and '379' not in text for text in (packet, transcript))


def test_wire_copies_preserve_names_without_object_identity():
    rows = [row(378), row(379)]
    display = display_participants(rows)
    assert [display.label(dict(r)) for r in rows] == ['Speaker A', 'Speaker B']


def test_prompt_prefix_normalizes_legacy_numeric_speaker_maps():
    from datetime import datetime, timezone
    from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix

    prefix = build_conversation_prompt_prefix(
        conversation_id='conversation',
        transcript='[first 378] hello\n\n[second 379] there',
        started_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        timezone_name='UTC',
        language_code='en',
        speaker_map={378: 'Ada', 379: None},
    )
    assert 'spk c0 Ada' in prefix.context and '[first c0]' in prefix.context
    assert '378' not in prefix.context and '379' not in prefix.context


def test_live_ledger_never_spreads_segment_bound_names_to_unbound_excerpts():
    rows = [dict(row(378), id='named', person_id='ada'), dict(row(378), id='unbound')]
    for defer in (False, True):
        display = display_participants(rows, names={'ada': 'Ada'}, voice_order=[], defer_short_voices=defer)
        assert display.label(rows[0]) == 'Ada'
        assert display.for_segment(rows[1]).name is None
        assert display.label(rows[1]) == ('Unknown speaker' if defer else 'Speaker A')
        assert len(display.voice_order) == (0 if defer else 1)


def test_live_manual_name_keeps_trusted_episode_projection_without_roster_map():
    rows = [dict(row(378), speaker_label_source='manual', person_id='ada', person_name='Ada')]
    display = display_participants(rows, voice_order=[], defer_short_voices=True)
    assert display.label(rows[0]) == 'Ada'
    assert display.for_segment(rows[0]).name == 'Ada'
    assert display.voice_order == ()

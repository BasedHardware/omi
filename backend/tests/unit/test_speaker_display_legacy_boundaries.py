"""No LLM-facing transcript formatter may emit a raw diarization speaker id.

A ``speaker_id`` is a per-conversation diarization counter that reaches the
hundreds in a long conversation. When a formatter renders ``Speaker 378`` into
a prompt, summarizer models copy the label verbatim into user-visible notes
(#23381). Every formatter here must render unnamed voices through
``utils.speaker_display.SpeakerLabeler`` (dense "Speaker A/B/..." labels) or
cluster keys, so the digits 378/379 can never survive a render.

The companion static check ``.github/scripts/check_speaker_label_interpolation.py``
keeps new code from reintroducing an interpolated ``Speaker {speaker_id}``.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from models.transcript_segment import TranscriptSegment
from utils.conversations import mcp_transcript_search, smart_merge_state, transcript_chunks
from utils.conversations.analytics import build_conversation_analytics
from utils.conversations.render import populate_speaker_names
from utils.conversations.shared_chat import build_bounded_transcript
from utils.conversations.transcript_for_llm import conversation_action_item_speaker_labels, render_cluster_transcript
from utils.episodes import incremental
from utils.episodes.moment_render import render_segments
from utils.speaker_display import SpeakerLabeler, voice_key

# The raw ids from the incident: a long live conversation whose "So far" bullets
# read "Speaker 379 mentions...", "Speaker 378 notes...".
RAW_IDS = (378, 379)


def _mapping_segments():
    return [
        {'id': 'seg-1', 'text': 'owner words', 'is_user': True, 'speaker_id': RAW_IDS[0]},
        {'id': 'seg-2', 'text': 'second voice', 'is_user': False, 'speaker_id': RAW_IDS[0]},
        {
            'id': 'seg-3',
            'text': 'third voice elsewhere',
            'is_user': False,
            'speaker_id': RAW_IDS[1],
            'speaker_id_scope': 'conversation:other',
        },
        {'id': 'seg-4', 'text': 'named friend talks', 'is_user': False, 'speaker_id': 4, 'person_id': 'p1'},
    ]


def _model_segments():
    return [
        TranscriptSegment(text='owner words', speaker=f'SPEAKER_{RAW_IDS[0]}', is_user=True, start=0.0, end=2.0),
        TranscriptSegment(text='second voice', speaker=f'SPEAKER_{RAW_IDS[0]}', is_user=False, start=2.0, end=4.0),
        TranscriptSegment(
            text='third voice elsewhere', speaker=f'SPEAKER_{RAW_IDS[1]}', is_user=False, start=4.0, end=6.0
        ),
    ]


def _assert_no_raw_ids(rendered):
    for raw in RAW_IDS:
        assert str(raw) not in rendered, f'raw diarization id {raw} leaked into: {rendered!r}'


def test_labeler_assigns_dense_labels_in_first_appearance_order():
    labeler = SpeakerLabeler()
    assert labeler.label((None, 378)) == 'Speaker A'
    assert labeler.label((None, 378)) == 'Speaker A'
    assert labeler.label((None, 379)) == 'Speaker B'
    # Same numeric id under a different scope is a different voice.
    assert labeler.label(('conversation:other', 378)) == 'Speaker C'
    assert labeler.label((None, 5)) == 'Speaker D'
    # Spreadsheet columns keep labels small past 26 voices.
    wide = SpeakerLabeler()
    for index in range(30):
        wide.label((None, index))
    assert wide.label((None, 100)) == 'Speaker AE'


def test_voice_key_reads_mappings_and_objects():
    assert voice_key({'speaker_id_scope': 's', 'speaker_id': 378}) == ('s', 378)
    assert voice_key(SimpleNamespace(speaker_id_scope=None, speaker_id=379)) == (None, 379)


def test_transcript_segment_segments_as_string_uses_dense_labels():
    rendered = TranscriptSegment.segments_as_string(_model_segments(), user_name='David')
    _assert_no_raw_ids(rendered)
    assert 'David: owner words' in rendered
    assert 'Speaker A: second voice' in rendered
    assert 'Speaker B: third voice elsewhere' in rendered


def test_live_moment_render_keeps_unplaced_voices_unnamed(monkeypatch):
    monkeypatch.delenv('NOTES_PACKET_V2_MODE', raising=False)
    rendered = incremental.render_moment(_mapping_segments(), uid=None)
    _assert_no_raw_ids(rendered.text)
    assert 'You: owner words' in rendered.text
    assert 'Unknown speaker: second voice' in rendered.text
    assert 'Unknown speaker: third voice elsewhere' in rendered.text
    assert 'Unknown speaker: named friend talks' in rendered.text


def test_live_moment_render_uses_dense_labels_after_qualification(monkeypatch):
    monkeypatch.delenv('NOTES_PACKET_V2_MODE', raising=False)
    rows = [dict(row, start=index * 5, end=(index + 1) * 5) for index, row in enumerate(_mapping_segments())]
    rendered = incremental.render_moment(rows, uid=None)
    _assert_no_raw_ids(rendered.text)
    assert 'You: owner words' in rendered.text
    assert 'Speaker A: second voice' in rendered.text
    # (conversation:other, 379) is a distinct voice with its own dense label.
    assert 'Speaker B: third voice elsewhere' in rendered.text
    # No stored person name for p1: the fourth voice is dense too, never "Speaker 4".
    assert 'Speaker C: named friend talks' in rendered.text


def test_cluster_moment_render_never_labels_a_speaker():
    text, _labels = render_segments(_mapping_segments(), owner_name='David')
    _assert_no_raw_ids(text)
    rendered, _map = render_cluster_transcript(_mapping_segments(), names={'p1': 'Minh'}, owner_name='David')
    _assert_no_raw_ids(rendered)


def test_smart_merge_transcript_lines_use_dense_labels():
    lines = '\n'.join(smart_merge_state.transcript_lines(_mapping_segments()))
    _assert_no_raw_ids(lines)
    assert 'You: owner words' in lines
    assert 'Speaker A: second voice' in lines


def test_shared_chat_bounded_transcript_uses_dense_labels():
    rendered = build_bounded_transcript(_mapping_segments(), max_chars=2_000)
    _assert_no_raw_ids(rendered)
    assert 'You: owner words' in rendered
    assert 'Speaker A: second voice' in rendered


def test_mcp_transcript_snippets_use_dense_labels():
    snippets = mcp_transcript_search.build_transcript_match_snippets(_mapping_segments(), 'voice', max_chars=2_000)
    for snippet in snippets:
        _assert_no_raw_ids(snippet.get('text', ''))
    joined = '\n'.join(str(snippet.get('text', '')) for snippet in snippets)
    assert 'Speaker A: second voice' in joined


def test_transcript_chunks_use_dense_labels():
    chunks = transcript_chunks.build_transcript_chunks(_mapping_segments(), datetime(2026, 10, 23, tzinfo=timezone.utc))
    for chunk in chunks:
        _assert_no_raw_ids(chunk.get('text', ''))
    joined = '\n'.join(chunk.get('text', '') for chunk in chunks)
    assert 'Speaker A: second voice' in joined


def test_action_item_speaker_labels_use_dense_labels(monkeypatch):
    import utils.conversations.transcript_for_llm as module

    monkeypatch.setattr(module, 'get_user_name', lambda uid, use_default=True: 'David', raising=False)
    conversation = SimpleNamespace(transcript_segments=_model_segments())
    labels = conversation_action_item_speaker_labels('uid-1', conversation, people=[])
    joined = '\n'.join(item['speaker_label'] for item in labels)
    _assert_no_raw_ids(joined)
    assert 'David' in joined and 'Speaker A' in joined


def test_populate_speaker_names_uses_dense_labels(monkeypatch):
    import utils.conversations.render as module

    monkeypatch.setattr(module, 'get_user_name', lambda uid, use_default=True: 'David', raising=False)
    monkeypatch.setattr(module.users_db, 'get_people_by_ids', lambda uid, ids: [], raising=False)
    conversation = {'transcript_segments': _mapping_segments()}
    populate_speaker_names('uid-1', [conversation])
    names = [segment['speaker_name'] for segment in conversation['transcript_segments']]
    joined = '\n'.join(names)
    _assert_no_raw_ids(joined)
    assert names == ['David', 'Speaker A', 'Speaker B', 'Speaker C']


def test_conversation_analytics_uses_dense_labels():
    segments = [
        SimpleNamespace(text='a b c', start=0.0, end=3.0, is_user=False, speaker_id=RAW_IDS[0]),
        SimpleNamespace(text='d e f', start=3.0, end=6.0, is_user=False, speaker_id=RAW_IDS[1]),
    ]
    analytics = build_conversation_analytics(SimpleNamespace(id='c1', transcript_segments=segments), {})
    joined = '\n'.join(speaker.speaker for speaker in analytics.speakers)
    _assert_no_raw_ids(joined)
    assert {speaker.speaker for speaker in analytics.speakers} == {'Speaker A', 'Speaker B'}

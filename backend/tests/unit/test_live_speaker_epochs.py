"""Safe live-epoch acceptance: real idle reopen, scoped allocation and live matcher.

Embeddings are deterministic fixtures, not a claim of real-audio accuracy. Unknown
short epochs stay separate opaque identities even when their labels are unnamed.
"""

from collections import deque
import numpy as np
import pytest

from models.transcript_segment import TranscriptSegment
from routers.listen.transcripts import TranscriptProcessor
from tests.unit.test_speaker_match import _live_matcher, _segment
from tests.unit.test_soniox_idle_close import build, settle
from utils.speakers.display import display_participants
from utils.episodes import incremental
from utils.speakers.policy import CROSS_EPOCH
from utils.stt.speaker_match import group_epoch_voices
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator, SpeakerProviderEpoch
from utils.speaker_assignment import process_speaker_assigned_segments


def test_grouping_requires_both_evidence_floors_and_cross_scope(monkeypatch):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    matcher, _, _ = _live_matcher(monkeypatch, [])
    matcher._voice_centroids = {0: owner, 1: owner, 2: owner}
    matcher._voice_scopes = {0: 'socket:0', 1: 'socket:1', 2: 'socket:1'}
    matcher.speaker_evidence = {0: deque([(owner, 5.0)]), 1: deque([(owner, 4.99)]), 2: deque([(owner, 5.0)])}
    assert matcher._provider_epoch_voice_groups() == {0: 0, 1: 1, 2: 0}
    matcher.speaker_evidence[1] = deque([(owner, 5.0)])
    assert matcher._provider_epoch_voice_groups() == {0: 0, 1: 0, 2: 2}


def test_grouping_abstains_on_close_runner_up_and_transitive_bridge(monkeypatch):
    def vector(degrees):
        angle = np.deg2rad(degrees)
        return np.array([[np.cos(angle), np.sin(angle)]], dtype=np.float32)

    matcher, _, _ = _live_matcher(monkeypatch, [])
    # Provider proves these first two voices distinct. A new ambiguous midpoint
    # cannot choose the first acceptable one; neither can a transitive chain.
    matcher._voice_centroids = {0: vector(-30), 1: vector(30), 2: vector(0)}
    matcher._voice_scopes = {0: 'a', 1: 'a', 2: 'b'}
    matcher.speaker_evidence = {v: deque([(e, 5.0)]) for v, e in matcher._voice_centroids.items()}
    assert matcher._provider_epoch_voice_groups() == {0: 0, 1: 1, 2: 2}
    matcher._voice_centroids = {0: vector(0), 1: vector(45), 2: vector(90)}
    matcher._voice_scopes = {0: 'a', 1: 'b', 2: 'c'}
    assert matcher._provider_epoch_voice_groups() == {0: 0, 1: 0, 2: 2}


def test_short_display_evidence_is_unique_placed_time_and_does_not_spend_ordinals():
    rows = [dict(id=str(i), speaker_id=i, speaker_id_scope=f'socket:{i}', start=0, end=1) for i in range(5)]
    # Duplicate revisions and overlapping windows cannot qualify the first voice.
    rows += [dict(rows[0], id='revision', end=4.9), dict(rows[0], id='unplaced', start=-1, end=-1)]
    display = display_participants(rows, defer_short_voices=True, voice_order=[])
    assert {display.label(r) for r in rows} == {'Unknown speaker'}
    assert len({display.for_segment(r).key for r in rows[:5]}) == 5
    assert display.voice_order == ()
    rows += [dict(id='substantial', speaker_id=8, speaker_id_scope='s:8', start=0, end=5)]
    display = display_participants(rows, defer_short_voices=True, voice_order=[])
    assert display.label(rows[-1]) == 'Speaker A'
    assert len(display.voice_order) == 1
    assert not any(p.countable for p in display.participants)


@pytest.mark.asyncio
@pytest.mark.parametrize('enrolled_guest', [False, True])
async def test_idle_reopen_listen_reconnect_short_turns_and_owner_evidence(monkeypatch, enrolled_guest):
    owner = np.array([[1.0, 0.0]], dtype=np.float32)
    guest = np.array([[0.0, 1.0]], dtype=np.float32)
    matcher, host, _ = _live_matcher(monkeypatch, [owner] * 4 + [guest] * 2)
    if not enrolled_guest:
        matcher.person_embeddings.pop('p1')  # Unenrolled guest must never be forced to owner.
    names = {'p1': 'Sarah'} if enrolled_guest else {}
    socket, idle, _, peers, seen, tick = build(monkeypatch)
    allocator, epoch = ConversationSpeakerIdAllocator(), SpeakerProviderEpoch('listen-1')
    rows = []

    async def turn(provider_label=1):
        offset = len(rows) * 3.0
        idle._transport._handle_tokens(
            [
                dict(
                    text='fixture ',
                    speaker=str(provider_label),
                    is_final=True,
                    start_ms=offset * 1000,
                    end_ms=(offset + 2.5) * 1000,
                )
            ]
        )
        incoming = seen.pop()
        epoch.stamp([incoming], 'soniox')
        allocator.assign(incoming)
        incoming['id'] = f'turn-{len(rows)}'
        rows.append(TranscriptSegment(**incoming))
        voice = incoming['speaker_id']
        await matcher.match(
            voice, dict(_segment(incoming['id'], offset, 2.5), speaker_id_scope=incoming['speaker_id_scope'])
        )
        process_speaker_assigned_segments(rows, matcher.segment_assignments, matcher.speaker_to_person)
        processor = object.__new__(TranscriptProcessor)
        processor.host = host
        host.speakers = matcher
        processor._apply_speaker_identity_statuses(rows)
        return display_participants(rows, names=names, defer_short_voices=True)

    try:
        assert socket.send(b'\x01\x00' * 1600, wall_time=100, start_sample=0)
        assert (await turn()).label(rows[-1]) == 'Unknown speaker'
        assert (await turn()).label(rows[-1]) == 'You'
        socket.send(b'\x00\x00' * 1600, wall_time=100.1, start_sample=1600)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103.1, start_sample=49600)
        await idle._close_task
        tick[0] += 20
        assert socket.send(b'\x01\x00' * 1600, wall_time=123.1, start_sample=369600)
        assert await socket.complete_send()
        await settle()
        assert len(peers) == 2 and peers[0].closed
        assert (await turn()).label(rows[-1]) == 'Unknown speaker'
        assert (await turn()).label(rows[-1]) == 'You'
        assert rows[0].speaker_id != rows[2].speaker_id
        assert rows[0].speaker_id_scope != rows[2].speaker_id_scope
        groups = matcher._provider_epoch_voice_groups()
        assert groups[rows[0].speaker_id] == groups[rows[2].speaker_id]
        assert (await turn(2)).label(rows[-1]) == 'Unknown speaker'
        assert (await turn(2)).label(rows[-1]) == ('Sarah' if enrolled_guest else 'Speaker A')
        assert not rows[-1].is_user

        # A new listen replica hydrates identity reservations, not acoustic proof.
        allocator, epoch = ConversationSpeakerIdAllocator(), SpeakerProviderEpoch('listen-2')
        allocator.hydrate([r.model_dump() for r in rows])
        matcher, host, _ = _live_matcher(monkeypatch, [guest] * 2 + [owner] * 2)
        if not enrolled_guest:
            matcher.person_embeddings.pop('p1')
        # Reused provider label 1 now belongs to the guest. Reconnect must not
        # inherit the old owner's label or acoustic proof from that number.
        assert (await turn()).label(rows[-1]) == 'Unknown speaker'
        assert (await turn()).label(rows[-1]) == ('Sarah' if enrolled_guest else 'Speaker B')
        assert not any(r.is_user for r in rows[-2:])
        assert (await turn(2)).label(rows[-1]) == 'Unknown speaker'
        assert (await turn(2)).label(rows[-1]) == 'You'
        assert all(r.is_user for r in rows[:4] + rows[-2:])
        assert not any(r.is_user for r in rows[4:8])
    finally:
        await idle.drain_and_close()


def test_unnamed_display_never_joins_distinct_voice_turns(monkeypatch):
    monkeypatch.setattr(incremental, 'shadow_or_serve', lambda *_: False)
    rows = [dict(speaker_id=i, speaker_id_scope='s', text=f'turn{i}', start=i, end=i + 1) for i in (1, 2)]
    assert incremental.render_moment(rows).text == 'Unknown speaker: turn1\nUnknown speaker: turn2'


@pytest.mark.parametrize(
    'start,end,conversation_id,expected',
    [(6, 7, 'c', 'Speaker A'), (-1, -1, 'c', 'Speaker A'), (6, 7, 'other', 'Unknown speaker')],
)
def test_moment_ledger_retains_qualification_across_short_deltas(monkeypatch, start, end, conversation_id, expected):
    monkeypatch.setattr(incremental, 'shadow_or_serve', lambda *_: False)
    voice = dict(speaker_id=1, speaker_id_scope='listen:0')
    first = incremental.render_moment(
        [dict(voice, id='anchor', text='first turn', start=0, end=6)], conversation_id='c', voice_order=[]
    )
    assert first.text == 'Speaker A: first turn'
    assert len(first.voice_order) == 1
    # The episode caller supplies only its new delta plus the saved ledger.
    # A new epoch must qualify independently; a different conversation cannot
    # borrow qualification even when the raw provider identity happens to agree.
    next_moment = incremental.render_moment(
        [
            dict(voice, id='reply', text='short reply', start=start, end=end),
            dict(id='new-epoch', speaker_id=2, speaker_id_scope='listen:1', text='new voice', start=8, end=9),
        ],
        conversation_id=conversation_id,
        voice_order=first.voice_order,
    )
    assert next_moment.text == f'{expected}: short reply\nUnknown speaker: new voice'
    assert next_moment.voice_order == first.voice_order


@pytest.mark.parametrize('delta,linked', [(0.0, False), (-0.001, True)])
def test_epoch_distance_boundary_is_strict(delta, linked):
    groups = group_epoch_voices(
        {0: [[1.0, 0.0]], 1: [[1.0, 0.0]]},
        {0: 'a', 1: 'b'},
        {0: 5.0, 1: 5.0},
        distance=lambda *_: CROSS_EPOCH.distance + delta,
    )
    assert (groups[0] == groups[1]) is linked


def test_invalid_vectors_and_unscoped_voices_cannot_link():
    vectors = {0: [[1.0, 0.0]], 1: [[0.0, 0.0]], 2: [[float('nan'), 0.0]], 3: [[1.0, 0.0, 0.0]], 4: [[1.0, 0.0]]}
    groups = group_epoch_voices(
        vectors, {0: 'a', 1: 'b', 2: 'c', 3: 'd'}, {v: 5.0 for v in vectors}, distance=lambda *_: 0.0
    )
    assert groups == {v: v for v in vectors}

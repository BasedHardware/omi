"""Synthetic presentation policy: never discard, never hide an engaged owner."""

from datetime import datetime, timezone
from types import SimpleNamespace as Row

import pytest

from models.speaker_evidence import SpeakerCandidate, SpeakerEvidence, VoiceCluster
from models.structured import Structured
from utils.conversations.relevance_salience import finalize_salience, minimum_is_background, repetitive_clip
from utils.conversations import relevance_salience as contract


def segments(*, owner=False, turns=1, text='Synthetic broadcast. Synthetic broadcast.'):
    return [
        Row(id=f's{i}', text=text, start=i * 2.0, end=i * 2.0 + 1, is_user=owner and i % 2 == 0, speaker_id=i % 2)
        for i in range(turns)
    ]


def evidence(rows, *, owner=False, status='resolved', source='voice', band='confident'):
    return SpeakerEvidence(
        status=status,
        policy_version='synthetic',
        clusters=[
            VoiceCluster(
                id=f'v{i}',
                segment_ids=[s.id for s in rows if s.speaker_id == i],
                speech_seconds=2,
                candidates=[
                    SpeakerCandidate(
                        person_id='owner' if owner and i == 0 else 'other', probability=0.9, band=band, source=source
                    )
                ],
            )
            for i in sorted({s.speaker_id for s in rows})
        ],
    )


def conversation(rows, **extra):
    return Row(
        id='synthetic-conversation',
        transcript_segments=rows,
        discarded=False,
        started_at=datetime.now(timezone.utc),
        **extra,
    )


def minimum(**extra):
    return Structured(title='Synthetic minimum', overview='', title_provenance='server_minimum', **extra)


@pytest.mark.parametrize('topic', ['Laundry', 'Weekend spa', 'Errands', 'A meeting', 'Casual home chat'])
@pytest.mark.parametrize('identity', ['segments', 'voice', 'likely', 'partial', 'missing'])
def test_owner_multiturn_is_never_background(topic, identity):
    rows = segments(owner=identity == 'segments', turns=6)
    ev = (
        None
        if identity == 'missing'
        else evidence(
            rows,
            owner=identity != 'segments',
            band='likely' if identity == 'likely' else 'confident',
            status='partial' if identity == 'partial' else 'resolved',
        )
    )
    note = Structured(title=topic, salience='background')
    capture = conversation(rows)
    assert finalize_salience(note, capture, ev).salience == 'highlight'
    assert not capture.discarded


@pytest.mark.parametrize('case', ['missing', 'partial', 'unavailable', 'stale', 'negative_duration'])
def test_unknown_is_not_owner_absence(case):
    rows = segments()
    ev = evidence(rows)
    if case == 'missing':
        ev = None
    elif case == 'stale':
        ev.clusters[0].segment_ids = ['old']
    elif case == 'negative_duration':
        ev.clusters[0].speech_seconds = -1
    else:
        ev.status = case
    assert finalize_salience(Structured(salience='background'), conversation(rows), ev).salience == 'highlight'
    assert not minimum_is_background(conversation(rows), minimum(), ev)


def test_complete_absence_preserves_model_background():
    rows = segments()
    assert (
        finalize_salience(Structured(salience='background'), conversation(rows), evidence(rows)).salience
        == 'background'
    )


@pytest.mark.parametrize(
    'text', ['Synthetic broadcast. Synthetic broadcast.', '地域の人たちは皆ここに地域の人たちは皆ここに地']
)
def test_minimum_repetition_without_owner_leaves_home_but_is_kept(text):
    rows = segments(text=text)
    capture = conversation(rows)
    assert repetitive_clip(rows)
    note = finalize_salience(minimum(), capture, evidence(rows))
    assert note.salience == 'background'
    assert note.title_provenance == 'server_minimum'
    assert not capture.discarded


@pytest.mark.parametrize(
    'case',
    [
        'owner',
        'unknown_owner',
        'long',
        'ordinary',
        'reminder',
        'digit',
        'photo',
        'user_title',
        'notes',
        'no_provenance',
        'invalid_span',
        'roster_owner',
    ],
)
def test_minimum_requires_all_conservative_signals(case):
    rows = segments(owner=case == 'owner')
    ev = evidence(rows)
    capture = conversation(rows)
    note = minimum()
    if case == 'unknown_owner':
        ev = None
    elif case == 'long':
        rows[0].end = 21
    elif case == 'ordinary':
        rows[0].text = 'Take the red bag from the kitchen.'
    elif case == 'reminder':
        rows[0].text = 'Remind me to call mom. Remind me to call mom.'
    elif case == 'digit':
        rows[0].text = 'The code is 1234. The code is 1234.'
    elif case == 'photo':
        capture.photos = ['synthetic-photo']
    elif case == 'user_title':
        capture.user_title = 'My moment'
    elif case == 'notes':
        note.overview = 'Actual notes.'
    elif case == 'no_provenance':
        note.title_provenance = None
    elif case == 'invalid_span':
        rows[0].end = float('nan')
    elif case == 'roster_owner':
        # A roster owner hypothesis is not evidence of absence, either.
        ev = evidence(rows, owner=True, source='roster')
        ev.status = 'partial'
    assert not minimum_is_background(capture, note, ev)
    assert finalize_salience(note, capture, ev).salience is None


@pytest.mark.parametrize('kind', ['media', 'noise'])
def test_served_content_kind_uses_same_absence_requirement(kind):
    rows = segments(text='A synthetic media clip.')
    capture = conversation(rows, content_kind=kind)
    assert minimum_is_background(capture, minimum(), evidence(rows))
    assert not minimum_is_background(capture, minimum(), None)
    rows[0].is_user = True
    assert not minimum_is_background(capture, minimum(), evidence(rows))


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
def test_final_boundary_runs_for_minimum_and_cached_notes_without_rollout_dependency(monkeypatch, mode):
    monkeypatch.setenv('NOTES_PACKET_V2_MODE', mode)
    rows = segments(owner=True, turns=6)
    monkeypatch.setattr(contract, 'get_evidence', lambda *_: None)
    capture = conversation(rows)
    assert (
        contract.finish_home_salience('synthetic-account', Structured(salience='background'), capture).salience
        == 'highlight'
    )
    rows = segments()
    monkeypatch.setattr(contract, 'get_evidence', lambda *_: evidence(rows))
    assert contract.finish_home_salience('synthetic-account', minimum(), conversation(rows)).salience == 'background'


def test_normal_highlights_do_not_read_evidence(monkeypatch):
    def unexpected(*_):
        pytest.fail('ordinary highlights need no read')

    monkeypatch.setattr(contract, 'get_evidence', unexpected)
    note = Structured(salience='highlight')
    assert contract.finish_home_salience('synthetic-account', note, conversation(segments())) is note


def test_explicit_restore_keeps_minimum_on_home_without_evidence_read(monkeypatch):
    def unexpected(*_):
        pytest.fail('explicit keep needs no read')

    monkeypatch.setattr(contract, 'get_evidence', unexpected)
    assert (
        contract.finish_home_salience('synthetic-account', minimum(), conversation(segments()), user_kept=True).salience
        == 'highlight'
    )

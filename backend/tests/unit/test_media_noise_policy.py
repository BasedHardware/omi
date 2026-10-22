"""Synthetic evidence only: media, owner noise floor, bystanders and rollout isolation."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config.refactor_modes import uid_digest
from models.boundary_evidence import BoundarySignal
from models.speaker_evidence import SpeakerCandidate, SpeakerEvidence, VoiceCluster
from utils.capture.media import media_playback_signals
from utils.conversations import relevance_media as adapter
from utils.conversations.relevance_content import (
    FLAG,
    classify_content,
    exclude_from_derived,
    owner_speech_seconds,
)
from utils.conversations.relevance_rules import deterministic_relevance

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def segment(text='Synthetic sample words.', *, id='segment-a'):
    return dict(id=id, text=text, start=0, end=1)


def evidence(segments, *, owner=0, status='resolved', voices=1, band='confident', source='voice'):
    clusters = [
        VoiceCluster(
            id='v0',
            segment_ids=[segments[0]['id']],
            speech_seconds=max(owner, 1),
            candidates=[
                SpeakerCandidate(person_id='owner' if owner else 'other', probability=0.9, band=band, source=source)
            ],
        )
    ]
    if len(segments) > 1:
        clusters.append(VoiceCluster(id='v1', segment_ids=[s['id'] for s in segments[1:]], speech_seconds=30))
    assert voices == 1 or len(clusters) > 1
    return SpeakerEvidence(status=status, policy_version='synthetic', clusters=clusters)


def screens(seconds=120, **fields):
    return [
        dict(
            timestamp=(START + timedelta(seconds=n)).isoformat(),
            appName='Chrome',
            windowTitle='Synthetic tutorial - YouTube',
            **fields
        )
        for n in range(0, seconds, 30)
    ]


def classify(segments=None, *, seconds=120, owner=0, screen_rows=(), **kwargs):
    segments = segments or [segment()]
    ev = kwargs.pop('evidence', evidence(segments, owner=owner))
    return classify_content(
        segments,
        started_at=START,
        finished_at=START + timedelta(seconds=seconds),
        evidence=ev,
        screen_rows=screen_rows,
        **kwargs
    )


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for suffix in ('', '_SERVE_PERCENT', '_SERVE_UID_SHA256S'):
        monkeypatch.delenv(FLAG + suffix, raising=False)


@pytest.mark.parametrize(
    'app,title',
    [
        ('Chrome', 'Synthetic tutorial - YouTube'),
        ('Netflix', 'Synthetic episode'),
        ('VLC', 'Synthetic clip'),
        ('IINA', 'Synthetic clip'),
        ('QuickTime Player', 'Synthetic clip'),
        ('Podcasts', 'Synthetic episode'),
        ('Coursera', 'Synthetic lecture'),
        ('Spotify', 'Synthetic podcast'),
    ],
)
def test_foreground_media_produces_boundary_contract(app, title):
    rows = [dict(timestamp=START, appName=app, windowTitle=title)]
    signals = media_playback_signals(rows, started_at=START, finished_at=START + timedelta(seconds=30))
    assert signals and all(s.kind == 'media_playback' for s in signals)
    assert signals == media_playback_signals(rows, started_at=START, finished_at=START + timedelta(seconds=30))
    assert signals[0].external_id.startswith('media:')
    assert BoundarySignal.model_validate_json(signals[0].model_dump_json()) == signals[0]


@pytest.mark.parametrize('fields', [dict(isForeground=False), dict(isPlaying=False), dict(is_foreground=False)])
def test_background_and_paused_media_are_ignored(fields):
    assert classify(screen_rows=screens(**fields)).content_kind == 'noise'


@pytest.mark.parametrize('title', ['YouTube', 'Home', 'Search'])
def test_media_home_page_is_not_a_player(title):
    assert not media_playback_signals(
        [dict(timestamp=START, appName='YouTube', windowTitle=title)],
        started_at=START,
        finished_at=START + timedelta(seconds=30),
    )


def test_mentions_outside_foreground_title_do_not_count():
    rows = [dict(timestamp=START, appName='Notes', windowTitle='Reading list', ocrText='YouTube Netflix')]
    assert not media_playback_signals(rows, started_at=START, finished_at=START + timedelta(seconds=30))


def test_sparse_out_of_window_and_non_media_switch_do_not_fill_capture():
    assert classify(seconds=3600, screen_rows=screens(30)).content_kind != 'media'
    rows = screens(30) + [dict(timestamp=START + timedelta(seconds=1), appName='Editor')]
    assert classify(screen_rows=rows).content_kind != 'media'
    assert classify(screen_rows=[dict(timestamp=START - timedelta(hours=1), appName='VLC')]).content_kind != 'media'
    assert classify(screen_rows=[dict(timestamp='malformed', appName='VLC')]).content_kind != 'media'


def test_owner_speech_protects_media_and_silence_requires_current_evidence():
    assert classify(owner=20, screen_rows=screens()).content_kind == 'conversation'
    for ev in (None, evidence([segment()], status='partial'), evidence([segment(id='stale')])):
        result = classify(screen_rows=screens(), evidence=ev)
        assert result.content_kind == 'conversation' and result.owner_seconds is None


def test_media_title_and_noise_floor():
    result = classify(screen_rows=screens())
    assert result.content_kind == 'media' and result.title == 'Watched: Synthetic tutorial'
    result = classify()
    assert result.content_kind == 'noise' and result.reason == 'below_floor'
    assert result.title == 'Ambient audio'
    assert classify([segment(' '.join(['synthetic'] * 12))]).content_kind == 'conversation'


def test_duration_alone_is_not_noise_or_discard():
    segments = [segment(' '.join(['synthetic'] * 20))]
    assert classify(segments, seconds=1).content_kind == 'conversation'
    assert classify(segments, seconds=7200).content_kind == 'conversation'
    assert deterministic_relevance(['Call mom before five.'], 0.01) == deterministic_relevance(
        ['Call mom before five.'], 7200
    )


def test_bystander_requires_long_multiple_voices_and_no_owner_call():
    segments = [segment(' '.join(['synthetic'] * 20)), segment('Synthetic second voice.', id='segment-b')]
    ev = evidence(segments, voices=2)
    assert classify(segments, seconds=1200, evidence=ev).reason == 'bystander'
    assert classify(segments, seconds=60, evidence=ev).content_kind == 'conversation'
    for kind in ('phone_call', 'desktop_meeting', 'screen_meeting'):
        boundary = BoundarySignal(kind=kind, started_at=START, ended_at=START + timedelta(seconds=1200))
        assert classify(segments, seconds=1200, evidence=ev, boundaries=[boundary]).reason == 'owner_in_call'
    for kind in ('calendar_event', 'media_playback'):
        boundary = BoundarySignal(kind=kind, started_at=START, ended_at=START + timedelta(seconds=1200))
        assert classify(segments, seconds=1200, evidence=ev, boundaries=[boundary]).reason == 'bystander'


def test_expired_call_does_not_protect_bystander():
    boundary = BoundarySignal(kind='phone_call', started_at=START - timedelta(hours=1), ended_at=START)
    assert classify(boundaries=[boundary]).content_kind == 'noise'


@pytest.mark.parametrize(
    'band,source,expected',
    [('likely', 'voice', 10), ('confident', 'manual', 10), ('unknown', 'voice', 0), ('confident', 'roster', 0)],
)
def test_owner_candidates_use_producer_bands_not_probabilities(band, source, expected):
    segments = [segment()]
    ev = evidence(segments, owner=10, band=band, source=source)
    ev.clusters[0].candidates[0].probability = 0.01
    assert owner_speech_seconds(ev, segments) == expected


def test_nonfinite_or_uncovered_evidence_abstains():
    ev = evidence([segment()])
    ev.clusters[0].speech_seconds = float('nan')
    assert owner_speech_seconds(ev, [segment()]) is None
    assert owner_speech_seconds(evidence([segment()]), [segment(), segment(id='new')]) is None


def test_reminders_and_photo_curation_protect_content():
    assert classify([segment('Remind me to finish the synthetic task.')], screen_rows=screens()).reason == 'protected'
    assert classify(screen_rows=screens(), protected=True).reason == 'protected'


@pytest.mark.parametrize('consumer', ['daily_summary', 'memories', 'recap', 'action_items', 'notes'])
def test_every_consumer_gate_defaults_shadow_and_can_rollback(monkeypatch, consumer):
    row = {'content_kind': 'media'}
    assert not exclude_from_derived('', row, consumer=consumer)
    monkeypatch.setenv(FLAG, 'srve')
    assert not exclude_from_derived('', row, consumer=consumer)
    monkeypatch.setenv(FLAG, 'serve')
    assert exclude_from_derived('', row, consumer=consumer)
    assert exclude_from_derived('', SimpleNamespace(content_kind='noise'), consumer=consumer)
    assert not exclude_from_derived('', {'content_kind': None}, consumer=consumer)
    monkeypatch.setenv(FLAG, 'off')
    assert not exclude_from_derived('', row, consumer=consumer)


def test_consumer_digest_cohort(monkeypatch):
    monkeypatch.setenv(FLAG + '_SERVE_UID_SHA256S', uid_digest(''))
    # Empty identity is never admitted to a shadow cohort.
    assert not exclude_from_derived('', {'content_kind': 'noise'}, consumer='notes')
    monkeypatch.setenv(FLAG + '_SERVE_PERCENT', '100')
    assert exclude_from_derived('synthetic-account', {'content_kind': 'noise'}, consumer='notes')


def mock_inputs(monkeypatch):
    segments = [segment()]
    monkeypatch.setattr(adapter, '_speaker_evidence', lambda *_: evidence(segments))
    monkeypatch.setattr(adapter, '_screen_rows', lambda *_: screens())
    monkeypatch.setattr(adapter, '_boundaries', lambda *_: [])
    return SimpleNamespace(
        id='synthetic-capture',
        started_at=START,
        finished_at=START + timedelta(seconds=120),
        transcript_segments=segments,
        content_kind=None,
        discarded=False,
    )


def test_shadow_classifies_without_mutating_or_writing(monkeypatch):
    conversation = mock_inputs(monkeypatch)
    monkeypatch.setattr(adapter, '_record_boundaries', lambda *_: pytest.fail('shadow wrote boundaries'))
    assert adapter.minimum_for_processing('', conversation) is None
    assert conversation.content_kind is None and not conversation.discarded


def test_off_reads_nothing(monkeypatch):
    conversation = mock_inputs(monkeypatch)
    monkeypatch.setenv(FLAG, 'off')
    monkeypatch.setattr(adapter, '_speaker_evidence', lambda *_: pytest.fail('off read evidence'))
    assert adapter.minimum_for_processing('', conversation) is None


def test_shadow_reads_only_for_the_uid_sample(monkeypatch):
    conversation = mock_inputs(monkeypatch)
    monkeypatch.setenv(FLAG, 'shadow')
    monkeypatch.setenv(FLAG + '_SHADOW_PERCENT', '0')
    monkeypatch.setattr(adapter, '_speaker_evidence', lambda *_: pytest.fail('unsampled shadow read evidence'))
    assert adapter.minimum_for_processing('synthetic-owner', conversation) is None
    reads = []
    monkeypatch.setenv(FLAG + '_SHADOW_PERCENT', '100')
    monkeypatch.setattr(adapter, '_speaker_evidence', lambda *a: reads.append(a) or None)
    monkeypatch.setattr(adapter, '_record_boundaries', lambda *_: pytest.fail('shadow wrote boundaries'))
    assert adapter.minimum_for_processing('synthetic-owner', conversation) is None
    assert reads and conversation.content_kind is None


def test_serving_minimum_has_no_paid_notes_or_action_items(monkeypatch):
    conversation = mock_inputs(monkeypatch)
    monkeypatch.setenv(FLAG, 'serve')
    recorded = []
    monkeypatch.setattr(adapter, '_record_boundaries', lambda _, signals: recorded.extend(signals))
    minimum = adapter.minimum_for_processing('', conversation)
    assert conversation.content_kind == 'media' and not conversation.discarded
    assert minimum.title == 'Watched: Synthetic tutorial'
    assert minimum.title_provenance == 'server_minimum'
    assert minimum.overview == '' and minimum.emoji == '' and minimum.action_items == []
    assert recorded and recorded[0].kind == 'media_playback'


def test_curation_restores_consumer_eligibility(monkeypatch):
    conversation = mock_inputs(monkeypatch)
    monkeypatch.setenv(FLAG, 'serve')
    conversation.content_kind = 'noise'
    assert adapter.minimum_for_processing('', conversation, user_kept=True) is None
    assert conversation.content_kind == 'conversation'


def test_failed_inputs_abstain_without_logging_payload(monkeypatch, caplog):
    conversation = mock_inputs(monkeypatch)

    def fail(*_):
        raise RuntimeError('sensitive synthetic payload')

    monkeypatch.setattr(adapter, '_speaker_evidence', fail)
    assert adapter.minimum_for_processing('', conversation) is None
    assert conversation.content_kind is None
    assert 'sensitive synthetic payload' not in caplog.text


def test_home_hiding_requires_serve_and_existing_client_capability(monkeypatch):
    from utils.conversations.relevance_content import noise_hidden_from_home

    row = {'content_kind': 'noise'}
    assert not noise_hidden_from_home('', row, client_supports_discarded=True)
    monkeypatch.setenv(FLAG, 'serve')
    assert not noise_hidden_from_home('', row)
    assert noise_hidden_from_home('', row, client_supports_discarded=True)
    assert not noise_hidden_from_home('', row, client_supports_discarded=True, user_kept=True)
    assert not noise_hidden_from_home('', {'content_kind': 'media'}, client_supports_discarded=True)
    monkeypatch.setenv(FLAG, 'off')
    assert not noise_hidden_from_home('', row, client_supports_discarded=True)


def test_restore_and_stale_evidence_cannot_leave_old_exclusion(monkeypatch):
    conversation = mock_inputs(monkeypatch)
    conversation.content_kind = 'noise'
    monkeypatch.setenv(FLAG, 'serve')
    monkeypatch.setattr(adapter, '_speaker_evidence', lambda *_: None)
    assert adapter.minimum_for_processing('', conversation, user_kept=True) is None
    assert conversation.content_kind == 'conversation'
    conversation.content_kind = 'media'
    assert adapter.minimum_for_processing('', conversation) is None
    assert conversation.content_kind is None


@pytest.mark.parametrize('kind', ['conversation', 'media', 'noise'])
def test_client_cannot_author_content_classification(kind):
    from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation, Structured

    create = CreateConversation(
        started_at=START, finished_at=START + timedelta(seconds=30), transcript_segments=[], content_kind=kind
    )
    external = ExternalIntegrationCreateConversation(text='Synthetic import.', content_kind=kind)
    assert create.content_kind is None and external.content_kind is None
    assert 'content_kind' not in CreateConversation.model_json_schema()['properties']
    assert 'content_kind' not in ExternalIntegrationCreateConversation.model_json_schema()['properties']
    assert 'content_kind' in Conversation.model_json_schema()['properties']
    # The server may assign its evidence decision after request validation.
    create.content_kind = kind
    stored = Conversation(id='synthetic-capture', created_at=START, structured=Structured(), **create.model_dump())
    assert stored.content_kind == kind


def test_adjacent_media_frames_share_one_boundary_ledger_entry():
    signals = media_playback_signals(screens(600), started_at=START, finished_at=START + timedelta(seconds=600))
    assert len(signals) == 1
    assert signals[0].started_at == START and signals[0].ended_at == START + timedelta(seconds=600)


def test_media_observations_do_not_merge_across_unobserved_gap():
    rows = screens(30) + [dict(screens(30)[0], timestamp=(START + timedelta(seconds=80)).isoformat())]
    signals = media_playback_signals(rows, started_at=START, finished_at=START + timedelta(seconds=120))
    assert len(signals) == 2
    assert signals[0].ended_at == START + timedelta(seconds=60)
    assert signals[1].started_at == START + timedelta(seconds=80)


def test_media_metrics_reject_unknown_check_and_keep_conversation_bucket():
    from utils.conversations.relevance_media_metrics import observe, SHADOW

    before = SHADOW.labels(check='conversation', outcome='agree')._value.get()
    observe('conversation', 'agree')
    assert SHADOW.labels(check='conversation', outcome='agree')._value.get() == before + 1
    with pytest.raises(ValueError, match='unknown media/noise check'):
        observe('invalid-consumer', 'agree')

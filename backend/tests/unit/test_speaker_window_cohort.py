"""Per-window speaker evidence follows the batch ramp and the beta client marker."""

from types import SimpleNamespace

import pytest

from utils.conversations import speaker_window_cohort as cohort

BATCH = [SimpleNamespace(speaker_id_scope='final:batch:unit-1', provider_speaker=None)]
RESOLVED_BATCH = [SimpleNamespace(speaker_id_scope='conversation:c1', provider_speaker={'scope': 'final:batch:unit-1'})]
SYNC = [SimpleNamespace(speaker_id_scope='sync:file-1', provider_speaker=None)]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        'SPEAKER_EVIDENCE_MODE',
        'SPEAKER_EVIDENCE_MODE_SERVE_PERCENT',
        'SPEAKER_EVIDENCE_MODE_SERVE_UID_SHA256S',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(cohort.SPEAKER_PER_WINDOW_ENV, raising=False)
    monkeypatch.delenv('EPISODES_CLIENT_CHANNELS', raising=False)
    monkeypatch.setattr(cohort, 'client_seen_cached', lambda uid: False)


@pytest.mark.parametrize('segments', [BATCH, RESOLVED_BATCH])
def test_batch_authority_qualifies_without_any_cohort(segments):
    assert cohort.per_window_evidence('u1', segments)


def test_store_user_outside_batch_stays_on_the_old_path():
    assert not cohort.per_window_evidence('u1', SYNC)


def test_beta_client_marker_qualifies(monkeypatch):
    monkeypatch.setattr(cohort, 'client_seen_cached', lambda uid: True)
    assert cohort.per_window_evidence('u1', SYNC)


def test_marker_stops_meaning_testflight_once_store_clients_are_admitted(monkeypatch):
    monkeypatch.setattr(cohort, 'client_seen_cached', lambda uid: True)
    monkeypatch.setenv('EPISODES_CLIENT_CHANNELS', 'beta,store')
    assert not cohort.per_window_evidence('u1', SYNC)
    assert cohort.per_window_evidence('u1', BATCH)


def test_kill_switch_stops_batch_and_beta(monkeypatch):
    monkeypatch.setattr(cohort, 'client_seen_cached', lambda uid: True)
    monkeypatch.setenv(cohort.SPEAKER_PER_WINDOW_ENV, 'false')
    assert not cohort.per_window_evidence('u1', BATCH)
    assert not cohort.per_window_evidence('u1', SYNC)


def test_evidence_serve_cohort_is_unchanged_by_the_kill_switch(monkeypatch):
    monkeypatch.setenv('SPEAKER_EVIDENCE_MODE', 'serve')
    monkeypatch.setenv(cohort.SPEAKER_PER_WINDOW_ENV, 'false')
    assert cohort.per_window_evidence('u1', SYNC)

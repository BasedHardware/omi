"""Deployed day3-reengagement-email entrypoint lifecycle behavior.

Mirrors test_daily_memory_sweep_job.py: the job module is loaded from its
literal path (``modal/`` is not an importable package on the normal path),
then every name it imported by reference is monkeypatched directly on the
loaded module object.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from utils.email.day3_reengagement import Day3Authority, RunSummary


@pytest.fixture
def day3_job(monkeypatch):
    monkeypatch.setenv(
        'ENCRYPTION_SECRET',
        '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcd',
    )
    entry_path = Path(__file__).resolve().parents[2] / 'modal' / 'day3_reengagement_email_job.py'
    spec = importlib.util.spec_from_file_location('_day3_reengagement_email_job_behavior_test', entry_path)
    assert spec is not None and spec.loader is not None
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    return job


@pytest.mark.parametrize(
    'authority',
    [
        Day3Authority(enabled=False),
        Day3Authority(enabled=True, kill_switch_active=True),
        None,
    ],
    ids=['disabled', 'kill-switch', 'unavailable'],
)
def test_closed_authority_exits_before_candidate_selection_or_send(monkeypatch, day3_job, authority):
    job = day3_job
    selection_calls: list[bool] = []
    run_calls: list[bool] = []

    monkeypatch.setattr(job, 'authority_from_environment', lambda: authority)
    monkeypatch.setattr(job, 'collect_day3_candidates', lambda *_a, **_k: selection_calls.append(True))
    monkeypatch.setattr(job, 'run_day3_reengagement', lambda *_a, **_k: run_calls.append(True))

    job.run_day3_reengagement_email_job()

    assert selection_calls == []
    assert run_calls == []


def test_truthy_malformed_authority_fails_closed(monkeypatch, day3_job):
    job = day3_job
    selection_calls: list[bool] = []

    class MalformedAuthority:
        may_send = 'false'  # truthy string, not the bool True the job requires

    monkeypatch.setattr(job, 'authority_from_environment', lambda: MalformedAuthority())
    monkeypatch.setattr(job, 'collect_day3_candidates', lambda *_a, **_k: selection_calls.append(True))

    job.run_day3_reengagement_email_job()

    assert selection_calls == []


def test_authority_property_failure_exits_before_candidate_selection(monkeypatch, day3_job):
    job = day3_job
    selection_calls: list[bool] = []

    class UnreadableAuthority:
        @property
        def may_send(self):
            raise RuntimeError('authority unreadable')

    monkeypatch.setattr(job, 'authority_from_environment', lambda: UnreadableAuthority())
    monkeypatch.setattr(job, 'collect_day3_candidates', lambda *_a, **_k: selection_calls.append(True))

    job.run_day3_reengagement_email_job()

    assert selection_calls == []


def test_authority_resolution_failure_exits_before_candidate_selection(monkeypatch, day3_job):
    job = day3_job
    selection_calls: list[bool] = []

    def unavailable_authority():
        raise RuntimeError('authority unavailable')

    monkeypatch.setattr(job, 'authority_from_environment', unavailable_authority)
    monkeypatch.setattr(job, 'collect_day3_candidates', lambda *_a, **_k: selection_calls.append(True))

    job.run_day3_reengagement_email_job()

    assert selection_calls == []


def test_open_authority_selects_candidates_and_runs(monkeypatch, day3_job):
    job = day3_job
    candidates = ['candidate-sentinel']
    summary = RunSummary(considered=1, sent=1)
    observed = {}

    def fake_collect(**kwargs):
        observed['collect'] = kwargs
        return candidates

    monkeypatch.setattr(job, 'authority_from_environment', lambda: Day3Authority(enabled=True))
    monkeypatch.setattr(job, 'collect_day3_candidates', fake_collect)

    def fake_run(**kwargs):
        observed['run'] = kwargs
        return summary

    monkeypatch.setattr(job, 'run_day3_reengagement', fake_run)

    job.run_day3_reengagement_email_job()

    assert observed['run']['candidates'] == candidates
    assert observed['run']['authority'].enabled is True
    assert observed['collect']['firestore_client'] is job.default_db_client
    assert observed['run']['firestore_client'] is job.default_db_client


def test_job_raises_when_the_summary_has_failures(monkeypatch, day3_job):
    job = day3_job
    monkeypatch.setattr(job, 'authority_from_environment', lambda: Day3Authority(enabled=True))
    monkeypatch.setattr(job, 'collect_day3_candidates', lambda **_k: [])
    monkeypatch.setattr(job, 'run_day3_reengagement', lambda **_k: RunSummary(considered=1, failed=1))

    with pytest.raises(RuntimeError):
        job.run_day3_reengagement_email_job()


def test_job_does_not_raise_when_the_summary_is_clean(monkeypatch, day3_job):
    job = day3_job
    monkeypatch.setattr(job, 'authority_from_environment', lambda: Day3Authority(enabled=True))
    monkeypatch.setattr(job, 'collect_day3_candidates', lambda **_k: [])
    monkeypatch.setattr(job, 'run_day3_reengagement', lambda **_k: RunSummary(considered=1, sent=1))

    job.run_day3_reengagement_email_job()  # must not raise


def test_display_name_for_reads_through_get_user_from_uid(monkeypatch, day3_job):
    job = day3_job
    monkeypatch.setattr(
        job, 'get_user_from_uid', lambda uid: {'display_name': f'name-{uid}'} if uid == 'uid-a' else None
    )

    assert job._display_name_for('uid-a') == 'name-uid-a'
    assert job._display_name_for('uid-missing') is None

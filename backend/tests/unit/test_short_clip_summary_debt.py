"""Intentional floors owe no generated summary; empty provider output still does."""

import importlib
from copy import deepcopy

import pytest

from utils.conversations import summary_delivery as delivery


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    importlib.import_module('database.conversations')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')


def minimum(*, intentional=False):
    row = dict(
        status='completed',
        discarded=False,
        structured=dict(title='Recording', title_provenance='server_minimum', overview='', sections=[]),
    )
    if intentional:
        row['relevance_decision'] = dict(verdict='keep', decided_by='rule', reason='content_below_floor')
    delivery.prepare(row, 'synthetic-account', now=100)
    return row


def test_intentional_floor_creation_is_terminal_for_summary_debt_only():
    write = minimum(intentional=True)
    assert delivery.creation_result(write, 'synthetic-account') is None
    assert write['summary_due_at'] is None and write['summary_processing_lease_until'] == 0
    assert write['summary_blocked_reason'] == 'content_below_floor'
    assert not write.get('terminal_no_derived_effects')
    assert not write.get('summary_completed_at')  # Never claim a generated summary exists.
    assert delivery.refusal(write) == 'content_below_floor'
    assert not delivery.finalization_pending({**write, 'finalization_job_id': 'job'}, 'synthetic-account', 'job')


def test_intentional_floor_retires_existing_debt_and_finishes_the_outbox_context():
    existing = minimum()
    assert existing['summary_due_at'] == 220
    write, context = minimum(intentional=True), {'owner': 'worker'}
    token = delivery.PROCESS_CONTEXT.set(context)
    try:
        assert delivery.merge_result(existing, write, 'synthetic-account', now=150) is None
        assert write['summary_due_at'] is None and context['blocked_reason'] == 'content_below_floor'
        assert write['summary_processing_lease_until'] == 0
        assert not write.get('terminal_no_derived_effects')
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


@pytest.mark.parametrize('change', [None, {'reason': 'model_error'}, {'decided_by': 'model'}, {'verdict': 'discard'}])
def test_provider_minimum_without_the_server_floor_decision_keeps_its_obligation(change):
    existing, write = minimum(), minimum(intentional=True)
    if change is None:
        write.pop('relevance_decision')
    else:
        write['relevance_decision'].update(change)
    with pytest.raises(delivery.SummaryOutputUnavailable):
        delivery.merge_result(existing, write, 'synthetic-account', now=150)


def test_floor_does_not_overwrite_a_banked_summary():
    existing = minimum()
    existing.update(
        summary_completed_at=110,
        summary_due_at=None,
        summary_output_present=True,
        structured=dict(title='Earlier notes', overview='Banked source summary', sections=[]),
    )
    write = minimum(intentional=True)
    delivery.merge_result(existing, write, 'synthetic-account', now=150)
    assert write['structured']['overview'] == 'Banked source summary'
    assert write['summary_output_present'] is True and write['summary_completed_at'] == 110


def test_later_enrichment_closes_the_waived_minimum_normally():
    existing = minimum(intentional=True)
    delivery.creation_result(existing, 'synthetic-account')
    write = dict(
        status='completed',
        structured=dict(title='Real notes', overview='A real follow-up summary'),
        summary_output_present=True,
    )
    receipt = delivery.merge_result(deepcopy(existing), write, 'synthetic-account', now=200)
    assert receipt['present'] is True
    assert write['summary_completed_at'] == 200 and write['summary_blocked_reason'] is None


def test_real_summary_content_is_receipted_even_with_stale_floor_metadata():
    write = minimum(intentional=True)
    write['structured']['overview'] = 'A real user-authored overview'
    delivery.prepare(write, 'synthetic-account', now=150)
    receipt = delivery.merge_result(minimum(), write, 'synthetic-account', now=200)
    assert receipt['present'] is True and write['summary_completed_at'] == 200

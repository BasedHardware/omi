"""Summary success is a fenced durable outcome, never upload/model success."""

import importlib
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from config import summary_guarantee as flags
from utils.conversations import summary_delivery as delivery
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured


@pytest.fixture(scope='module', autouse=True)
def summary_database_dependency():
    # The banked-summary branch lazily imports effective_user_title. Load the
    # real dependency in setup so the call CPU guard measures merge logic,
    # while import failures still fail this suite and all assertions stay real.
    importlib.import_module('database.conversations')


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)


def minimum():
    return dict(
        status='completed',
        summary_output_present=False,
        structured={'title': 'Server title', 'title_provenance': 'server_minimum', 'overview': '', 'sections': []},
    )


def debt():
    row = minimum()
    delivery.prepare(row, 'u', now=100)
    return row


def test_dark_defaults_and_no_shape_change(monkeypatch):
    monkeypatch.delenv('FIRST_SUMMARY_DEADLINE_ENABLED', raising=False)
    row = minimum()
    before = deepcopy(row)
    delivery.prepare(row, 'u', now=100)
    assert row == before
    assert not flags.enabled('u') and not flags.repair_enabled()
    result = build_deterministic_minimum_structured(SimpleNamespace(transcript_segments=[]), uid='u')
    assert 'title_provenance' not in result.model_dump()


def test_server_title_provenance_is_stamped_only_for_cohort_owners(monkeypatch):
    """PFS-F1: the gate being on somewhere must not stamp every owner's minimum."""
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)
    row = SimpleNamespace(transcript_segments=[])
    assert flags.enabled() and not flags.enabled('outside-owner')
    assert 'title_provenance' not in build_deterministic_minimum_structured(row, uid='outside-owner').model_dump()
    assert 'title_provenance' not in build_deterministic_minimum_structured(row, uid=None).model_dump()
    assert 'title_provenance' not in build_deterministic_minimum_structured(row).model_dump()

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    assert build_deterministic_minimum_structured(row, uid='outside-owner').model_dump()['title_provenance'] == (
        'server_minimum'
    )


def test_server_title_provenance_is_not_a_model_or_manual_title(enabled):
    result = build_deterministic_minimum_structured(SimpleNamespace(transcript_segments=[]), uid='u')
    assert result.model_dump()['title_provenance'] == 'server_minimum'
    assert 'title_provenance' not in result.model_json_schema()['properties']
    assert delivery.refusal(debt()) is None
    for field, value in [
        ('user_title', 'Edited'),
        ('user_overview', ''),
        ('discarded', True),
        ('deleted', True),
        ('is_locked', True),
        ('deferred', True),
        ('processing_state', 'local_pending'),
        ('data_protection_level', 'e2ee'),
        ('finalization_job_id', 'owned'),
        ('finalization_status', 'blocked_byok'),
    ]:
        assert delivery.refusal({**debt(), field: value}) is not None
    assert delivery.refusal({**debt(), 'summary_title_provenance': 'unknown'}) == 'unknown_provenance'


def test_deadline_metadata_survives_appends(enabled):
    row = debt()
    delivery.prepare(row, 'u', now=10000)
    assert row['summary_first_pending_at'] == 100
    assert row['summary_due_at'] == 220


def test_current_finalizer_finishes_completed_minimum_but_background_repair_cannot(enabled, monkeypatch):
    row = {**debt(), 'finalization_job_id': 'current-job', 'finalization_status': 'queued'}
    assert delivery.refusal(row) == 'generation_owned'
    assert delivery.finalization_pending(row, 'u', 'current-job')
    for changes in (
        {'structured': {'overview': 'Already delivered'}},
        {'user_title': 'Manual title'},
        {'deleted': True},
        {'discarded': True},
        {'terminal_no_derived_effects': True},
        {'data_protection_level': 'e2ee'},
        {'summary_title_provenance': None},
        {'summary_blocked_reason': 'empty_output_exhausted'},
        {'finalization_status': 'blocked_byok'},
        {'finalization_job_id': 'replacement-job'},
        {'finalization_job_id': None},
    ):
        assert not delivery.finalization_pending({**row, **changes}, 'u', 'current-job')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
    assert not delivery.finalization_pending(row, 'u', 'current-job')


@pytest.mark.parametrize('finish,expected', [(50, 1900), (1800, 200), (2100, None), (None, None)])
def test_post_speech_latency_excludes_time_before_acceptance_and_open_speech(enabled, finish, expected):
    row = debt()
    if finish is not None:
        row['finished_at'] = datetime.fromtimestamp(finish, timezone.utc)
    receipt = delivery.merge_result(row, {'status': 'completed', 'summary_output_present': True}, 'u', now=2000)
    assert receipt['latency'] == 1900
    assert receipt['closed_latency'] == expected


def test_intake_discard_never_indexes_debt_and_keep_gets_a_new_deadline(enabled):
    row = {**minimum(), 'discarded': True}
    delivery.prepare(row, 'u', now=100)
    assert row['summary_due_at'] is None
    assert row['summary_discard_receipted']
    assert 'summary_first_pending_at' not in row
    delivery.prepare(row, 'u', now=200)
    assert row['summary_due_at'] is None
    row['discarded'] = False
    delivery.prepare(row, 'u', now=300)
    assert row['summary_due_at'] == 420 and row['summary_first_pending_at'] == 300


def test_existing_due_discard_and_exhausted_empty_output_leave_the_index(enabled):
    row = {**debt(), 'discarded': True}
    delivery.prepare(row, 'u', now=1000)
    assert row['summary_due_at'] is None
    blocked = {**debt(), 'summary_blocked_reason': 'empty_output_exhausted'}
    delivery.prepare(blocked, 'u', now=1000)
    assert blocked['summary_due_at'] is None
    assert delivery.refusal(blocked) == 'empty_output_exhausted'


def test_only_owner_replacement_fences_a_live_result_after_expiry():
    token = delivery.PROCESS_CONTEXT.set({'owner': 'same', 'claimed': True, 'lease_until': 1})
    try:
        assert not delivery.processing_fenced({'summary_processing_owner': 'same', 'summary_processing_lease_until': 1})
        assert delivery.processing_fenced({'summary_processing_owner': 'replacement'})
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


def test_actions_events_title_and_empty_sections_do_not_satisfy_summary():
    for structured in (
        {'title': 't'},
        {'overview': '  ', 'action_items': [1]},
        {'events': [1]},
        {'sections': [{'title': 'Heading', 'body_markdown': ' '}]},
    ):
        assert not delivery.present(structured)
    assert delivery.present({'sections': [{'body_markdown': 'A supported note.'}]})
    assert delivery.present({'overview': 'A supported overview.'})


def test_empty_model_output_retains_debt_and_prior_good_output(enabled):
    row = debt()
    with pytest.raises(delivery.SummaryOutputUnavailable):
        delivery.merge_result(row, minimum(), 'u', now=300)
    assert row['summary_due_at'] == 220
    # A failed model attempt never gets to overwrite a prior usable summary:
    # the enriched row now commits (no lane stranding without an outbox), but
    # the banked content and receipts are re-applied onto the write instead
    # of letting the empty structured payload clobber them.
    old = {
        **row,
        'structured': {'title': 'Kept', 'overview': 'Banked summary'},
        'summary_completed_at': 150,
        'summary_due_at': None,
        'summary_output_present': True,
    }
    empty_write = minimum()
    assert delivery.merge_result(old, empty_write, 'u', now=300) is None
    banked_structured = empty_write['structured']
    assert isinstance(banked_structured, dict)
    assert banked_structured['overview'] == 'Banked summary'
    assert empty_write['summary_output_present'] is True
    assert empty_write['summary_completed_at'] == 150
    assert empty_write['summary_due_at'] is None


def test_lost_ack_does_not_emit_second_terminal_receipt(enabled):
    row = debt()
    write = {'status': 'completed', 'summary_output_present': True}
    receipt = delivery.merge_result(row, write, 'u', now=150)
    assert receipt['present'] and receipt['latency'] == 50
    assert write['summary_due_at'] is None and write['summary_completed_at'] == 150
    assert delivery.merge_result({**row, **write}, dict(write), 'u', now=200) is None


def test_generation_fence_and_manual_edit_after_admission(enabled):
    row = {**debt(), 'sync_content_revision': 2}
    token = delivery.REPAIR_CONTEXT.set({'summary_expected_revision': 2})
    try:
        assert not delivery.repair_fenced(row)
        assert delivery.repair_fenced({**row, 'sync_content_revision': 3})
        assert delivery.repair_fenced({**row, 'user_title': 'Manual'})
        assert delivery.repair_fenced({**row, 'finalization_job_id': 'new-generation'})
    finally:
        delivery.REPAIR_CONTEXT.reset(token)


def test_allowlist_and_invalid_deadline_fail_closed(enabled, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    assert not flags.enabled('canary') and not flags.enabled('other')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'canary')
    assert flags.enabled('canary') and not flags.enabled('other')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', 'invalid')
    assert flags.deadline_seconds() == 120
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_SECONDS', '999')
    assert flags.deadline_seconds() == 120


def test_local_only_minimum_is_explicitly_blocked_not_retried_as_empty(enabled):
    write = {**minimum(), 'terminal_no_derived_effects': True}
    context = {'owner': 'worker', 'lease_until': 999}
    token = delivery.PROCESS_CONTEXT.set(context)
    try:
        receipt = delivery.merge_result(debt(), write, 'u', now=150)
        assert receipt['reason'] == 'local_only' and not receipt['present']
        assert write['summary_due_at'] is None and context['blocked_reason'] == 'local_only'
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


def test_discard_receipt_does_not_hide_a_later_first_summary(enabled):
    row = debt()
    write = {'status': 'completed', 'discarded': True, 'summary_output_present': False}
    receipt = delivery.merge_result(row, write, 'u', now=150)
    assert not receipt['present'] and 'summary_completed_at' not in write
    assert write['summary_discard_receipted']
    assert delivery.merge_result({**row, **write}, dict(write), 'u', now=151) is None
    restored = {**row, **write, 'discarded': False}
    delivery.prepare(restored, 'u', now=200)
    assert restored['summary_due_at'] == 320 and restored['summary_first_pending_at'] == 200
    output = {'status': 'completed', 'summary_output_present': True}
    receipt = delivery.merge_result(restored, output, 'u', now=250)
    assert receipt['present'] and receipt['latency'] == 50

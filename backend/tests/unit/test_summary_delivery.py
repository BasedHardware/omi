"""Summary success is a fenced durable outcome, never upload/model success."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from config import summary_guarantee as flags
from utils.conversations import summary_delivery as delivery
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
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
    result = build_deterministic_minimum_structured(SimpleNamespace(transcript_segments=[]))
    assert 'title_provenance' not in result.model_dump()


def test_server_title_provenance_is_not_a_model_or_manual_title(enabled):
    result = build_deterministic_minimum_structured(SimpleNamespace(transcript_segments=[]))
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
    # A failed model attempt never gets to overwrite a prior usable summary.
    old = {**row, 'summary_completed_at': 150, 'summary_due_at': None, 'summary_output_present': True}
    with pytest.raises(delivery.SummaryOutputUnavailable):
        delivery.merge_result(old, minimum(), 'u', now=300)


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

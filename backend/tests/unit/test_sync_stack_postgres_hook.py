"""The hermetic sync stack starts Postgres only when OMI_STACK_POSTGRES asks for it."""

import json

import httpx
import pytest

from testing.sync_cloud_tasks_stack import run


@pytest.mark.parametrize(
    'value,expected',
    [(None, False), ('', False), ('0', False), ('no', False), ('1', True), ('TRUE', True), (' on ', True)],
)
def test_postgres_is_opt_in(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('OMI_STACK_POSTGRES', raising=False)
    else:
        monkeypatch.setenv('OMI_STACK_POSTGRES', value)
    assert run.postgres_requested() is expected


def test_stt_gate_diagnostics_reports_stages_without_fixture_content(tmp_path):
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    (evidence / 'providers.jsonl').write_text(
        json.dumps({'event': 'stt_completed', 'uid': 'PRIVATE-UID', 'text': 'PRIVATE-TEXT'}) + '\n'
    )
    delivery = httpx.Response(503, json={'status': 'failed', 'detail': 'PRIVATE-ERROR'})
    summary = run._stt_gate_diagnostics(tmp_path, [delivery])
    assert 'first_delivery_http=503 first_delivery_status=failed' in summary
    assert 'stt_completed=1' in summary and 'stt_gate_entered=0' in summary
    assert 'PRIVATE' not in summary and str(tmp_path) not in summary


def test_stt_gate_diagnostics_bounds_unknown_responses_and_pending_delivery(tmp_path):
    pending = run._stt_gate_diagnostics(tmp_path, [])
    assert 'first_delivery_http=pending' in pending and 'first_delivery_status=unknown' in pending
    private = httpx.Response(500, json={'status': 'PRIVATE-RESPONSE'})
    assert 'PRIVATE' not in run._stt_gate_diagnostics(tmp_path, [private])

import logging

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest

from utils.observability.stt_cap_dispatch import RECONCILIATION, record_reconciliation


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize(
    'outcome', ['cleared_noncall', 'reconciled_ingested', 'redispatched', 'failed', 'settled_empty']
)
def test_reconciliation_counter_and_log_are_additive_bounded_and_identifiable(monkeypatch, caplog, enabled, outcome):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enabled))
    metric = RECONCILIATION.labels(outcome=outcome)
    before = metric._value.get()
    with caplog.at_level(logging.INFO):
        record_reconciliation(outcome, 'synthetic-hold', '1792152000.wav')
    assert metric._value.get() == before + int(enabled)
    if enabled:
        assert f'outcome={outcome}' in caplog.text
        assert 'hold_id=synthetic-hold' in caplog.text and '1792152000.wav' in caplog.text
    else:
        assert not caplog.text
    for family in RECONCILIATION.collect():
        assert all(set(sample.labels) == {'outcome'} for sample in family.samples)

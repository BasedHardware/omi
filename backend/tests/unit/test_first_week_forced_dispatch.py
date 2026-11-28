"""Regression coverage for forced-close dispatch and its scoped consent grant."""

from types import SimpleNamespace


def test_forced_close_delivery_passes_its_explicit_budget_consent(monkeypatch):
    from config.summary_guarantee import FIRST_WEEK_FORCED_CLOSE_ENV, FIRST_WEEK_FORCED_POLICY_FIELD
    from utils import funded_processing
    from utils.enrichment.consumer import EnrichmentConsumer

    monkeypatch.setenv(FIRST_WEEK_FORCED_CLOSE_ENV, 'true')
    monkeypatch.setattr(funded_processing, 'enabled', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(funded_processing, 'period_id', lambda: 'current-period')
    calls = []

    def callback(uid, conversation_id, language, *, first_week_forced=False):
        calls.append((uid, conversation_id, language, first_week_forced, funded_processing.consent_allows(uid)))
        return SimpleNamespace(structured={'title': 'First summary', 'overview': 'Summary body'})

    claim = SimpleNamespace(
        payload={
            'conversation_id': 'conversation',
            'language': 'en',
            'first_pending_at': 1,
            FIRST_WEEK_FORCED_POLICY_FIELD: 'first_week_forced_close.v1',
        },
        owner_id='payer',
        row_id='outbox-row',
        lease_token='lease',
        lease_until=0,
        wake_token='wake',
    )
    consumer_outbox = SimpleNamespace(record_summary=lambda _claim: True)
    result = EnrichmentConsumer(outbox=consumer_outbox, process=callback)._deliver(claim, lambda: True)

    assert result.outcome.value == 'done'
    assert calls == [('payer', 'conversation', 'en', True, True)]

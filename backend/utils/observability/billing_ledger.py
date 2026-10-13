"""Closed, zero-initialized billing delivery counters. No account/event labels."""

from prometheus_client import Counter

OUTCOMES = (
    'claimed',
    'duplicate',
    'busy',
    'acknowledged',
    'out_of_order',
    'claim_error',
    'finish_error',
    'handler_error',
    'unprotected',
    'observe_error',
)
LEDGER = Counter('omi_billing_webhook_ledger_total', 'Durable billing delivery ledger outcomes.', ['outcome'])
for outcome in OUTCOMES:
    LEDGER.labels(outcome=outcome)


def record_outcome(outcome: str) -> None:
    if outcome not in OUTCOMES:
        raise ValueError('unknown billing ledger outcome')
    LEDGER.labels(outcome=outcome).inc()

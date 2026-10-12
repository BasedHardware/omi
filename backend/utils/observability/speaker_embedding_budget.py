"""Closed-label live query admission and extraction counters (never user IDs)."""

from prometheus_client import REGISTRY, Counter


def _counter(name: str, description: str, label: str) -> Counter:
    try:
        return Counter(name, description, [label])
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]


BUDGET_EXITS = _counter(
    'omi_speaker_id_budget_exits_total', 'Blocked live query detections by exclusive admission cap', 'cap'
)
BUDGET_VOICES = _counter(
    'omi_speaker_id_budget_voices_total',
    'First blocked detection per voice and matcher generation, by first cap',
    'cap',
)
BUDGET_SOCKETS = _counter(
    'omi_speaker_id_budget_sockets_total', 'First blocked detection per socket lifetime, by first cap', 'cap'
)
EMBEDDING_ATTEMPTS = _counter(
    'omi_speaker_id_embedding_attempts_total', 'Live query reservations and extraction completions', 'outcome'
)
REJECTOR_DEMOTIONS = _counter(
    'omi_speaker_id_rejector_demotions_total',
    'Proven-rejector pending entries deferred or provider updates coalesced',
    'action',
)
REJECTOR_TAIL_DENIALS = _counter(
    'omi_speaker_id_rejector_tail_denials_total',
    'Proven-rejector reservations denied to preserve the socket tail',
    'reason',
)

for _cap in ('voice', 'socket', 'both'):
    BUDGET_EXITS.labels(cap=_cap)
    BUDGET_VOICES.labels(cap=_cap)
    BUDGET_SOCKETS.labels(cap=_cap)
for _outcome in ('reserved', 'succeeded', 'failed'):
    EMBEDDING_ATTEMPTS.labels(outcome=_outcome)
for _action in ('deferred', 'coalesced'):
    REJECTOR_DEMOTIONS.labels(action=_action)
REJECTOR_TAIL_DENIALS.labels(reason='reserved_tail')

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

RECOVERY_GRANTS = _counter(
    'omi_speaker_id_recovery_tranches_total', 'Fresh PCM recovery allowance grants per voice generation', 'tranche'
)
RECOVERY_ACCEPTANCES = _counter(
    'omi_speaker_id_recovery_acceptances_total',
    'First automatic acceptance per voice generation after successful recovery extraction',
    'target',
)
RECOVERY_DENIALS = _counter(
    'omi_speaker_id_recovery_denials_total',
    'Recovery grants or extra reservations refused by voice eligibility',
    'reason',
)
for _tranche in ('first', 'second'):
    RECOVERY_GRANTS.labels(tranche=_tranche)
for _target in ('owner', 'person'):
    RECOVERY_ACCEPTANCES.labels(target=_target)
for _reason in ('proven_rejector', 'clearly_far', 'completed_not_near_owner'):
    RECOVERY_DENIALS.labels(reason=_reason)

PCM_WINDOWS_RESTORED = _counter(
    'omi_speaker_id_pcm_windows_restored_total',
    'Candidate query windows reaching their physical minimum only after exact full-span sample restoration',
    'reason',
)
PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding')

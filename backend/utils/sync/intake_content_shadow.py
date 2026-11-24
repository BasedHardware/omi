"""Post-commit, fixed-cardinality measurement of plain-sync append contents."""

from typing import Any

from prometheus_client import Counter

from utils.conversations.recorded_time import conversation_span

FIELD = '_sync_intake_content_shadow'
SPEECH = frozenset({'new_speech', 'repeat_only'})
SPANS = frozenset({'unchanged', 'growth', 'changed', 'unknown'})
INTAKE_CONTENT = Counter(
    'omi_sync_intake_content_shadow_total',
    'Committed plain-sync merges by surviving speech and recorded extent change; shadow only',
    ['speech', 'span'],
)
for _speech in SPEECH:
    for _span in SPANS:
        INTAKE_CONTENT.labels(speech=_speech, span=_span)


def capture(conversation: dict, plans: list[Any]) -> None:
    """Use the same final survivors as live append_stats, without new reads.

    Mark only the returned result after payload encoding. Aborted attempts do
    not emit or persist observations. Size rollover plans each count once.
    """
    observations = []
    for plan in plans:
        if plan.created or plan.result.get('sync_live_target'):
            continue
        before = conversation_span(plan.matched.get(plan.canonical) or {})
        after = conversation_span(plan.result)
        span = 'unknown'
        if before is not None and after is not None:
            old = (before.recorded_start, before.recorded_end)
            new = (after.recorded_start, after.recorded_end)
            span = 'unchanged' if old == new else 'growth' if new[0] <= old[0] and new[1] >= old[1] else 'changed'
        observations.append(('new_speech' if plan.survivors else 'repeat_only', span))
    if observations:
        conversation[FIELD] = observations


def emit(conversation: dict) -> None:
    for speech, span in conversation.pop(FIELD, []):
        if speech in SPEECH and span in SPANS:
            INTAKE_CONTENT.labels(speech=speech, span=span).inc()

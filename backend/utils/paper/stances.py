"""Stance ledger — what you have been asserting, and how one-sidedly.

A stance is one-sided when you keep landing on the same position across several days and
nothing in the record shows you weighing the other way. That is the trigger for
Counterpoint. Selection is deterministic here; only the argument itself is written by a
model, which keeps the block from firing on a position you never actually took.
"""

from models.paper import Counterpoint

from .text import overlap

# Two statements this similar express the same stance. Kept at half the content words
# because decisions are short — at 0.6 a four-word position needs three words to recur
# verbatim, which real speech never does.
SAME_STANCE_THRESHOLD = 0.5

# A stance must recur on at least this many distinct days before it counts as a pattern
# rather than a one-off call.
MIN_DISTINCT_DAYS = 2

# Language that shows the user already weighed the other side. Its presence in the same
# stance cluster disqualifies the stance — they are not being one-sided, they are torn.
_HEDGES = (
    'but ',
    'however',
    'although',
    'on the other hand',
    'trade-off',
    'tradeoff',
    'not sure',
    'unclear',
    'risk',
    'downside',
    'depends',
)


def _is_hedged(text: str) -> bool:
    lowered = (text or '').lower()
    return any(hedge in lowered for hedge in _HEDGES)


def _echoes(summary: dict) -> list[str]:
    """Prose from a day that can corroborate a stance without being a decision.

    A position recurs in what someone kept *talking about*, not only in what got logged
    as a decision — so highlights count as evidence that the stance held that day, even
    though only a decision is ever quoted back.
    """
    out = []
    for highlight in summary.get('highlights') or []:
        topic = (highlight or {}).get('topic') or ''
        detail = (highlight or {}).get('summary') or ''
        joined = f'{topic} {detail}'.strip()
        if joined:
            out.append(joined)
    return out


def find_one_sided_stance(summaries: list[dict]) -> Counterpoint | None:
    """The most-repeated unhedged position in the window, or None.

    Clusters are seeded only by decisions — those are actual positions, and only a
    position can fairly be argued against. Highlights can add days to a cluster but can
    never create one.

    Returns a Counterpoint with ``argument`` left empty — the caller fills it in. The
    empty argument is what marks it as a candidate rather than a finished block.
    """
    ordered = sorted(summaries, key=lambda s: str(s.get('date') or ''))

    # Each cluster: representative text -> {dates}, and whether any member hedged.
    clusters: list[dict] = []
    for summary in ordered:
        day = str(summary.get('date') or '')
        if not day:
            continue
        for entry in summary.get('decisions_made') or []:
            decision = ((entry or {}).get('decision') or '').strip()
            if not decision:
                continue

            for cluster in clusters:
                if overlap(decision, cluster['text']) >= SAME_STANCE_THRESHOLD:
                    cluster['dates'].add(day)
                    cluster['hedged'] = cluster['hedged'] or _is_hedged(decision)
                    break
            else:
                clusters.append(
                    {
                        'text': decision,
                        'dates': {day},
                        'hedged': _is_hedged(decision),
                        'first': day,
                    }
                )

    # Second pass: a day whose talk echoes an existing stance counts toward it.
    for summary in ordered:
        day = str(summary.get('date') or '')
        if not day:
            continue
        echoes = _echoes(summary)
        if not echoes:
            continue
        for cluster in clusters:
            if day in cluster['dates']:
                continue
            for echo in echoes:
                if overlap(cluster['text'], echo) >= SAME_STANCE_THRESHOLD:
                    cluster['dates'].add(day)
                    cluster['hedged'] = cluster['hedged'] or _is_hedged(echo)
                    break

    candidates = [c for c in clusters if not c['hedged'] and len(c['dates']) >= MIN_DISTINCT_DAYS]
    if not candidates:
        return None

    best = max(candidates, key=lambda c: (len(c['dates']), c['first']))
    return Counterpoint(
        position=best['text'],
        argument='',
        days_asserted=len(best['dates']),
        first_asserted=best['first'],
    )

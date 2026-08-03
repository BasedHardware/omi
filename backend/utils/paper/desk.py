"""The Desk — someone you mentioned, then stopped mentioning.

A person who came up once and then went quiet is more interesting than the person you
talk about daily, so this ranks by silence rather than by frequency. Only people Omi has
already identified are eligible; we never invent a relationship from a bare first name.
"""

from datetime import date

from models.paper import DeskItem

from .text import content_words, days_between

# Below this the person is simply part of the current week and not worth surfacing.
MIN_SILENCE_DAYS = 3

# Past this we assume the thread is genuinely closed rather than dropped.
MAX_SILENCE_DAYS = 45


def _mention_text(summary: dict) -> str:
    """All prose from one day's summary, where a person's name might appear."""
    parts = [str(summary.get('headline') or ''), str(summary.get('overview') or '')]
    for highlight in summary.get('highlights') or []:
        parts.append(str((highlight or {}).get('topic') or ''))
        parts.append(str((highlight or {}).get('summary') or ''))
    return ' '.join(parts)


def find_dropped_people(
    summaries: list[dict],
    people: list[str],
    today: date,
    limit: int = 1,
) -> list[DeskItem]:
    """People mentioned in the window, ranked by how long they have been quiet.

    ``people`` are known contact names from Omi. Matching is on the first name as a whole
    content word, so "Sam" matches "Sam said" but not "same".
    """
    ordered = sorted(summaries, key=lambda s: str(s.get('date') or ''), reverse=True)

    found: list[DeskItem] = []
    for name in people:
        first = (name or '').strip().split(' ')[0]
        if len(first) < 2:
            continue
        needle = content_words(first)
        if not needle:
            continue

        for summary in ordered:
            day = str(summary.get('date') or '')
            if not day:
                continue
            text = _mention_text(summary)
            if not needle <= content_words(text):
                continue

            silence = days_between(day, today)
            if MIN_SILENCE_DAYS <= silence <= MAX_SILENCE_DAYS:
                found.append(
                    DeskItem(
                        name=name.strip(),
                        context=str(summary.get('headline') or '').strip(),
                        last_mentioned=day,
                        days_since=silence,
                    )
                )
            # Only the most recent mention matters, dropped or not.
            break

    found.sort(key=lambda item: (-item.days_since, item.name))
    return found[:limit]

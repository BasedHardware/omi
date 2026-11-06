"""Presentation-only replacement of transcript-echo minimum titles."""

from datetime import datetime
from collections.abc import Mapping
from typing import Any, Callable, Optional

from config.episodes import home_neutral_minimum_titles_enabled

from utils.conversations.deterministic_minimum import fallback_title, first_sentence, truncate_on_word_boundary


def apply_user_title(row: dict[str, Any], user_title: str | None) -> None:
    """Apply the repository-resolved durable user override to its read copy."""
    if user_title is not None:
        structured = row.get('structured')
        if not isinstance(structured, dict):
            structured = {}
            row['structured'] = structured
        structured['title'] = user_title


# Loaded beside list rows so an owed summary is visible without transcripts.
SUMMARY_DEBT_FIELDS = ('summary_due_at', 'summary_completed_at', 'summary_output_present')


def summary_owed(row: Mapping[str, Any]) -> bool:
    """The pipeline still owes this row a summary, so its stored title is provisional."""
    return (
        row.get('summary_due_at') is not None
        and not row.get('summary_completed_at')
        and not row.get('summary_output_present')
    )


def neutralize_minimum_title(
    row: dict[str, Any], *, tz_name_provider: Optional[Callable[[], Optional[str]]] = None
) -> dict[str, Any]:
    """Replace transcript-echo titles that are not the row's real title yet.

    Short, below-floor and summary-owed rows keep a neutral ``Recording · time``
    title until a real one lands. ``tz_name_provider`` is called only when a
    title is replaced; without a zone the time renders in UTC.
    """
    if not home_neutral_minimum_titles_enabled():
        return row
    structured = row.get('structured') or {}
    if (
        row.get('finalization_status') == 'dead_letter'
        or row.get('summary_retryable')
        or str(row.get('user_title') or '').strip()
    ):
        return row
    provenance = structured.get('title_provenance')
    text_parts = [str(s.get('text') or '').strip() for s in row.get('transcript_segments') or [] if isinstance(s, dict)]
    text = ' '.join(part for part in text_parts if part)
    first = next((part for part in text_parts if part), '')
    start, end = row.get('started_at'), row.get('finished_at')
    short = isinstance(start, datetime) and isinstance(end, datetime) and 0 <= (end - start).total_seconds() <= 60
    decision = row.get('relevance_decision') or {}
    floor = (
        row.get('summary_blocked_reason') == 'content_below_floor' or decision.get('reason') == 'content_below_floor'
    )
    title = structured.get('title')
    lazy = not provenance and len(first.split()) >= 8 and title == ' '.join(first.split()[:8])
    minimum = (short or floor or summary_owed(row)) and (
        provenance == 'server_minimum'
        or (not provenance and text and title == truncate_on_word_boundary(first_sentence(text)))
    )
    if not minimum and not lazy:
        return row
    result = dict(row)
    result['structured'] = {
        **structured,
        'title': fallback_title(row.get('started_at') or row.get('created_at'), tz_name=_zone(tz_name_provider)),
        'title_provenance': 'server_minimum',
    }
    return result


def _zone(provider: Optional[Callable[[], Optional[str]]]) -> Optional[str]:
    if provider is None:
        return None
    try:
        return provider()
    except Exception:
        # A title label must never fail a read; UTC is the documented fallback.
        return None


def user_zone_provider(uid: str) -> Callable[[], Optional[str]]:
    """Lazy, process-cached lookup of the user's stored zone for neutral titles."""

    def provider() -> Optional[str]:
        from database.notifications import get_cached_user_time_zone

        return get_cached_user_time_zone(uid)

    return provider


def project_home(uid: str, row: dict[str, Any], *, firestore_client=None, read_budget=None):
    """Neutral Home titles precede the shared transcript-capability projection."""
    from utils.agent_capabilities.transcripts import project

    return project(
        uid,
        neutralize_minimum_title(row, tz_name_provider=user_zone_provider(uid)),
        firestore_client=firestore_client,
        read_budget=read_budget,
    )

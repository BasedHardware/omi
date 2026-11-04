"""Presentation-only replacement of transcript-echo minimum titles."""

from datetime import datetime
from typing import Any

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


def neutralize_minimum_title(row: dict[str, Any]) -> dict[str, Any]:
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
    minimum = (short or floor) and (
        provenance == 'server_minimum'
        or (not provenance and text and title == truncate_on_word_boundary(first_sentence(text)))
    )
    if not minimum and not lazy:
        return row
    result = dict(row)
    result['structured'] = {
        **structured,
        'title': fallback_title(row.get('started_at') or row.get('created_at')),
        'title_provenance': 'server_minimum',
    }
    return result


def project_home(uid: str, row: dict[str, Any], *, firestore_client=None, read_budget=None):
    """Neutral Home titles precede the shared transcript-capability projection."""
    from utils.agent_capabilities.transcripts import project

    return project(uid, neutralize_minimum_title(row), firestore_client=firestore_client, read_budget=read_budget)

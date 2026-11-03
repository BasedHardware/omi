"""Presentation-only replacement of transcript-echo minimum titles."""

from copy import deepcopy
from typing import Any

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
    structured = row.get('structured') or {}
    if str(row.get('user_title') or '').strip():
        return row
    provenance = structured.get('title_provenance')
    text_parts = [str(s.get('text') or '').strip() for s in row.get('transcript_segments') or [] if isinstance(s, dict)]
    text = ' '.join(part for part in text_parts if part)
    first = next((part for part in text_parts if part), '')
    legacy = (
        not provenance
        and text
        and structured.get('title') in {truncate_on_word_boundary(first_sentence(text)), ' '.join(first.split()[:8])}
    )
    if provenance != 'server_minimum' and not legacy:
        return row
    result = deepcopy(row)
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

"""Conservative admission for the server's short-recording compute policy."""

from collections.abc import Callable, Mapping
from typing import Any

from utils.conversations.recovery import structured_is_rich
from utils.llm.output_language import normalize_language
from utils.observability.fallback import record_fallback


def _field(row: Any, name: str) -> Any:
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)


def has_existing_notes(conversation: Any) -> bool:
    """A minimum must never replace an enriched row, including a title-only one."""
    structured = _field(conversation, 'structured')
    title = _field(structured, 'title') or ''
    provenance = _field(structured, 'title_provenance')
    return structured_is_rich(structured) or (
        (bool(str(title).strip()) or bool(provenance)) and provenance != 'server_minimum'
    )


def english_word_floor(conversation: Any, text: str) -> bool:
    """Only known English capture speech has a covered reminder/word contract.

    Output-language preferences do not identify the spoken language. Unknown,
    multilingual and other captures use duration only. Non-ASCII letters also
    veto this rule, protecting mixed/mistagged unspaced scripts (including all
    CJK extensions) without guessing their word boundaries.
    """
    language = normalize_language(_field(conversation, 'language'))
    return language.split('-')[0] == 'en' and not any(c.isalpha() and not c.isascii() for c in text)


def selected_summary_app(uid: str, requested: bool, lookup: Callable[[str], Any]) -> bool:
    """User summary selection outranks compute thinning; an unreadable choice does too."""
    if requested:
        return True
    try:
        return bool(lookup(uid))
    except Exception:
        record_fallback(
            component='conversation_notes',
            from_mode='floor',
            to_mode='full_notes',
            reason='other',
            outcome='recovered',
        )
        return True

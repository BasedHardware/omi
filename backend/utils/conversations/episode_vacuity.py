"""Detect whole-field generic fallback prose, rather than phrases inside facts."""

import re
from typing import Any, Mapping

# Full clauses only: attribution, names, subjects and other specifics leave words
# unmatched. Joining several generic fallback clauses still counts as filler.
_FILLER = re.compile(
    r'(?:a\s+)?(?:brief exchange|quick chat|no (?:clear |concrete |meaningful )?'
    r'(?:topic|topics|decisions?|content|discussion)|nothing)'
    r'(?:\s+or\s+(?:clear |concrete )?(?:topic|decisions?))?'
    r'(?:\s+(?:was|is)\s+captured|\s+captured)?',
    re.IGNORECASE,
)


def _is_filler(text: str) -> bool:
    clauses = [part.strip(' \t\n-#*`') for part in re.split(r'[.;!\n]+', text) if part.strip()]
    return bool(clauses) and all(_FILLER.fullmatch(clause) for clause in clauses)


def is_vacuous_note(note: Any) -> bool:
    def value(field):
        return note.get(field, '') if isinstance(note, Mapping) else getattr(note, field, '')

    title, overview = value('title') or '', value('overview') or ''
    sections = value('sections') or []
    recap = '\n'.join(
        section.get('body_markdown', '') if isinstance(section, Mapping) else getattr(section, 'body_markdown', '')
        for section in sections
    )
    return not (overview.strip() or recap.strip()) or any(_is_filler(text) for text in (title, overview, recap))

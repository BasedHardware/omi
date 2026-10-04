"""Pure, deliberately narrow vacuity detector shared by eval and notes extraction."""

import re
from typing import Any, Mapping

_VACUOUS = re.compile(
    r'\b(?:brief exchange|no clear topic|nothing (?:was )?captured|no (?:concrete |clear )?'
    r'(?:decisions?|topic|content)(?: (?:was |is )?captured)?|quick chat|no meaningful (?:content|discussion))\b',
    re.IGNORECASE,
)


def is_vacuous_note(note: Any) -> bool:
    def value(field):
        return note.get(field, '') if isinstance(note, Mapping) else getattr(note, field, '')

    title, overview = value('title') or '', value('overview') or ''
    sections = value('sections') or []
    recap = '\n'.join(
        section.get('body_markdown', '') if isinstance(section, Mapping) else section.body_markdown
        for section in sections
    )
    return not (overview.strip() or recap.strip()) or any(
        _VACUOUS.search(text) is not None for text in (title, overview, recap)
    )

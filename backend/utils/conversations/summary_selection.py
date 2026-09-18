"""Canonical summary projection and primary-content selection.

The stored conversation shape has two representations of the first-party note:
``structured.overview`` is the released compatibility field and
``structured.sections`` is the structured source used by newer clients.  This
module keeps consumers from composing both representations into one view.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional

SummaryKind = Literal['app', 'overview', 'sections', 'empty']


@dataclass(frozen=True)
class SummarySelection:
    """The one body a client should render or export."""

    kind: SummaryKind
    content: str
    app_id: Optional[str] = None
    result_index: Optional[int] = None


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ''


def render_sections_markdown(sections: Any) -> str:
    """Render structured sections as deterministic compatibility Markdown.

    Empty headings do not produce heading-only output.  Empty sections are
    omitted, while body-only sections remain readable and preserve their text.
    """

    rendered: list[str] = []
    for section in sections or []:
        heading = _text(_value(section, 'heading'))
        body = _text(_value(section, 'body_markdown'))
        if heading and body:
            rendered.append(f'## {heading}\n\n{body}')
        elif body:
            rendered.append(body)
    return '\n\n'.join(rendered)


def select_primary_summary(conversation: Any) -> SummarySelection:
    """Select the single primary summary body for display, copy, and sharing.

    App results have explicit precedence when their content is usable, even
    when the result has no app ID.  The structured section projection wins
    over an identical overview so all clients agree on its provenance; a
    divergent overview remains authoritative because it may be a user edit.
    """

    for result_index, result in enumerate(_value(conversation, 'apps_results', []) or []):
        content = _text(_value(result, 'content'))
        if content:
            app_id = _value(result, 'app_id')
            return SummarySelection(
                kind='app',
                content=content,
                app_id=app_id if isinstance(app_id, str) else None,
                result_index=result_index,
            )

    structured = _value(conversation, 'structured', {}) or {}
    overview = _text(_value(structured, 'overview'))
    sections = render_sections_markdown(_value(structured, 'sections', []) or [])
    if overview and sections and overview == sections:
        return SummarySelection(kind='sections', content=sections)
    if overview:
        return SummarySelection(kind='overview', content=overview)
    if sections:
        return SummarySelection(kind='sections', content=sections)
    return SummarySelection(kind='empty', content='')


__all__ = ['SummaryKind', 'SummarySelection', 'render_sections_markdown', 'select_primary_summary']

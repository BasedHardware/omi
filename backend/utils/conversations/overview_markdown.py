"""Safe HTML for notes-v2 overview markdown in share emails.

Notes v2 stores ``conversation.structured.overview`` as markdown. The share
email used to escape each line as plain text, so every external recipient saw
literal ``##`` and ``-``. This module renders a closed subset with
``markdown-it-py`` (already in the runtime lock): headings, paragraphs, bullet
and numbered lists, bold, italic, and ``http(s)`` links. HTML from the model is
never passed through; every text node is escaped first.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

_md = MarkdownIt('commonmark', {'html': False, 'breaks': True, 'linkify': False})
_md.disable(
    [
        'image',
        'fence',
        'code',
        'blockquote',
        'hr',
        'html_block',
        'html_inline',
        'autolink',
        'lheading',
    ]
)


def _https_only_link(url: str) -> bool:
    value = (url or '').strip().lower()
    return value.startswith('http://') or value.startswith('https://')


_md.validateLink = _https_only_link


def overview_to_email_html(overview: str) -> str:
    """Render overview markdown to a safe HTML fragment for the share email."""
    if not overview:
        return ''
    return _md.render(overview).strip()

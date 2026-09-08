"""Safe HTML for notes-v2 overview markdown in share emails.

Notes v2 stores ``conversation.structured.overview`` as markdown. The share
email used to escape each line as plain text, so every external recipient saw
literal ``##`` and ``-``. This module renders a closed subset — headings,
paragraphs, bullet and numbered lists, bold, italic, and ``http(s)`` links —
without a third-party parser. Every text node is escaped first, so HTML from
the model never reaches the email.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
_UL_ITEM = re.compile(r'^[-*+]\s+(.+)$')
_OL_ITEM = re.compile(r'^\d+\.\s+(.+)$')
_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
_BOLD = re.compile(r'\*\*(.+?)\*\*')
_ITALIC = re.compile(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)')


def _escape_text(value: str) -> str:
    return value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _inline(text: str) -> str:
    escaped = _escape_text(text)
    escaped = _LINK.sub(r'<a href="\2">\1</a>', escaped)
    escaped = _BOLD.sub(r'<strong>\1</strong>', escaped)
    return _ITALIC.sub(r'<em>\1</em>', escaped)


def _is_special(line: str) -> bool:
    return bool(_HEADING.match(line) or _UL_ITEM.match(line) or _OL_ITEM.match(line))


def overview_to_email_html(overview: str) -> str:
    """Render overview markdown to a safe HTML fragment for the share email."""
    if not overview:
        return ''
    parts: list[str] = []
    lines = overview.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            parts.append(f'<h{level}>{_inline(heading.group(2))}</h{level}>')
            i += 1
            continue
        if _UL_ITEM.match(line):
            items: list[str] = []
            while i < len(lines):
                item = _UL_ITEM.match(lines[i])
                if not item:
                    break
                items.append(f'<li>{_inline(item.group(1))}</li>')
                i += 1
            parts.append('<ul>' + ''.join(items) + '</ul>')
            continue
        if _OL_ITEM.match(line):
            items = []
            while i < len(lines):
                item = _OL_ITEM.match(lines[i])
                if not item:
                    break
                items.append(f'<li>{_inline(item.group(1))}</li>')
                i += 1
            parts.append('<ol>' + ''.join(items) + '</ol>')
            continue
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not _is_special(lines[i]):
            para.append(lines[i])
            i += 1
        parts.append('<p>' + '<br>'.join(_inline(part) for part in para) + '</p>')
    return ''.join(parts)

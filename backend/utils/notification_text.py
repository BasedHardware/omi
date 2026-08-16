"""Plain-text rendering for push notification bodies.

Notification bodies are rendered by the OS, which has no markdown support: an
answer written as ``**US President**: ...`` shows the literal asterisks on the
lock screen. The markdown stays in the message payload (the app renders it in
chat) — only the displayed body is flattened.
"""

import re

_FENCE_RE = re.compile(r'^\s*```.*$', re.MULTILINE)
_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\([^)]*\)')
_LINK_RE = re.compile(r'\[([^\]]*)\]\([^)]*\)')
_HEADING_RE = re.compile(r'^\s{0,3}#{1,6}\s+', re.MULTILINE)
_BLOCKQUOTE_RE = re.compile(r'^\s{0,3}>\s?', re.MULTILINE)
_HORIZONTAL_RULE_RE = re.compile(r'^\s{0,3}([-*_])\s*(?:\1\s*){2,}$', re.MULTILINE)
_BULLET_RE = re.compile(r'^(\s*)[-*+]\s+', re.MULTILINE)
_INLINE_CODE_RE = re.compile(r'`+([^`]+)`+')
_BOLD_ITALIC_RE = re.compile(r'(\*{1,3})(\S.*?\S|\S)\1', re.DOTALL)
_UNDERSCORE_EMPHASIS_RE = re.compile(r'(?<![\w\\])(_{1,3})(\S.*?\S|\S)\1(?![\w])', re.DOTALL)
_STRIKETHROUGH_RE = re.compile(r'~~(\S.*?\S|\S)~~', re.DOTALL)
_BLANK_LINES_RE = re.compile(r'\n{3,}')


def to_plain_text(body: str) -> str:
    """Flatten markdown in ``body`` to what the OS should display."""
    if not body:
        return body

    text = _FENCE_RE.sub('', body)
    text = _IMAGE_RE.sub(r'\1', text)
    text = _LINK_RE.sub(r'\1', text)
    text = _HORIZONTAL_RULE_RE.sub('', text)
    text = _HEADING_RE.sub('', text)
    text = _BLOCKQUOTE_RE.sub('', text)
    text = _BULLET_RE.sub(r'\1• ', text)
    text = _INLINE_CODE_RE.sub(r'\1', text)
    text = _BOLD_ITALIC_RE.sub(r'\2', text)
    text = _UNDERSCORE_EMPHASIS_RE.sub(r'\2', text)
    text = _STRIKETHROUGH_RE.sub(r'\1', text)
    text = _BLANK_LINES_RE.sub('\n\n', text)

    return text.strip()

"""Adapt Omi chat answers for the Even Realities G2 glasses display.

Omi writes for a phone: markdown, bullet lists, links, fenced code, inline
citations (``yesterday[1][2]``), emoji and long paragraphs. The G2 renders
roughly 400 characters of monochrome text with no markdown, no fonts, no
alignment and a firmware-limited character set, so raw Omi output arrives as
garbage. This module is the adapter between the two.

Three entry points:

    fit_for_glasses(text, limit=380) -> str
        One screen of display-ready text.

    paginate(text, page_size=400) -> list[str]
        Display-ready text split across several screens, losing nothing.

    openai_chat_completion(content, model='omi') -> dict
        The response body the Even "Add Agent" endpoint expects.

Stdlib only -- the bridge must run before any venv exists.
"""

from __future__ import annotations

import re
import time
import unicodedata
import uuid

__all__ = [
    'DEFAULT_LIMIT',
    'DEFAULT_PAGE_SIZE',
    'fit_for_glasses',
    'paginate',
    'openai_chat_completion',
]

# The G2 shows ~400 characters. The default fit limit keeps a little headroom
# so a caller can prepend a short prefix without overflowing the screen.
DEFAULT_LIMIT = 380
DEFAULT_PAGE_SIZE = 400

ELLIPSIS = '...'

# A sentence boundary is the nicest place to cut, but only if it still fills
# the screen. Omi's bullet lists carry no terminal punctuation, so the "last
# sentence that fits" can sit a long way back and waste half the display --
# and on a 400-character screen those wasted lines are real information. Below
# this fraction of the budget we take the word boundary instead.
_MIN_SENTENCE_FILL = 0.6


# --------------------------------------------------------------------------
# Markdown stripping
#
# Order matters and is enforced by _strip_markdown: block constructs first
# (they are anchored to line starts and would be destroyed by inline rules),
# then links before bare URLs (so a link target is never mistaken for prose),
# then citations, then emphasis.
# --------------------------------------------------------------------------

# A fence line -- ```python / ``` / ~~~ -- is dropped, its contents kept. The
# code is often the whole answer to a "how do I" question; the fence is never
# information.
_FENCE_RE = re.compile(r'^[ \t]*(?:`{3,}|~{3,})[^\n]*$', re.MULTILINE)

# Horizontal rules: ---, ***, ___ (with optional spaces between). Must run
# before the bullet rule so "- - -" is not read as a list item.
_HR_RE = re.compile(r'^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$', re.MULTILINE)

_HEADING_RE = re.compile(r'^[ \t]{0,3}#{1,6}[ \t]*', re.MULTILINE)
_QUOTE_RE = re.compile(r'^[ \t]*>+[ \t]?', re.MULTILINE)

# -, *, + and 1. / 1) all collapse to a plain "- " marker.
_BULLET_RE = re.compile(r'^[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+', re.MULTILINE)

# GitHub task list boxes, after the bullet above has been normalised.
_TASK_RE = re.compile(r'^- \[[ xX]\][ \t]*', re.MULTILINE)

# Images carry no information on a monochrome text display -- drop them whole.
_IMAGE_RE = re.compile(r'!\[[^\]\n]*\]\([^)\n]*\)')

# [label](url) -> label
_LINK_RE = re.compile(r'\[([^\]\n]*)\]\([^)\n]*\)')

_AUTOLINK_RE = re.compile(r'<(?:https?|ftp|mailto):[^>\s]*>')
_URL_RE = re.compile(r'(?:https?://|ftp://|www\.)[^\s<>()\[\]"\']+', re.IGNORECASE)

# Omi citations: "text[1]", "text[1][2]". The negative lookahead keeps this
# from firing on a markdown link whose label happens to be a number.
_CITATION_RE = re.compile(r'\[\d{1,3}\](?!\()')

_CODE_RE = re.compile(r'`{1,3}([^`\n]*)`{1,3}')
_BOLD_ITALIC_RE = re.compile(r'\*\*\*([^*\n]+)\*\*\*|___([^_\n]+)___')
_BOLD_RE = re.compile(r'\*\*([^*\n]+)\*\*|__([^_\n]+)__')
_ITALIC_RE = re.compile(r'(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])')
_STRIKE_RE = re.compile(r'~~([^~\n]+)~~')

# Brackets left empty once their contents were removed, e.g. "see ()".
_EMPTY_PAIR_RE = re.compile(r'\([ \t]*\)|\[[ \t]*\]|<[ \t]*>')

# A space that only exists because something was deleted before punctuation.
_SPACE_BEFORE_PUNCT_RE = re.compile(r'[^\S\n]+([,.;:!?])')

_HORIZONTAL_WS_RE = re.compile(r'[^\S\n]+')
_BLANK_LINES_RE = re.compile(r'\n{3,}')

# Sentence terminator, allowing a closing quote/bracket, followed by space or
# end of text. Used to prefer sentence boundaries when truncating.
_SENTENCE_END_RE = re.compile(r'[.!?][\'")\]]*(?=\s|\Z)')
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')

# Leftovers that carry no meaning once their content was stripped.
_EMPTY_LINE_TOKENS = frozenset({'-', '*', '+', '- -', '|', '-|', '#'})


# --------------------------------------------------------------------------
# Character set
#
# The firmware font is limited, so anything outside printable ASCII is either
# transliterated to a recognisable ASCII equivalent or dropped. Dropping is
# always safe; rendering an unsupported glyph is not.
# --------------------------------------------------------------------------

_TRANSLITERATIONS = {
    # Quotes and primes.
    '‘': "'",
    '’': "'",
    '‚': "'",
    '‛': "'",
    '′': "'",
    '“': '"',
    '”': '"',
    '„': '"',
    '‟': '"',
    '″': '"',
    '«': '"',
    '»': '"',
    '‹': "'",
    '›': "'",
    # Dashes and minus.
    '‐': '-',
    '‑': '-',
    '‒': '-',
    '–': '-',
    '—': '-',
    '―': '-',
    '−': '-',
    # Ellipsis expands, so a smart ellipsis still reads as one on-device.
    '…': '...',
    # Spaces that are not U+0020.
    ' ': ' ',
    ' ': ' ',
    ' ': ' ',
    ' ': ' ',
    ' ': ' ',
    '　': ' ',
    # Zero-width joiners/marks: emoji glue and invisible junk.
    '​': '',
    '‌': '',
    '‍': '',
    '﻿': '',
    '⁠': '',
    # List glyphs Omi sometimes emits directly.
    '•': '-',
    '‣': '-',
    '▪': '-',
    '●': '-',
    '◦': '-',
    '·': '-',
    # Arrows and math that show up in explanations.
    '→': '->',
    '←': '<-',
    '↔': '<->',
    '⇒': '=>',
    '≤': '<=',
    '≥': '>=',
    '≠': '!=',
    '×': 'x',
    '÷': '/',
    '⁄': '/',
    # Currency and marks with no ASCII decomposition.
    '€': 'EUR',
    '£': 'GBP',
    '¥': 'JPY',
    '¢': 'c',
    '™': 'TM',
    '®': '(R)',
    '©': '(C)',
}


def _to_safe_charset(text: str) -> str:
    """Map text onto printable ASCII, transliterating what has an equivalent.

    Anything with no sensible ASCII rendering -- emoji, CJK, symbols -- is
    dropped rather than shown as a missing glyph.
    """
    out: list[str] = []
    for char in text:
        if char == '\n':
            out.append(char)
            continue
        if ' ' <= char <= '~':
            out.append(char)
            continue
        if char == '\t':
            out.append(' ')
            continue
        replacement = _TRANSLITERATIONS.get(char)
        if replacement is not None:
            out.append(replacement)
            continue
        # Compatibility-decompose so "café" -> "cafe" and "½" -> "1/2".
        for piece in unicodedata.normalize('NFKD', char):
            if ' ' <= piece <= '~':
                out.append(piece)
            elif unicodedata.combining(piece):
                continue
            else:
                out.append(_TRANSLITERATIONS.get(piece, ''))
    return ''.join(out)


def _strip_markdown(text: str) -> str:
    """Remove every markdown construct, keeping the words inside it."""
    # Block level first -- these are anchored to line starts.
    text = _FENCE_RE.sub('', text)
    text = _HR_RE.sub('', text)
    text = _HEADING_RE.sub('', text)
    text = _QUOTE_RE.sub('', text)
    text = _BULLET_RE.sub('- ', text)
    text = _TASK_RE.sub('- ', text)

    # Links before URLs, so a link target never survives as prose.
    text = _IMAGE_RE.sub('', text)
    text = _LINK_RE.sub(r'\1', text)
    text = _AUTOLINK_RE.sub('', text)
    text = _URL_RE.sub('', text)

    text = _CITATION_RE.sub('', text)

    # Emphasis, widest marker first so *** is not eaten by **.
    text = _CODE_RE.sub(r'\1', text)
    text = _BOLD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or '', text)
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or '', text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or '', text)
    text = _STRIKE_RE.sub(r'\1', text)
    return text


def _collapse_whitespace(text: str) -> str:
    """Squeeze horizontal runs, drop dead lines, allow at most one blank line."""
    lines = []
    for line in text.split('\n'):
        line = _HORIZONTAL_WS_RE.sub(' ', line).strip()
        # A bullet whose only content was a URL or an emoji is now noise.
        if line in _EMPTY_LINE_TOKENS:
            line = ''
        lines.append(line)
    text = '\n'.join(lines)
    text = _BLANK_LINES_RE.sub('\n\n', text)
    return text.strip()


def _with_ellipsis(head: str) -> str:
    """Close a truncated fragment with exactly one ellipsis."""
    # Strip trailing whitespace and dangling punctuation so a cut on a
    # sentence boundary reads "Done..." rather than "Done....".
    head = head.rstrip().rstrip(' .,;:')
    return head + ELLIPSIS


def _truncate(text: str, limit: int) -> str:
    """Cut to `limit` characters INCLUDING the ellipsis, never mid-word.

    Prefers a sentence boundary, falls back to a word boundary. The length
    cap is absolute: for the degenerate case of a single word longer than the
    limit there is no whitespace to cut on, and the word is hard-cut rather
    than overflowing the screen.
    """
    if limit <= 0:
        return ''
    if len(text) <= limit:
        return text
    if limit <= len(ELLIPSIS):
        # No room for both content and an ellipsis; content wins.
        return text[:limit].rstrip()

    budget = limit - len(ELLIPSIS)

    # 1. Last sentence boundary that fits.
    sentence_cut = 0
    for match in _SENTENCE_END_RE.finditer(text):
        if match.end() <= budget:
            sentence_cut = match.end()
        else:
            break

    # 2. Otherwise -- or when that boundary wastes most of the screen -- the
    #    last word boundary that fits. budget + 1 as the search end means a
    #    separator sitting exactly at `budget` still counts, which keeps the
    #    word before it whole.
    cut = sentence_cut
    if sentence_cut < budget * _MIN_SENTENCE_FILL:
        word_cut = max(text.rfind(' ', 0, budget + 1), text.rfind('\n', 0, budget + 1))
        cut = max(cut, word_cut)

    # 3. Otherwise a single oversized word: hard-cut to hold the limit.
    head = text[:cut] if cut > 0 else text[:budget]
    return _with_ellipsis(head)


def fit_for_glasses(text: str, limit: int = DEFAULT_LIMIT) -> str:
    """Turn an Omi chat answer into one screen of G2-renderable text.

    Strips markdown, removes URLs and Omi citation markers, forces the text
    into the firmware-safe character set, collapses whitespace and truncates
    on a sentence (else word) boundary. The result is never longer than
    `limit` -- the ellipsis is included in that budget -- and never carries
    leading or trailing whitespace. Empty or whitespace-only input, and input
    that is entirely unrenderable (emoji only), returns "".
    """
    if not text or not text.strip():
        return ''

    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _strip_markdown(text)
    text = _to_safe_charset(text)
    text = _EMPTY_PAIR_RE.sub('', text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r'\1', text)
    text = _collapse_whitespace(text)
    if not text:
        return ''
    return _truncate(text, limit)


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------


def _split_word(word: str, page_size: int) -> list[str]:
    """Last resort: a single word longer than the screen, cut into chunks."""
    return [word[i : i + page_size] for i in range(0, len(word), page_size)]


def _pack(units: list[str], sep: str, page_size: int, split_smaller) -> list[str]:
    """Greedily pack `units` into pages, recursing when a unit cannot fit.

    Every returned page is <= page_size and no non-whitespace character is
    lost or reordered.
    """
    pages: list[str] = []
    current = ''
    for unit in units:
        candidate = unit if not current else current + sep + unit
        if len(candidate) <= page_size:
            current = candidate
            continue
        if current:
            pages.append(current)
            current = ''
        if len(unit) <= page_size:
            current = unit
            continue
        # Too big even on its own: break it into finer units. All but the last
        # chunk are complete pages; the last stays open for what follows.
        chunks = split_smaller(unit, page_size)
        if chunks:
            pages.extend(chunks[:-1])
            current = chunks[-1]
    if current:
        pages.append(current)
    return pages


def _split_sentence(sentence: str, page_size: int) -> list[str]:
    return _pack(sentence.split(), ' ', page_size, _split_word)


def _split_paragraph(paragraph: str, page_size: int) -> list[str]:
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(paragraph) if s]
    return _pack(sentences, ' ', page_size, _split_sentence)


def paginate(text: str, page_size: int = DEFAULT_PAGE_SIZE) -> list[str]:
    """Split display-ready text into screens that each fit the G2.

    Breaks on paragraph boundaries, then sentence, then word -- never mid-word
    (the sole exception being a single word longer than a whole screen, which
    has no boundary to break on). No page exceeds `page_size`; every word is
    preserved, in order. Empty or whitespace-only input returns [].
    """
    if page_size <= 0:
        raise ValueError('page_size must be positive')
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r'\n[ \t]*\n', text.strip())]
    paragraphs = [p for p in paragraphs if p]
    return _pack(paragraphs, '\n\n', page_size, _split_paragraph)


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def openai_chat_completion(content: str, model: str = 'omi') -> dict:
    """Build the OpenAI chat-completion body the Even glasses expect.

    The Even "Add Agent" endpoint speaks the OpenAI chat-completions shape;
    the glasses render choices[0].message.content.
    """
    content = content if isinstance(content, str) else ''
    # The glasses do no tokenisation -- this is a cheap, honest estimate so the
    # body is structurally complete rather than a fabricated exact count.
    completion_tokens = (len(content) + 3) // 4 if content else 0
    return {
        'id': f'chatcmpl-{uuid.uuid4().hex[:24]}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': model,
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': content},
                'finish_reason': 'stop',
            }
        ],
        'usage': {
            'prompt_tokens': 0,
            'completion_tokens': completion_tokens,
            'total_tokens': completion_tokens,
        },
    }

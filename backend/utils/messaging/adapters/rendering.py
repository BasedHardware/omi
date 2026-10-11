"""Standard Markdown rendered by the adapter, with content-free item URLs."""

import html
import re
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

from markdown_it import MarkdownIt
from utils.observability.fallback import record_fallback

CITATION_PATTERN = r'\[\s*#?\s*(\d+)(?:\s*[,;–-]\s*#?\s*\d+)*\s*\](?!\()'
CITATIONS = re.compile(CITATION_PATTERN)


def item_link(kind, item_id):
    if kind not in {'conversation', 'task', 'memory'} or not isinstance(item_id, str) or not item_id.strip():
        raise ValueError('Invalid Omi item link')
    return 'https://h.omi.me/' + kind + '/' + quote(item_id, safe='')


def source_phrases(text, sources=()):
    # Citations are UI chrome; even unknown or malformed indices cannot leak.
    return CITATIONS.sub('', text)


def linked_items(response):
    items, seen = [], set()
    sources = response.get('conversations', response.get('memories', ()))
    for source in sources:
        kind = source.get('kind', 'conversation')
        item_id = source.get('id') or source.get('conversation_id')
        if kind not in {'conversation', 'task', 'memory'} or not item_id:
            continue
        title = source.get('title') or source.get('name') or source.get('structured', {}).get('title') or kind.title()
        if (kind, item_id) not in seen:
            seen.add((kind, item_id))
            items.append({'kind': kind, 'id': item_id, 'title': str(title), 'url': item_link(kind, item_id)})
    fields = {
        'taskCard': ('task', 'task_id'),
        'memoryLink': ('memory', 'memory_id'),
        'conversationLink': ('conversation', 'conversation_id'),
        'captureLink': ('conversation', 'conversation_id'),
    }
    for block in response.get('content_blocks', ()):
        if (
            block.get('type') == 'itemLink'
            and block.get('kind') in {'conversation', 'task', 'memory'}
            and block.get('id')
        ):
            kind, item_id = block['kind'], block['id']
            if (kind, item_id) not in seen:
                seen.add((kind, item_id))
                items.append(
                    {
                        'kind': kind,
                        'id': item_id,
                        'title': block.get('title') or kind.title(),
                        'url': item_link(kind, item_id),
                    }
                )
        if block.get('type') in fields:
            kind, field = fields[block['type']]
            item_id = block.get(field)
            if item_id and (kind, item_id) not in seen:
                seen.add((kind, item_id))
                items.append(
                    {
                        'kind': kind,
                        'id': item_id,
                        'title': block.get('summary') or kind.title(),
                        'url': item_link(kind, item_id),
                    }
                )
    return items


def item_buttons(items):
    rows = [[{'text': item['title'].replace('\n', ' ')[:32], 'url': item['url']}] for item in items[:5]]
    if len(items) > 5:
        rows.append([{'text': 'Open in Omi', 'url': 'https://h.omi.me'}])
    return {'inline_keyboard': rows} if rows else None


def _spoiler(state, silent):
    if not state.src.startswith('||', state.pos):
        return False
    end = state.src.find('||', state.pos + 2)
    if end < 0:
        return False
    if not silent:
        state.push('spoiler_open', 'tg-spoiler', 1)
        state.md.inline.parse(state.src[state.pos + 2 : end], state.md, state.env, state.tokens)
        state.push('spoiler_close', 'tg-spoiler', -1)
    state.pos = end + 2
    return True


def _tokens(text):
    parser = MarkdownIt('commonmark', {'html': False})
    parser.inline.ruler.before('text', 'spoiler', _spoiler)
    return parser.parse(source_phrases(text))


def _inline(tokens, rich):
    out = []
    for token in tokens or ():
        if token.type == 'text':
            value = html.escape(token.content, quote=False) if rich else token.content
            if rich:
                value = re.sub(r'\|\|(.+?)\|\|', r'<tg-spoiler>\1</tg-spoiler>', value)
            else:
                value = value.replace('||', '')
            out.append(value)
        elif token.type in {'spoiler_open', 'spoiler_close'} and rich:
            out.append('<tg-spoiler>' if token.nesting == 1 else '</tg-spoiler>')
        elif token.type == 'code_inline':
            value = html.escape(token.content, quote=False) if rich else token.content
            out.append('<code>' + value + '</code>' if rich else value)
        elif token.type in {'softbreak', 'hardbreak'}:
            out.append('\n')
        elif token.type in {'strong_open', 'strong_close', 'em_open', 'em_close'} and rich:
            tag = 'b' if token.type.startswith('strong') else 'i'
            out.append('<' + ('/' if token.nesting == -1 else '') + tag + '>')
        elif token.type == 'link_open' and rich:
            url = token.attrGet('href') or ''
            if urlparse(url).scheme in {'https', 'http'}:
                # Attribute quotes are encoded too, unlike text-node escaping.
                out.append('<a href="' + html.escape(url, quote=True) + '">')
            else:
                out.append('<a>')
        elif token.type == 'link_close' and rich:
            out.append('</a>')
        elif token.type == 'image':
            out.append(html.escape(token.content, quote=False) if rich else token.content)
    return ''.join(out)


def render_markdown(text, *, rich):
    out = []
    for token in _tokens(text):
        if token.type == 'inline':
            out.append(_inline(token.children, rich))
        elif token.type in {'fence', 'code_block'}:
            value = html.escape(token.content.rstrip('\n'), quote=False) if rich else token.content.rstrip('\n')
            out.append('<pre><code>' + value + '</code></pre>\n' if rich else value + '\n')
        elif token.type in {'paragraph_close', 'heading_close'}:
            out.append('\n')
        elif token.type == 'list_item_open':
            out.append('• ')
        elif token.type == 'blockquote_open':
            out.append('<blockquote>' if rich else '> ')
        elif token.type == 'blockquote_close' and rich:
            out.append('</blockquote>')
    return ''.join(out).strip()


def plain(text):
    return render_markdown(text, rich=False)


def split_text(text, size):
    """Split in UTF-16 units without splitting astral code points."""
    parts = []
    while text:
        end = units = 0
        for char in text:
            width = 2 if ord(char) > 0xFFFF else 1
            if units + width > size:
                break
            units += width
            end += 1
        if end == 0:
            raise ValueError('Character exceeds message budget')
        if end < len(text):
            boundary = max(text.rfind('\n', 0, end), text.rfind(' ', 0, end))
            if boundary > end // 2:
                end = boundary + 1
        parts.append(text[:end])
        text = text[end:]
    return tuple(parts)


class _HTMLUnits(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.units = []

    def handle_starttag(self, tag, attrs):
        self.units.append(('open', tag, self.get_starttag_text()))

    def handle_endtag(self, tag):
        self.units.append(('close', tag, '</' + tag + '>'))

    def handle_data(self, data):
        self.units.extend(('text', '', char) for char in data)

    def handle_entityref(self, name):
        self.units.append(('text', '', '&' + name + ';'))

    def handle_charref(self, name):
        self.units.append(('text', '', '&#' + name + ';'))


def split_html(text, size):
    """Close/reopen the active stack at boundaries; tags and entities are atomic.

    Budget includes markup, conservatively below Telegram's parsed-text limit.
    """
    parser = _HTMLUnits()
    parser.feed(text)
    stack, parts, current = [], [], ''
    units = lambda value: len(value.encode('utf-16-le')) // 2
    for kind, tag, value in parser.units:
        next_stack = list(stack)
        if kind == 'open':
            next_stack.append((tag, value))
        elif kind == 'close':
            if not next_stack or next_stack[-1][0] != tag:
                raise ValueError('Unbalanced HTML')
            next_stack.pop()
        closing = ''.join('</' + name + '>' for name, _ in reversed(next_stack))
        if units(current + value + closing) > size:
            suffix = ''.join('</' + name + '>' for name, _ in reversed(stack))
            parts.append(current + suffix)
            current = ''.join(opening for _, opening in stack)
            if units(current + value + closing) > size:
                raise ValueError('HTML token exceeds budget')
        current += value
        stack = next_stack
    if stack:
        raise ValueError('Unbalanced HTML')
    if current:
        parts.append(current)
    return tuple(parts)


def telegram(text, size=4096):
    try:
        return split_html(render_markdown(text, rich=True), size)
    except Exception:
        record_fallback(
            component='other', from_mode='telegram_html', to_mode='plain_text', reason='other', outcome='degraded'
        )
        return tuple(html.escape(part, quote=False) for part in split_text(source_phrases(text), max(2, size // 5)))


def html_plain(text):
    """Provider rejected known HTML; strip markup and decode only entities."""

    class PlainParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.chunks = []

        def handle_data(self, data):
            self.chunks.append(data)

    parser = PlainParser()
    parser.feed(text)
    return ''.join(parser.chunks)

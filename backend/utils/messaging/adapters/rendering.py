"""Standard Markdown rendered by the adapter, with content-free item URLs."""

import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, unquote, urlparse

from markdown_it import MarkdownIt
from utils.observability.fallback import record_fallback
from utils.share_links import build_share_url

_CITATION_LIST = r'#?\s*+\d++(?:\s*+[,;–-]\s*+#?\s*+\d++)*+'
# ASCII [1]/[#1]/[1][2], fullwidth 【1】, and markdown footnotes [^1].
# Possessive quantifiers keep an unclosed marker from backtracking.
CITATION_PATTERN = (
    rf'(?:\[\s*+{_CITATION_LIST}\s*+\](?!\()|【\s*+{_CITATION_LIST}\s*+】|\[\^\s*+{_CITATION_LIST}\s*+\])'
)
CITATIONS = re.compile(CITATION_PATTERN)
_MARKDOWN_LINK = re.compile(r'\[([^\]\n]*)\]\(([^)\n]*)\)')
_UNSAFE_SCHEME = re.compile(r'(?i)(?:javascript|data|vbscript|file)\s*:[^\s<>()]*|\bhttp(?!s)\s*:[^\s<>()]*')
_BUTTON_LABEL_LIMIT = 30


def item_link(kind, item_id):
    if kind not in {'conversation', 'task', 'memory'} or not isinstance(item_id, str) or not item_id.strip():
        raise ValueError('Invalid Omi item link')
    return build_share_url('/' + kind + '/' + quote(item_id, safe=''))


def item_list_link(items):
    """Content-free ordered navigation; encode IDs without changing repeated keys."""
    pairs = []
    for item in items[:10]:
        item_link(item['kind'], item['id'])  # Apply the singular-link validation.
        pairs.append(item['kind'] + '=' + quote(item['id'], safe=''))
    if not pairs:
        raise ValueError('Items required')
    return build_share_url('/items?' + '&'.join(pairs))


def valid_item_link(url):
    """Accept only canonical singular/list links on the configured share base."""
    if not isinstance(url, str):
        return False
    try:
        if url.startswith(build_share_url('/items?')):
            pairs = parse_qsl(urlparse(url).query, keep_blank_values=True)
            return 1 < len(pairs) <= 10 and url == item_list_link(
                [{'kind': kind, 'id': item_id} for kind, item_id in pairs]
            )
        for kind in ('conversation', 'task', 'memory'):
            prefix = build_share_url('/' + kind + '/')
            if url.startswith(prefix):
                return url == item_link(kind, unquote(url[len(prefix) :]))
    except (ValueError, KeyError, TypeError):
        return False
    return False


def _https_url(url):
    """https URLs with a host only. javascript:, http, and scheme-relative links are not links."""
    if not isinstance(url, str) or not url or any(ord(char) < 33 for char in url):
        return None
    parsed = urlparse(url.strip().strip('<>'))
    if parsed.scheme != 'https' or not parsed.hostname:
        return None
    return url.strip().strip('<>')


def _drop_unsafe_links(text):
    def replace(match):
        destination = match.group(2).strip().strip('<>')
        if _https_url(destination):
            return match.group(0)
        return match.group(1)

    return _UNSAFE_SCHEME.sub('', _MARKDOWN_LINK.sub(replace, text))


def source_phrases(text, sources=()):
    # Citations are UI chrome; even unknown or malformed indices cannot leak.
    return _drop_unsafe_links(CITATIONS.sub('', text or ''))


def linked_items(response):
    items, seen = [], set()
    sources = (*response.get('conversations', ()), *response.get('memories', ()))
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
    # Tool results are candidates, not evidence that the answer recommended them.
    answer = ' '.join(plain(response.get('text', '')).casefold().split())
    referenced = []
    for item in items:
        title = ' '.join(plain(item['title']).casefold().split())
        needles = [item['url'].casefold(), str(item['id']).casefold()]
        if title and title not in {'task', 'memory', 'conversation'}:
            needles.append(title)
        positions = []
        for needle in needles:
            match = re.search(r'(?<!\w)' + re.escape(needle) + r'(?!\w)', answer)
            if match:
                positions.append(match.start())
        if positions:
            referenced.append((min(positions), item))
    return [item for _, item in sorted(referenced, key=lambda pair: pair[0])][:10]


def button_label(title):
    """Keep complete words within a phone-sized row, including the ellipsis."""
    text = ' '.join(str(title or '').split())
    if len(text) > _BUTTON_LABEL_LIMIT:
        prefix = text[: _BUTTON_LABEL_LIMIT - 1]
        if text[_BUTTON_LABEL_LIMIT - 1] != ' ':
            prefix = prefix.rsplit(' ', 1)[0] if ' ' in prefix else ''
        text = prefix.rstrip() + '…' if prefix else 'Item…'
    return text or 'Item'


def item_buttons(items):
    rows = [[{'text': button_label(item['title']), 'url': item['url']}] for item in items[:5]]
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
    parser.enable(['table', 'strikethrough'])
    parser.inline.ruler.before('text', 'spoiler', _spoiler)
    return parser.parse(source_phrases(text))


def _inline(tokens, rich):
    out = []
    link_urls = []
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
        elif token.type in {'strong_open', 'strong_close', 'em_open', 'em_close', 's_open', 's_close'} and rich:
            tag = 'b' if token.type.startswith('strong') else ('s' if token.type.startswith('s_') else 'i')
            out.append('<' + ('/' if token.nesting == -1 else '') + tag + '>')
        elif token.type == 'link_open':
            link_urls.append(_https_url(token.attrGet('href') or ''))
            if rich and link_urls[-1]:
                # Attribute quotes are encoded too, unlike text-node escaping.
                out.append('<a href="' + html.escape(link_urls[-1], quote=True) + '">')
        elif token.type == 'link_close':
            url = link_urls.pop() if link_urls else None
            if url and rich:
                out.append('</a>')
            elif url:
                out.append(' (' + url + ')')
        elif token.type == 'image':
            out.append(html.escape(token.content, quote=False) if rich else token.content)
    return ''.join(out)


def _render_table(tokens, rich):
    rows, row = [], []
    for token in tokens:
        if token.type == 'tr_open':
            row = []
        elif token.type == 'inline':
            row.append((_inline(token.children, False), _inline(token.children, rich)))
        elif token.type == 'tr_close':
            rows.append(row)
    if not rows:
        return ''
    columns = max(len(row) for row in rows)
    widths = [max(len(row[i][0]) if i < len(row) else 0 for row in rows) for i in range(columns)]
    if rich and sum(widths) + 2 * (columns - 1) <= 40:
        lines = ['  '.join(cell[0].ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in rows]
        return '<pre>' + html.escape('\n'.join(lines), quote=False) + '</pre>\n'
    headers = [cell[0] for cell in rows[0]]
    blocks = []
    for row in rows[1:]:
        lines = []
        for i, cell in enumerate(row):
            if i == 0:
                lines.append('<b>' + html.escape(cell[0], quote=False) + '</b>' if rich else cell[0])
            else:
                header = headers[i] if i < len(headers) else 'Column ' + str(i + 1)
                lines.append((html.escape(header, quote=False) if rich else header) + ': ' + cell[1])
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks) + '\n'


def render_markdown(text, *, rich):
    out, lists = [], []
    tokens = iter(_tokens(text))
    for token in tokens:
        if token.type == 'table_open':
            table = []
            for cell in tokens:
                if cell.type == 'table_close':
                    break
                table.append(cell)
            out.append(_render_table(table, rich))
        elif token.type == 'inline':
            out.append(_inline(token.children, rich))
        elif token.type in {'fence', 'code_block'}:
            value = html.escape(token.content.rstrip('\n'), quote=False) if rich else token.content.rstrip('\n')
            out.append('<pre><code>' + value + '</code></pre>\n' if rich else value + '\n')
        elif token.type in {'paragraph_close', 'heading_close'}:
            out.append('\n')
        elif token.type in {'ordered_list_open', 'bullet_list_open'}:
            lists.append(int(token.attrGet('start') or 1) if token.type == 'ordered_list_open' else None)
        elif token.type in {'ordered_list_close', 'bullet_list_close'}:
            lists.pop()
        elif token.type == 'list_item_open':
            if lists and lists[-1] is not None:
                out.append(str(lists[-1]) + '. ')
                lists[-1] += 1
            else:
                out.append('• ')
        elif token.type == 'blockquote_open':
            out.append('<blockquote>' if rich else '')
        elif token.type == 'blockquote_close' and rich:
            out.append('</blockquote>')
        elif token.type == 'hr':
            out.append('\n')
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

"""Rendering, citation and content-free item-link contracts for every adapter."""

import html
from html.parser import HTMLParser

import pytest

from utils.messaging.adapters import rendering


@pytest.mark.parametrize(
    'marker', ['[9]', '[#9]', '[ #9 ]', '[ 9 ]', '[# 9]', '[9, 10]', '[#9; #10]', '[9-10]', '[#9–#10]']
)
def test_every_raw_citation_is_removed(marker):
    assert rendering.source_phrases('See ' + marker + '.') == 'See .'
    assert marker not in ''.join(rendering.telegram('See ' + marker))
    assert marker not in rendering.plain('See ' + marker)


def test_html_formats_and_escapes_only_text_entities():
    value = '\n'.join(
        [
            '# Heading',
            '**Bold** _italic_ [link](https://example.com/?a=1&b=2)',
            '- one',
            '- two',
            '> quote',
            '`a < b & c > d`',
            '```python\na < b\n```',
            '||spoiler||',
            'literal <script> _inside_word_ ! .',
        ]
    )
    text = ''.join(rendering.telegram(value))
    for expected in [
        '<b>Bold</b>',
        '<i>italic</i>',
        '<a href="https://example.com/?a=1&amp;b=2">link</a>',
        '• one',
        '<blockquote>',
        '<code>a &lt; b &amp; c &gt; d</code>',
        '<pre><code>a &lt; b</code></pre>',
        '<tg-spoiler>spoiler</tg-spoiler>',
        '&lt;script&gt;',
        '! .',
    ]:
        assert expected in text
    assert '<script>' not in text
    assert '\\!' not in text


def test_plain_keeps_bullets_and_strips_emphasis_headings():
    assert rendering.plain('# Title\n\n- **bold** and _italic_\n- `code`') == 'Title\n• bold and italic\n• code'


def test_render_failure_has_observable_plain_fallback(monkeypatch):
    events = []
    monkeypatch.setattr(rendering, 'render_markdown', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError()))
    monkeypatch.setattr(rendering, 'record_fallback', lambda **kwargs: events.append(kwargs))
    assert rendering.telegram('a < b & c [#9]') == ('a &lt; b &amp; c ',)
    assert events[0]['outcome'] == 'degraded'


def test_splitting_balances_tags_and_preserves_entities_and_unicode():
    value = '<b><i>' + html.escape(('😀 & <value> ' * 30), quote=False) + '</i></b>'
    parts = rendering.split_html(value, 100)
    assert len(parts) > 1
    for part in parts:
        assert len(part.encode('utf-16-le')) // 2 <= 100
        stack = []

        class Check(HTMLParser):
            def handle_starttag(self, tag, attrs):
                stack.append(tag)

            def handle_endtag(self, tag):
                assert stack.pop() == tag

        Check().feed(part)
        assert not stack
    assert ''.join(rendering.html_plain(part) for part in parts) == '😀 & <value> ' * 30


@pytest.mark.parametrize('kind', ['conversation', 'task', 'memory'])
def test_link_builder_has_ruling_domain_and_encoded_id_only(kind):
    assert rendering.item_link(kind, 'opaque/id?x') == f'https://h.omi.me/{kind}/opaque%2Fid%3Fx'
    with pytest.raises(ValueError):
        rendering.item_link('person', 'id')


def test_item_buttons_bounded_labels_and_overflow():
    items = [dict(title='Long title ' * 10, url=rendering.item_link('task', str(i))) for i in range(7)]
    rows = rendering.item_buttons(items)['inline_keyboard']
    assert len(rows) == 6
    assert all(len(row[0]['text']) <= 32 for row in rows)
    assert rows[-1] == [dict(text='Open in Omi', url='https://h.omi.me')]
    assert all('callback_data' not in row[0] for row in rows)


def test_links_from_existing_blocks_deduplicated():
    items = rendering.linked_items(
        dict(
            text='Task',
            content_blocks=[
                dict(type='taskCard', task_id='a'),
                dict(type='taskCard', task_id='a'),
                dict(type='memoryLink', memory_id='b', summary='Memory'),
            ],
        )
    )
    assert len(items) == 2
    assert items[0]['url'] == 'https://h.omi.me/task/a'


def test_spoilers_support_nested_markdown():
    assert rendering.telegram('||**secret** and `code`||') == (
        '<tg-spoiler><b>secret</b> and <code>code</code></tg-spoiler>',
    )
    assert rendering.plain('||**secret**||') == 'secret'

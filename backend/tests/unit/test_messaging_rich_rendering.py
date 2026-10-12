"""Rendering, citation and content-free item-link contracts for every adapter."""

import html
from html.parser import HTMLParser

import pytest

from utils.messaging.adapters import rendering


@pytest.mark.parametrize(
    'marker',
    [
        '[9]',
        '[#9]',
        '[ #9 ]',
        '[ 9 ]',
        '[# 9]',
        '[9, 10]',
        '[#9; #10]',
        '[9-10]',
        '[#9–#10]',
        '[1][2]',
        '【1】',
        '【#1】',
        '【1】【2】',
        '【1, 2】',
        '[^1]',
        '[^1][^2]',
    ],
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
    assert len(rows) == 5
    assert all(len(row[0]['text']) <= 32 for row in rows)
    assert all(row[0]['url'] != 'https://h.omi.me' for row in rows)
    assert all('callback_data' not in row[0] for row in rows)


def test_links_from_existing_blocks_deduplicated():
    items = rendering.linked_items(
        dict(
            text='Task a and Memory b',
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


def test_plain_markdown_links_keep_the_destination():
    assert rendering.plain('[documentation](https://example.com/help)') == 'documentation (https://example.com/help)'


def test_non_https_links_are_dropped_and_hrefs_escape_markup():
    rendered = ''.join(
        rendering.telegram(
            '[ok](https://example.com/?q=<tag>&x="y") [js](javascript:alert(1)) '
            '[web](http://example.com) [scheme](https:alert(1)) <javascript:alert(2)>'
        )
    )
    assert 'href="https://example.com/?q=%3Ctag%3E&amp;x=%22y%22"' in rendered
    assert 'javascript:' not in rendered.lower()
    assert 'http://example.com' not in rendered
    assert 'https:alert' not in rendered
    assert '<a>' not in rendered
    assert rendered.count('<a ') == rendered.count('</a>') == 1
    plain = rendering.plain('[js](javascript:alert(1)) and [web](http://example.com) and [ok](https://example.com/a)')
    assert 'javascript:' not in plain.lower()
    assert 'http://' not in plain
    assert 'https://example.com/a' in plain


def test_button_labels_do_not_split_joiners_or_leak_into_urls():
    title = ('x' * 30) + '👨\u200d👩'
    rows = rendering.item_buttons([dict(title=title, url=rendering.item_link('memory', 'id'))])['inline_keyboard']
    label = rows[0][0]['text']
    assert len(label) <= 32
    assert not label.endswith('\u200d')
    assert title not in rows[0][0]['url']
    assert rows[0][0]['url'] == 'https://h.omi.me/memory/id'


def test_adversarial_unclosed_citation_does_not_backtrack():
    text = '[0,' + ' 0,' * 20000
    assert rendering.source_phrases(text) == text


@pytest.mark.parametrize('rich', [False, True])
def test_tables_strip_pipes_and_inline_markdown(rich):
    text = '| Name | State |\n|---|---|\n| **Alpha** | `Ready` |\n| Beta | Done |'
    result = rendering.render_markdown(text, rich=rich)
    assert '|' not in result and '**' not in result and '`' not in result
    if rich:
        assert result == '<pre>Name   State\nAlpha  Ready\nBeta   Done</pre>'
    else:
        assert result == 'Alpha\nState: Ready\n\nBeta\nState: Done'


@pytest.mark.parametrize('rich', [False, True])
def test_wide_table_uses_row_lists(rich):
    value = 'A long description that exceeds the phone width'
    result = rendering.render_markdown('| Task | Detail |\n|---|---|\n| **Alpha** | ' + value + ' |', rich=rich)
    assert '<pre>' not in result and '|' not in result
    assert ('<b>Alpha</b>' if rich else 'Alpha') in result
    assert 'Detail: ' + value in result


@pytest.mark.parametrize('rich', [False, True])
def test_common_block_markdown_does_not_leak(rich):
    result = rendering.render_markdown(
        '# Title\n\n> quote\n\n3. first\n4. second\n\n---\n\n```python\ncode\n```', rich=rich
    )
    assert '# ' not in result and '> quote' not in result and '```' not in result and '---' not in result
    assert '3. first' in result and '4. second' in result and 'code' in result


def test_item_selection_matches_answer_in_order_and_rejects_unmentioned_tools():
    sources = [
        dict(kind='task', id=str(i), title=title)
        for i, title in enumerate(
            [
                'Make a prediction market about the election',
                'Send both documents out for Signature',
                'Set up a session with the team',
                'Do YC application with Nick',
                'Try the double-click-to-mute feature',
            ]
        )
    ]
    result = rendering.linked_items(
        dict(
            text='**Set up a session with the team**, then Send both documents out for Signature.',
            conversations=sources,
        )
    )
    assert [item['id'] for item in result] == ['2', '1']
    assert rendering.linked_items(dict(text='Nothing useful.', conversations=sources)) == []
    assert rendering.linked_items(dict(text='Open task 0.', conversations=sources))[0]['id'] == '0'
    assert rendering.button_label(sources[0]['title']) == 'Make a prediction market…'
    assert rendering.button_label(sources[1]['title']) == 'Send both documents out for…'


def test_gfm_strikethrough_does_not_leak_markers():
    assert rendering.telegram('~~retired~~') == ('<s>retired</s>',)
    assert rendering.plain('~~retired~~') == 'retired'

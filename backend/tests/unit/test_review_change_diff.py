"""Recent-change diffs are bounded excerpts, computed from the journal row."""

from datetime import datetime, timezone

from database.review_changes import extract_change_diff
from models.review import ReviewChange

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def change(**extra):
    body = {
        'change_id': 'synthetic-change',
        'kind': 'other',
        'title': 'Spelling',
        'created_at': NOW,
        'undone': False,
    }
    body.update(extra)
    return body


def spelling_row(text, before='Omni', after='Omi', title='Launch planning', occurrences_segments=None):
    segments = occurrences_segments or [{'text': text, 'speaker_label': 'You', 'is_user': True}]
    return {
        'change': change(
            edit_kind='spelling',
            before=before,
            after=after,
            context={
                'conversation_title': title,
                'conversation_date': NOW,
                'segments': segments,
                'main_index': 0,
            },
            refs=[{'type': 'conversation', 'id': 'conv-1', 'label': title}],
        )
    }


def test_spelling_diff_is_one_span_with_context():
    diff = extract_change_diff(spelling_row('Please send the UL to the design group.', 'UL', 'URL'))
    assert diff is not None
    assert diff.field == 'transcript'
    assert diff.before == 'UL' and diff.after == 'URL'
    assert diff.context_before == 'Please send the '
    assert diff.context_after == ' to the design group.'
    assert diff.occurrences == 1
    assert diff.source_title == 'Launch planning'
    assert diff.source_started_at == NOW
    assert diff.group_key == 'transcript|ul|url'


def test_spelling_diff_counts_repeated_terms_and_groups_across_conversations():
    left = extract_change_diff(spelling_row('Omni met Omni before lunch.', title='Morning'))
    right = extract_change_diff(spelling_row('Then Omni called back.', title='Afternoon'))
    assert left is not None and right is not None
    assert left.occurrences == 2 and right.occurrences == 1
    assert left.group_key == right.group_key == 'transcript|omni|omi'
    assert left.source_title == 'Morning' and right.source_title == 'Afternoon'
    assert not left.context_before and 'Omni' in (left.context_after or '')


def test_long_transcript_context_stays_inside_the_window():
    text = 'FARLEFT ' + ('x ' * 200) + 'Omni ' + ('y ' * 200) + 'FARRIGHT'
    diff = extract_change_diff(spelling_row(text))
    assert diff is not None
    dumped = diff.model_dump()
    blob = ' '.join(value for value in dumped.values() if isinstance(value, str))
    assert 'FARLEFT' not in blob and 'FARRIGHT' not in blob
    assert len(diff.context_before or '') == 120
    assert len(diff.context_after or '') == 120
    assert len(diff.before or '') <= 240 and len(diff.after or '') <= 500
    assert text not in blob


def test_memory_and_task_and_title_before_after():
    memory = extract_change_diff(
        {
            'change': change(
                edit_kind='memory', title='Memory', before='Alex prefers tea', after='Alex prefers coffee'
            ),
            'before': {'content': 'Alex prefers tea'},
            'memory_edit': {'memory_id': 'mem-1', 'content': 'Alex prefers coffee'},
        }
    )
    task = extract_change_diff(
        {
            'change': change(edit_kind='close_task', title='Task'),
            'edits': [
                {
                    'collection': 'action_items',
                    'document_id': 'task-1',
                    'before': {'description': {'present': True, 'value': 'Send the notes'}},
                    'after': {'description': {'present': True, 'value': 'Send the notes today'}},
                }
            ],
        }
    )
    title = extract_change_diff(
        {
            'change': change(edit_kind='title', title='Title', kind='title_conversation'),
            'edits': [
                {
                    'collection': 'conversations',
                    'document_id': 'conv-1',
                    'before': {'structured.title': {'present': True, 'value': 'Launch'}},
                    'after': {'structured.title': {'present': True, 'value': 'Launch plan'}},
                }
            ],
        }
    )
    assert memory is not None and memory.field == 'content'
    assert memory.before == 'Alex prefers tea' and memory.after == 'Alex prefers coffee'
    assert task is not None and task.field == 'description'
    assert task.before == 'Send the notes' and task.after == 'Send the notes today'
    assert title is not None and title.field == 'title'
    assert title.before == 'Launch' and title.after == 'Launch plan'


def test_long_memory_returns_the_changed_span_not_the_whole_text():
    before = 'HEAD' + ('a' * 2000) + ' tea ' + ('b' * 2000) + 'TAIL'
    after = 'HEAD' + ('a' * 2000) + ' coffee ' + ('b' * 2000) + 'TAIL'
    diff = extract_change_diff(
        {
            'change': change(edit_kind='memory', title='Memory'),
            'before': {'content': before},
            'memory_edit': {'memory_id': 'mem-1', 'content': after},
        }
    )
    assert diff is not None
    blob = ' '.join(value for value in diff.model_dump().values() if isinstance(value, str))
    assert 'HEAD' not in blob and 'TAIL' not in blob
    assert 'tea' in (diff.before or '') and 'coffee' in (diff.after or '')
    assert len(diff.before or '') <= 240 and len(diff.context_before or '') <= 120
    assert len(blob) < len(before)


def test_merge_uses_item_labels():
    diff = extract_change_diff(
        {
            'change': change(
                edit_kind='merge_memories',
                kind='merge_memories',
                title='Merge memories',
                before='Fact A + Fact B',
                after='Combined fact',
                refs=[
                    {'type': 'memory', 'id': 'a', 'label': 'Fact A'},
                    {'type': 'memory', 'id': 'b', 'label': 'Fact B'},
                ],
            )
        }
    )
    assert diff is not None
    assert diff.field == 'merge'
    assert diff.before == 'Fact A + Fact B' and diff.after == 'Combined fact'
    assert diff.occurrences == 2
    assert diff.group_key.startswith('merge|')


def test_old_journal_without_text_has_no_diff():
    assert extract_change_diff({'change': change(title='Spelling', reason='Same text as the title')}) is None
    assert extract_change_diff({'phase': 'applied'}) is None
    assert extract_change_diff('not-a-row') is None


def test_review_change_omits_empty_diff_and_keeps_required_title():
    row = ReviewChange(
        change_id='synthetic-change', kind='other', title='Spelling', reason='Canonical name', created_at=NOW
    )
    dumped = row.model_dump()
    assert 'diff' not in dumped
    assert dumped['title'] == 'Spelling' and dumped['reason'] == 'Canonical name'
    assert row.model_dump(mode='python')['created_at'] == NOW
    diff = extract_change_diff(spelling_row('Please send the UL to the design group.', 'UL', 'URL'))
    wire = row.model_copy(update={'diff': diff}).model_dump(mode='json')
    assert wire['diff']['before'] == 'UL' and wire['diff']['group_key'] == 'transcript|ul|url'
    assert 'diff' not in ReviewChange.model_json_schema()['required']

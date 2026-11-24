"""A v3 window that names people must stay readable as a Conversation (list reads and the notes pass).

Synthetic data only; no model calls.
"""

import os

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime, timedelta, timezone  # noqa: E402

from models.conversation import Conversation  # noqa: E402
from models.structured import Participant, Structured  # noqa: E402
from utils.conversations.v3 import outline, planner  # noqa: E402

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def _built_row(people):
    row = {
        'id': 'r',
        'started_at': NOW,
        'source': 'omi',
        'recording': True,
        'transcript_segments': [{'text': 'hello world', 'start': 0, 'end': 10, 'is_user': True}],
    }
    groups = outline.stretches([row], NOW + timedelta(hours=1))
    entry = {
        'first_line': 1,
        'title': 'A stable subject',
        'line': 'You made a plan.',
        'kind': 'conversation',
        'emoji': '🛠',
        'people': people,
        'sections': [{'title': 'Plan'}],
    }
    [window] = planner.windows(groups, [[entry]])
    return planner.build('synthetic', window, {'r': row})


def test_planned_window_with_people_validates_as_conversation():
    built = _built_row(['Alex', 'Sam'])
    assert [p['source'] for p in built['structured']['participants']] == ['transcript', 'transcript']
    conversation = Conversation(**built)
    assert [p.name for p in conversation.structured.participants] == ['Alex', 'Sam']


def test_rows_stored_without_participant_source_still_read():
    # Rows the planner stored before the fix carry {'name'} only.
    structured = Structured.model_validate(
        {'title': 't', 'participants': [{'name': 'Alex'}, {'name': 'Sam', 'source': 'roster'}]}
    )
    assert [(p.name, p.source) for p in structured.participants] == [('Alex', 'transcript'), ('Sam', 'roster')]
    assert 'source' in Participant.model_json_schema()['required']

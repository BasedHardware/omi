"""Generate a synthetic snapshot in the exporter format, for tests and UI work.

Everything here is invented: a fake owner uid, made-up conversations about a
fictional garden project, no real names. Shapes follow the exporter's files (see
``seed/snapshot.py``) closely enough to exercise cut, strip and remap rules.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

SYNTHETIC_SOURCE_UID = 'synthOwner0000000000000000a1'

_TOPICS = [
    (
        'Seed order for the community garden',
        'Planned which tomato and bean seeds to order.',
        'Order heirloom tomato seeds',
    ),
    ('Watering rota', 'Agreed who waters the beds on which weekday.', 'Share the watering rota'),
    ('Compost bin repair', 'Discussed fixing the broken compost bin lid.', 'Buy hinges for the compost bin'),
    ('Harvest festival planning', 'Sketched a plan for the autumn harvest festival.', 'Book the hall for the festival'),
]


def _segments(text: str, start: float = 0.0) -> list[dict[str, Any]]:
    words = text.split('. ')
    out = []
    cursor = start
    for index, sentence in enumerate(words):
        out.append(
            {
                'id': f'seg-{index}',
                'text': sentence,
                'speaker': f'SPEAKER_0{index % 2}',
                'speaker_id': index % 2,
                'is_user': index % 2 == 0,
                'person_id': None,
                'start': cursor,
                'end': cursor + 4.0,
            }
        )
        cursor += 4.5
    return out


def make_conversation(
    uid: str, index: int, started: datetime, *, discarded: bool = False, with_hashes: bool = True
) -> dict[str, Any]:
    title, overview, task = _TOPICS[index % len(_TOPICS)]
    finished = started + timedelta(minutes=12)
    row: dict[str, Any] = {
        'id': f'conv-{index:03d}',
        'uid': uid,
        'created_at': started.isoformat(),
        'started_at': started.isoformat(),
        'finished_at': finished.isoformat(),
        'source': 'omi',
        'language': 'en',
        'status': 'completed',
        'discarded': discarded,
        'record_lane_owner': 'batch_live_v1' if index % 2 else None,
        'structured': {
            'title': title,
            'overview': overview,
            'emoji': '🌱',
            'category': 'personal',
            'action_items': [{'description': task, 'completed': False}],
            'events': [],
        },
        'transcript_segments': _segments(
            f'We talked about {title.lower()}. {overview} Next step is to {task.lower()}.'
        ),
        'notes_written_at': (finished + timedelta(seconds=40)).isoformat(),
        'external_data': {'owner_ref': f'users/{uid}/conversations/conv-{index:03d}'},
        'speaker_embedding': {'_bytes': 512},
    }
    if with_hashes:
        row['notes_llm_input_hash'] = 'f' * 64
        row['notes_llm_output_hash'] = 'e' * 64
        row['l1_llm_input_hash'] = 'd' * 64
    return row


def write_synthetic_snapshot(
    root: Path,
    *,
    day: str = '2026-03-14',
    prior_days: int = 2,
    per_day: int = 3,
    uid: str = SYNTHETIC_SOURCE_UID,
) -> Path:
    """Write a snapshot whose window covers ``prior_days`` before ``day`` and ``day`` itself."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    day_start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    conversations, memories, action_items, summaries = [], [], [], []
    index = 0
    for offset in range(-prior_days, 1):
        base = day_start + timedelta(days=offset)
        for slot in range(per_day):
            started = base + timedelta(hours=9 + 3 * slot)
            conv = make_conversation(uid, index, started, discarded=(slot == per_day - 1 and offset == 0))
            conversations.append(conv)
            memories.append(
                {
                    'id': f'mem-{index:03d}',
                    'uid': uid,
                    'content': f'The owner cares about {conv["structured"]["title"].lower()}.',
                    'category': 'interesting',
                    'conversation_id': conv['id'],
                    'created_at': (started + timedelta(minutes=13)).isoformat(),
                    'l1_llm_input_hash': 'c' * 64,
                }
            )
            action_items.append(
                {
                    'id': f'task-{index:03d}',
                    'uid': uid,
                    'description': conv['structured']['action_items'][0]['description'],
                    'completed': False,
                    'conversation_id': conv['id'],
                    'created_at': (started + timedelta(minutes=13)).isoformat(),
                    'due_at': (started + timedelta(days=2)).isoformat(),
                }
            )
            index += 1
        summaries.append(
            {
                'id': f'sum-{(base.date()).isoformat()}',
                'date': base.date().isoformat(),
                'headline': 'A day in the garden',
                'overview': 'Garden planning across several short chats.',
                'created_at': (base + timedelta(hours=22)).isoformat(),
            }
        )
    files: dict[str, Any] = {
        'profile.json': {'uid': uid, 'name': 'Synthetic Owner', 'time_zone': 'UTC', 'language': 'en'},
        'people.json': [
            {'id': 'person-1', 'name': 'Gardener A', 'created_at': (day_start - timedelta(days=30)).isoformat()},
            {'id': 'person-2', 'name': 'Gardener B', 'created_at': (day_start + timedelta(hours=10)).isoformat()},
        ],
        'goals.json': [
            {
                'id': 'goal-1',
                'title': 'Grow tomatoes',
                'current_value': 1,
                'target_value': 5,
                'created_at': (day_start - timedelta(days=10)).isoformat(),
            }
        ],
        'daily_summaries.json': summaries,
        'meetings.json': [],
        'manifest.json': {
            'uid_prefix': uid[:6],
            'window': {
                'start': (day_start - timedelta(days=prior_days)).isoformat(),
                'end': (day_start + timedelta(days=1)).isoformat(),
                'days': prior_days + 1,
            },
            'created_at': (day_start + timedelta(days=1)).isoformat(),
            'source_commit': '0' * 40,
            'counts': {'conversations': len(conversations)},
        },
    }
    for name, value in files.items():
        (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')
    for name, rows in (
        ('conversations.jsonl', conversations),
        ('memories.jsonl', memories),
        ('action_items.jsonl', action_items),
        ('screen_activity.jsonl', []),
    ):
        with (root / name).open('w', encoding='utf-8') as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    return root

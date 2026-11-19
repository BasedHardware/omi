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


_V3_SEEDS = (
    'We should order the heirloom tomato seeds this week. The bean seeds can wait a little. '
    'I will check the catalogue tonight and pick three kinds. Remember the trellis needs fixing first.'
)
_V3_WATER = (
    'Switching topics to the watering rota for the beds. Monday and Thursday are mine. '
    'Gardener B takes the weekend shift. We keep the hose by the shed from now on.'
)
_V3_FESTIVAL = (
    'The harvest festival needs a hall, a band and enough tables for the produce stalls. '
    'We agreed to ask the school about their hall first because it is cheaper and closer to the garden. '
    'The band could be the local folk group that played last spring. Everyone liked them. '
)


def _v3_segments(text: str, *, repeat: int = 1, gap: float = 4.5) -> list[dict[str, Any]]:
    sentences = [s.strip() for s in (text * repeat).split('. ') if s.strip()]
    out, cursor = [], 0.0
    for index, sentence in enumerate(sentences):
        out.append(
            {
                'id': f'v3seg-{index}',
                'text': sentence if sentence.endswith('.') else sentence + '.',
                'speaker': f'SPEAKER_0{index % 2}',
                'speaker_id': index % 2,
                'is_user': index % 2 == 0,
                'person_id': None,
                'start': cursor,
                'end': cursor + 4.0,
            }
        )
        cursor += gap
    return out


def _recording(uid: str, rid: str, started: datetime, segments: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    duration = (segments[-1]['end'] if segments else 60.0) + 5.0
    finished = started + timedelta(seconds=duration)
    row: dict[str, Any] = {
        'id': rid,
        'uid': uid,
        'created_at': started.isoformat(),
        'started_at': started.isoformat(),
        'finished_at': finished.isoformat(),
        'source': 'omi',
        'language': 'en',
        'status': 'completed',
        'discarded': False,
        'recording': True,
        'terminal_no_derived_effects': True,
        'v3_pending': False,
        'v3_pending_since': None,
        'record_lane_owner': 'batch_live_v1',
        'record_sealed_at': finished.timestamp() + 20.0,
        'structured': {},
        'transcript_segments': segments,
        'audio_files': [],
        'claims': [],
        '_create_time': started.isoformat(),
        '_update_time': (finished + timedelta(minutes=10)).isoformat(),
    }
    row.update(extra)
    return row


def _derived(uid: str, cid: str, recordings: list[str], started: datetime, minutes: float, **extra: Any) -> dict:
    words = extra.pop('words', 40)
    hidden = words < 300
    row: dict[str, Any] = {
        'id': cid,
        'uid': uid,
        'v3_derived': True,
        'created_at': started.isoformat(),
        'started_at': started.isoformat(),
        'finished_at': (started + timedelta(minutes=minutes)).isoformat(),
        'source': 'omi',
        'language': 'en',
        'status': 'completed',
        'discarded': False,
        'kind': 'conversation',
        'outline_kind': 'conversation',
        'home_hidden': hidden,
        'home_hidden_reason': 'below_word_minimum' if hidden else 'conversation',
        'tile_state': 'done',
        'title_locked': True,
        'v3_notes_written': not hidden,
        'v3_recording_ids': recordings,
        'transcript_segments': _v3_segments(extra.pop('text', _V3_SEEDS)),
        'structured': {
            'title': extra.pop('title', 'Seed order'),
            'overview': extra.pop('overview', 'Seeds for the garden.'),
            'emoji': '🌱',
            'category': 'personal',
            'sections': [{'heading': 'Plan', 'body_markdown': 'Order seeds.'}],
            'action_items': [],
            'events': [],
        },
        '_create_time': (started + timedelta(minutes=minutes + 6)).isoformat(),
    }
    row.update(extra)
    return row


def synthetic_v3_rows(uid: str, day_start: datetime) -> dict[str, list[dict[str, Any]]]:
    """Recordings of one synthetic v3 day (and one from the evening before) and production's result."""
    nine = day_start + timedelta(hours=9)
    recordings = [
        _recording(uid, 'rec-prev', day_start - timedelta(minutes=20), _v3_segments(_V3_SEEDS)),
        _recording(uid, 'rec-a', nine, _v3_segments(_V3_SEEDS)),
        _recording(uid, 'rec-b', nine + timedelta(minutes=2), _v3_segments(_V3_WATER), v3_manual_end=False),
        _recording(
            uid,
            'rec-c',
            day_start + timedelta(hours=11),
            _v3_segments(_V3_FESTIVAL, repeat=7),
            terminal_family_at=(day_start + timedelta(hours=11, minutes=13)).isoformat(),
        ),
        _recording(uid, 'rec-live', day_start + timedelta(hours=15), [], status='in_progress'),
        _recording(uid, 'rec-gone', day_start + timedelta(hours=16), _v3_segments(_V3_SEEDS), deleted=True),
    ]
    derived = [
        _derived(uid, 'v3-prev', ['rec-prev'], day_start - timedelta(minutes=20), 1.5),
        _derived(uid, 'v3-seeds', ['rec-a', 'rec-b'], nine, 2.0, title='Seed order'),
        _derived(
            uid,
            'v3-water',
            ['rec-b'],
            nine + timedelta(minutes=2),
            1.5,
            title='Watering rota',
            text=_V3_WATER,
            overview='Who waters when.',
        ),
        _derived(
            uid,
            'v3-festival',
            ['rec-c'],
            day_start + timedelta(hours=11),
            12.0,
            title='Harvest festival plans',
            text=_V3_FESTIVAL * 7,
            overview='Hall, band and stalls for the festival.',
            words=320,
        ),
    ]
    return {'recordings': recordings, 'derived': derived}


def write_synthetic_v3_export(root: Path, day_start: datetime, uid: str = SYNTHETIC_SOURCE_UID) -> dict[str, Any]:
    """``<snapshot>/v3/`` in the ``v3/prod_export.py`` format."""
    rows = synthetic_v3_rows(uid, day_start)
    out = Path(root) / 'v3'
    out.mkdir(parents=True, exist_ok=True)
    for name in ('recordings', 'derived'):
        with (out / f'{name}.jsonl').open('w', encoding='utf-8') as stream:
            for row in rows[name]:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    (out / 'other.jsonl').write_text('', encoding='utf-8')
    (out / 'leases.jsonl').write_text('', encoding='utf-8')
    manifest = {'counts': {'recordings': len(rows['recordings']), 'derived': len(rows['derived'])}}
    (out / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return rows


def write_synthetic_snapshot(
    root: Path,
    *,
    day: str = '2026-03-14',
    prior_days: int = 2,
    per_day: int = 3,
    uid: str = SYNTHETIC_SOURCE_UID,
    v3: bool = False,
) -> Path:
    """Write a snapshot whose window covers ``prior_days`` before ``day`` and ``day`` itself.

    ``v3=True`` also writes a ``v3/`` export (recordings and production's v3 conversations) and
    lists the v3 conversations in ``conversations.jsonl``, as the Home reader would.
    """
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
    if v3:
        v3_rows = write_synthetic_v3_export(root, day_start, uid)
        conversations.extend({k: v for k, v in row.items() if not k.startswith('_')} for row in v3_rows['derived'])
        memories.append(
            {
                'id': 'mem-v3-festival',
                'uid': uid,
                'content': 'The owner is organizing the harvest festival.',
                'category': 'interesting',
                'conversation_id': 'v3-festival',
                'created_at': (day_start + timedelta(hours=11, minutes=20)).isoformat(),
            }
        )
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

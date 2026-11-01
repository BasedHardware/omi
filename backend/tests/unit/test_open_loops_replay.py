"""Offline replay: the loop store stays bounded across many synthetic days.

A scripted model (deterministic, derived from each day's own inputs) plays the
daily pass over 70 days: one fresh deliverable loop per day, mentioned for
three days, then silent; one special loop resolved on day 5 with the model
still (wrongly) proposing it for surfacing afterwards.

Proves: open loops never exceed the cap, total documents stay bounded by
expiry + terminal retention (no offline-store growth), and a resolved loop
stops surfacing no matter what the model proposes.
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

import database.conversations as conversations_db
import utils.open_loops.daily as daily
from database.open_loops import get_cards, get_loops
from tests.support.open_loops_store_fake import FakeFirestore
from utils.open_loops import store

UID = 'u1'
START_DAY = date(2026, 8, 1)  # 70 days run through mid-October
DAYS = 70
RESOLVED_ON = 5
MENTION_WINDOW = 3  # days a carried loop keeps earning a status decision


def _now(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 14, 0, tzinfo=timezone.utc)


def _extractions(who: str, what: str):
    return {
        'version': 1,
        'delegated_by_user': [
            {'who': who, 'what': what, 'by_when': None, 'evidence': f'{who} will {what}', 'work_related': True}
        ],
        'commitments_by_others': [],
        'observed_issue_or_blocker': None,
    }


def _row(day: date, index: int, who: str, what: str):
    started = f'{day.isoformat()}T10:00:00+00:00'
    row = {
        'id': f'c-{day.isoformat()}-{index}',
        'created_at': started,
        'started_at': started,
        'finished_at': f'{day.isoformat()}T10:20:00+00:00',
        'structured': {'title': f'Sync {day.isoformat()}', 'overview': f'{who} will {what}.'},
    }
    row.update(
        conversations_db.encode_conversation_for_write(
            UID, {'open_loop_extractions': _extractions(who, what)}, 'standard'
        )
    )
    return row


class ScriptedModel:
    """Deterministic stand-in: reads the day's JSON input, decides like the
    validated prompt would, and keeps proposing the resolved loop forever."""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        user = messages[1]['content']
        payload = json.loads(user.split('INPUT (JSON):\n', 1)[1])
        loops_out, surface_out = [], []
        seen_ids = set()
        for entry in payload['loop_extractions']:
            for delegated in entry['delegated_by_user']:
                loops_out.append(
                    {
                        'loop_id': f'slug-{delegated["who"].lower()}-{len(seen_ids)}',
                        'kind': 'owed_to_user',
                        'who': delegated['who'],
                        'what': delegated['what'],
                        'status': 'opened',
                        'due': None,
                        'work_related': True,
                        'evidence': delegated['evidence'],
                        'source_conversation_ids': [entry['conversation_id']],
                        'from_task_id': None,
                    }
                )
                seen_ids.add(entry['conversation_id'])
        for carried in payload['carried_loops']:
            age = carried.get('age_days') or 0
            if age > MENTION_WINDOW:
                continue  # no signal: the model stays silent
            if 'resolve-' in str(carried.get('what')) and age >= 1:
                loops_out.append(
                    {
                        'loop_id': carried['loop_id'],
                        'kind': carried['kind'],
                        'who': carried['who'],
                        'what': carried['what'],
                        'status': 'resolved',
                        'due': None,
                        'work_related': True,
                        'evidence': 'delivered this morning',
                        'source_conversation_ids': [],
                        'from_task_id': None,
                    }
                )
                continue
            if age <= MENTION_WINDOW:
                loops_out.append(
                    {
                        'loop_id': carried['loop_id'],
                        'kind': carried['kind'],
                        'who': carried['who'],
                        'what': carried['what'],
                        'status': 'progressing',
                        'due': None,
                        'work_related': True,
                        'evidence': 'still in progress',
                        'source_conversation_ids': [],
                        'from_task_id': None,
                    }
                )
        # propose every decided loop for surfacing, resolved included (on purpose)
        for loop in loops_out:
            surface_out.append({'loop_id': loop['loop_id'], 'why_now': 'replay', 'value': 4})
        return type('Response', (), {'content': json.dumps({'loops': loops_out, 'surface': surface_out})})()


def test_replay_stays_bounded_and_resolved_loops_stop_surfacing(monkeypatch):
    fake = FakeFirestore()
    rows_by_day = {}

    def conversations(uid, *, start_date=None, end_date=None, **kwargs):
        for end, rows in rows_by_day.items():
            if end_date == end:
                return list(rows)
        return []

    monkeypatch.setattr(daily.conversations_db, 'get_conversations', conversations)
    monkeypatch.setattr(daily.action_items_db, 'get_action_items', lambda uid, **kwargs: [])
    monkeypatch.setattr(daily.daily_summaries_db, 'get_daily_summary_by_date', lambda uid, date_str: None)

    model = ScriptedModel()
    max_open = max_total = 0
    surfaced_after_resolution = []

    for offset in range(DAYS):
        day = START_DAY + timedelta(days=offset)
        what = f'deliverable number {offset}'
        rows = [_row(day, 0, 'Maya', what)]
        if offset == RESOLVED_ON:
            rows.append(_row(day, 1, 'Ann', f'resolve-{RESOLVED_ON} target'))
        end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        rows_by_day[end] = rows

        outcome = daily.run_daily_pass(
            UID,
            date_str=day.isoformat(),
            start_utc=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            end_utc=end,
            tz='UTC',
            now=_now(day),
            firestore_client=fake,
            llm=model,
        )
        assert outcome == daily.RAN, f'day {day} declined: {outcome}'

        loops = get_loops(UID, firestore_client=fake)
        open_count = sum(1 for loop in loops if store.is_open(loop))
        max_open = max(max_open, open_count)
        max_total = max(max_total, len(loops))

        cards = get_cards(UID, day.isoformat(), firestore_client=fake) or []
        if offset > RESOLVED_ON:
            resolved_ids = {
                loop['id'] for loop in loops if loop['status'] == 'resolved' and 'resolve' in str(loop.get('what'))
            }
            surfaced_after_resolution.extend(card['loop_id'] for card in cards if card['loop_id'] in resolved_ids)

    # Bounded store: opens never near the cap, documents bounded by expiry + retention
    assert max_open <= store.OPEN_LOOP_STORE_CAP
    assert max_total <= 2 * max(store.EXPIRY_DAYS_BY_KIND.values()) + store.TERMINAL_RETENTION_DAYS + 5
    # A loop a day for 70 days would be 70 docs unbounded; the sweep keeps it far below
    assert max_total < DAYS
    # The resolved loop is closed and never surfaces again, however often proposed
    assert surfaced_after_resolution == []
    all_loops = get_loops(UID, firestore_client=fake)
    resolved = [loop for loop in all_loops if 'resolve' in str(loop.get('what'))]
    assert all(loop['status'] == 'resolved' for loop in resolved)
    assert model.calls == DAYS  # exactly one model call per day

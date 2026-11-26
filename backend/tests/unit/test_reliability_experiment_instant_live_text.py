"""Experiment ``instant_live_text``: speech that misses its minute's grouping run is grouped within a slot.

``triggers.enqueue`` names the grouping task by owner and wall-clock minute, and Cloud Tasks refuses a
name it has seen for about an hour. A speech write in a minute whose task already ran (or is scheduled
for later in the minute) is therefore dropped as a duplicate and waits for the owner's next scheduled
wake. Off (the default) that stays exactly so. On, the refused write-driven wake enqueues one follow-up
task at the end of its 15 s slot. The experiment also turns on the open conversation's device stamp
(``v3_capture_device_id``), which the app reads to show its own speech recognition.
"""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from config import reliability_experiments
from models.conversation import ConversationsLiveResponse
from routers import conversations as routes
from utils.conversations.v3 import capture_device, triggers
from tests.unit.test_conversations_v3_claim_growth import strict, owners_import, path  # noqa: F401
from tests.unit.test_conversations_v3_live_passes import T0, derived, put_recording, reconcile_at, speech, timing

EXPERIMENT = 'instant_live_text'
PHONE = 'ios_06b76a44'
# 12:00:20 UTC: second 20 of its minute, inside the slot that ends at second 30.
NOW = datetime(2026, 11, 25, 12, 0, 20, tzinfo=timezone.utc)
MINUTE = int(NOW.timestamp()) // 60
SLOT_END = int(NOW.timestamp()) + 10


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)


class Queue:
    """Cloud Tasks' naming rule: a name is created once, then refused."""

    def __init__(self, taken=()):
        self.names = set(taken)
        self.created = []

    def enqueue(self, queue, url, task_id, payload, *, schedule_at=None, **_):
        if task_id in self.names:
            return False
        self.names.add(task_id)
        self.created.append((task_id, schedule_at, url, payload))
        return True


@pytest.fixture
def queue(monkeypatch):
    fake = Queue()
    monkeypatch.setattr(triggers, 'enqueue_named_task', fake.enqueue)
    monkeypatch.setattr(triggers, 'task_base', lambda: 'https://tasks.test')

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(triggers, 'datetime', Clock)
    return fake


def minute_name(uid='u'):
    return f'conversations-v3-{hashlib.sha256(uid.encode()).hexdigest()[:32]}-{MINUTE}'


def test_registered():
    assert EXPERIMENT in reliability_experiments.EXPERIMENTS


def test_any_enabled_reads_each_name(monkeypatch):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    assert not reliability_experiments.any_enabled('end_button_by_device', EXPERIMENT)
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    assert reliability_experiments.any_enabled('end_button_by_device', EXPERIMENT)
    with pytest.raises(KeyError):
        reliability_experiments.any_enabled(EXPERIMENT, 'not_registered')


def test_off_a_refused_wake_enqueues_nothing_more(off, queue):
    triggers.enqueue('u')
    triggers.enqueue('u')
    assert [name for name, *_ in queue.created] == [minute_name()]


def test_on_the_first_wake_of_a_minute_is_today_s_task_alone(on, queue):
    triggers.enqueue('u')
    assert queue.created == [
        (minute_name(), int(NOW.timestamp()), 'https://tasks.test/v1/conversations-v3/reconcile', {'uid': 'u'})
    ]


def test_on_a_refused_wake_gets_one_follow_up_at_the_end_of_its_slot(on, queue):
    triggers.enqueue('u')
    triggers.enqueue('u')
    # A third write of the same slot shares the follow-up: it starts after all of them.
    triggers.enqueue('u')
    assert [(name, at) for name, at, *_ in queue.created] == [
        (minute_name(), int(NOW.timestamp())),
        (f'{minute_name()}-late-{SLOT_END}', SLOT_END),
    ]
    assert SLOT_END % triggers.FOLLOW_UP_SLOT_SECONDS == 0 and 0 < SLOT_END - int(NOW.timestamp()) <= 15


def test_on_a_write_in_a_later_slot_gets_its_own_follow_up(on, queue, monkeypatch):
    triggers.enqueue('u')
    triggers.enqueue('u')
    later = NOW + timedelta(seconds=15)

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return later

    monkeypatch.setattr(triggers, 'datetime', Later)
    triggers.enqueue('u')
    assert [at for _, at, *_ in queue.created] == [int(NOW.timestamp()), SLOT_END, SLOT_END + 15]


def test_on_the_builder_s_scheduled_wakes_and_user_ends_never_chain(on, queue):
    scheduled = NOW + timedelta(seconds=5)
    triggers.enqueue('u', at=scheduled)
    # The same minute name again, as a scheduled wake: refused, and left at that.
    triggers.enqueue('u', at=scheduled)
    triggers.enqueue('u', manual_end_id='cut')
    triggers.enqueue('u', manual_end_id='cut')
    names = [name for name, *_ in queue.created]
    assert len(names) == 2 and not any('-late-' in name for name in names)


def test_on_another_owner_s_minute_is_not_followed_up(on, queue):
    triggers.enqueue('u')
    triggers.enqueue('other')
    assert [name for name, *_ in queue.created] == [minute_name(), minute_name('other')]


def test_enqueue_named_task_says_whether_it_created_the_task(monkeypatch):
    from google.api_core.exceptions import AlreadyExists
    from utils import cloud_tasks

    class Client:
        def __init__(self):
            self.seen = set()

        def queue_path(self, *parts):
            return '/'.join(parts)

        def task_path(self, *parts):
            return '/'.join(parts)

        def create_task(self, *, parent, task):
            if task.name in self.seen:
                raise AlreadyExists('duplicate')
            self.seen.add(task.name)

    client = Client()
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'p')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'l')
    monkeypatch.setattr(cloud_tasks, '_get_tasks_client', lambda: client)
    monkeypatch.setattr(cloud_tasks, '_invoker_sa', lambda: 'sa@test')
    monkeypatch.setattr(cloud_tasks, '_oidc_audience', lambda: 'https://tasks.test')
    assert cloud_tasks.enqueue_named_task('q', 'https://tasks.test/x', 'name', {}) is True
    assert cloud_tasks.enqueue_named_task('q', 'https://tasks.test/x', 'name', {}) is False


@pytest.mark.asyncio
async def test_on_the_open_conversation_names_the_device_behind_its_latest_speech(on, strict, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_LIVE_TITLE', 'off')
    timing(monkeypatch, 900, 900)
    segments = speech(4)
    landed = T0 + timedelta(seconds=segments[-1]['end'] + 30)
    put_recording(strict, segments, status='in_progress', landed=landed)
    strict.rows[path('r')]['client_device_id'] = PHONE
    assert await reconcile_at(strict, monkeypatch, landed) == 'committed'
    (row,) = derived(strict)
    assert row['tile_state'] == 'live' and row[capture_device.FIELD] == PHONE


def serve(monkeypatch, **extra):
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    row = {
        'id': 'open',
        'status': 'in_progress',
        'created_at': now,
        'started_at': now,
        'finished_at': now,
        'v3_derived': True,
        'tile_state': 'live',
        'structured': {'title': 'Plan', 'emoji': '🌳'},
        'v3_recording_ids': ['r'],
        **extra,
    }
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(routes.conversations_v3_live, 'recent_windows', lambda uid, **kw: ([row], 1))
    monkeypatch.setattr(routes.v3_client_capability, 'note_capable', lambda uid: None)
    result = routes.get_live_conversation('u', 'store')
    return ConversationsLiveResponse(**result).model_dump(exclude_unset=True)['conversation']


def test_on_the_live_read_serves_the_device(on, monkeypatch):
    assert serve(monkeypatch, **{capture_device.FIELD: PHONE})[capture_device.FIELD] == PHONE


def test_off_the_live_read_serves_no_device(off, monkeypatch):
    assert capture_device.FIELD not in serve(monkeypatch, **{capture_device.FIELD: PHONE})

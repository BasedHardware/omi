"""Synthetic v3 switch, read boundaries, capture and released-wire contracts."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException

from config import conversations_v3 as switch
from database import conversations as db
from routers import conversations as routes, episodes
from utils.conversations.v3 import service, audio, triggers
from utils.conversations.processing_trigger import ProcessingTrigger


def test_manual_end_wake_survives_a_completed_live_task_in_same_minute(monkeypatch):
    tasks = {}
    calls = []
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://test.invalid')
    monkeypatch.setattr(triggers.store, 'mark_pending', lambda *a, **kw: True)

    def enqueue(queue, url, task_id, payload, **kwargs):
        calls.append(task_id)
        tasks.setdefault(task_id, (payload, kwargs))

    monkeypatch.setattr(triggers, 'enqueue_named_task', enqueue)
    fixed = datetime(2026, 11, 16, 12, 0, 10, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(triggers, 'datetime', Clock)
    triggers.changed('owner', 'recording')  # Live task runs and Cloud Tasks retains its name.
    triggers.changed('owner', 'recording', manual_end=True)
    triggers.changed('owner', 'recording', manual_end=True)  # Delivery retry stays idempotent.
    assert len(tasks) == 2
    assert calls[0] != calls[1] == calls[2]
    assert all(kw['schedule_at'] == int(fixed.timestamp()) for _, kw in tasks.values())


def test_native_ready_name_survives_live_tombstone_and_retains_same_revision(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://test.invalid')
    from google.api_core.exceptions import AlreadyExists
    from utils import cloud_tasks

    class FakeCloudTasks:
        tasks = {}

        @staticmethod
        def queue_path(project, location, queue):
            return queue

        @staticmethod
        def task_path(project, location, queue, task_id):
            return queue + '/' + task_id

        def create_task(self, *, parent, task):
            if task.name in self.tasks:
                raise AlreadyExists('completed name retained')
            self.tasks[task.name] = task

    fake = FakeCloudTasks()
    monkeypatch.setattr(cloud_tasks, '_get_tasks_client', lambda: fake)
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'synthetic')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'synthetic')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'synthetic@example.invalid')
    start = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    triggers.enqueue('owner', at=start)
    triggers.enqueue('owner', at=start, native_manual_ready=('recording', 7))
    triggers.enqueue('owner', at=start + timedelta(minutes=1), native_manual_ready=('recording', 7))
    triggers.enqueue('owner', at=start, native_manual_ready=('recording', 8))
    triggers.enqueue('owner', at=start, native_manual_ready=('recording', 7), native_rearm=True)
    triggers.enqueue('owner', at=start + timedelta(minutes=1), native_manual_ready=('recording', 7), native_rearm=True)
    assert len(fake.tasks) == 4
    assert sum('-native-rearm-' in name for name in fake.tasks) == 1
    ready = [task for task in fake.tasks.values() if b'native_manual_ready' in task.http_request.body]
    assert len(ready) == 3


@pytest.mark.asyncio
async def test_busy_native_ready_leaves_cloud_task_retryable(monkeypatch):
    from starlette.requests import Request

    from routers import conversations_v3_tasks

    lanes = []

    async def busy(uid, *, background=False):
        lanes.append(background)
        return 'busy'

    monkeypatch.setattr(service, 'reconcile', busy)
    http_request = Request({'type': 'http', 'headers': []})
    request = conversations_v3_tasks.ReconcileRequest(uid='owner')
    assert await conversations_v3_tasks.reconcile(request, http_request) == {'outcome': 'busy'}
    request = conversations_v3_tasks.ReconcileRequest(uid='owner', trigger='native_manual_ready')
    retry = await conversations_v3_tasks.reconcile(request, http_request)
    assert retry.status_code == 409
    assert json.loads(retry.body) == {'status': 'retry', 'reason': 'locked'}
    assert lanes == [True, False]


def test_scheduled_wake_rounds_up_and_coalesces_in_delivery_minute(monkeypatch):
    tasks = {}
    attempts = []
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://test.invalid')

    def enqueue(queue, url, name, payload, *, schedule_at):
        attempts.append((name, schedule_at))
        tasks.setdefault(name, schedule_at)

    monkeypatch.setattr(triggers, 'enqueue_named_task', enqueue)
    start = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    for seconds in (5, 5.5, 60, 59.5):
        triggers.enqueue('owner', at=start + timedelta(seconds=seconds))

    epoch = int(start.timestamp())
    assert [when - epoch for _, when in attempts] == [5, 6, 60, 60]
    assert [name.rsplit('-', 1)[-1] for name, when in attempts] == [str(when // 60) for _, when in attempts]
    assert len(tasks) == 2
    assert attempts[2] == attempts[3]


@pytest.mark.parametrize(
    'stage,seen,capable,cohort,expected',
    [
        ('beta', False, False, False, False),
        ('beta', True, True, False, True),
        # A stale episodes marker from a pre-v3 store build is not v3 capability.
        ('beta', True, False, False, False),
        # The capability marker alone does not widen beta past TestFlight.
        ('beta', False, True, False, False),
        ('beta', False, False, True, True),
        ('cohort', True, True, False, False),
        ('cohort', False, False, True, True),
        # all admits any owner with a v3-capable app, never an owner whose apps all predate v3.
        ('all', False, False, False, False),
        ('all', False, True, False, True),
        ('all', True, False, False, False),
        ('all', False, False, True, True),
        ('invalid', True, True, False, False),
    ],
)
def test_switch_is_per_owner_not_device(monkeypatch, stage, seen, capable, cohort, expected):
    monkeypatch.setenv('CONVERSATIONS_V3_STAGE', stage)
    monkeypatch.delenv('CONVERSATIONS_V3', raising=False)
    monkeypatch.setattr(switch.client_gate, 'client_seen_cached', lambda uid: seen)
    monkeypatch.setattr(switch.client_capability, 'capable_cached', lambda uid: capable)
    monkeypatch.setattr(switch, 'in_rollout_cohort', lambda uid, key: cohort and key == 'conversations-v3')
    assert switch.conversations_v3_enabled('synthetic') is expected
    monkeypatch.setenv('CONVERSATIONS_V3', 'off')
    assert switch.conversations_v3_enabled('synthetic') is False


class _Holdout:
    """Synthetic holdout membership behind the real admission predicates; stage ``all``, capable owner."""

    def __init__(self, monkeypatch):
        self.member, self.unavailable, self.reads, self.fallbacks = False, False, [], []
        monkeypatch.setenv('CONVERSATIONS_V3_STAGE', 'all')
        monkeypatch.delenv('CONVERSATIONS_V3', raising=False)
        monkeypatch.delenv('CONVERSATIONS_V3_HOLDOUT', raising=False)
        monkeypatch.setattr(switch.client_gate, 'client_seen_cached', lambda uid: False)
        monkeypatch.setattr(switch.client_capability, 'capable_cached', lambda uid: True)
        monkeypatch.setattr(switch, 'in_rollout_cohort', self._membership)
        monkeypatch.setattr(switch, 'record_fallback', lambda **kw: self.fallbacks.append(kw))
        for module in (triggers, routes):
            monkeypatch.setattr(module, 'conversations_v3_enabled', switch.conversations_v3_enabled)
            monkeypatch.setattr(module, 'v3_intake_held_out', switch.v3_intake_held_out)

    def _membership(self, uid, key):
        self.reads.append(key)
        if key != 'conversations-v3-holdout':
            return False
        if self.unavailable:
            raise switch.RolloutCohortUnavailable('synthetic outage')
        return self.member

    def new_row(self):
        row = {'source': 'omi', 'data_protection_level': 'standard'}
        triggers.mark_new('synthetic', row)
        return row


def _serve_live(monkeypatch, window):
    monkeypatch.setattr(routes.client_gate, 'note_client_seen', lambda uid: None)
    monkeypatch.setattr(routes.v3_client_capability, 'note_capable', lambda uid: None)
    monkeypatch.setattr(routes.reliability_experiments, 'any_enabled', lambda *a: False)
    monkeypatch.setattr(
        routes.conversations_v3_live,
        'live_window_lookup',
        lambda uid, **kw: (window.get('row'), window.get('complete', True)),
    )


def test_holdout_keeps_stage_admission_for_existing_v3_work(monkeypatch):
    holdout = _Holdout(monkeypatch)
    holdout.member = True
    for stage in ('all', 'beta', 'cohort'):
        monkeypatch.setenv('CONVERSATIONS_V3_STAGE', stage)
        monkeypatch.setattr(switch.client_gate, 'client_seen_cached', lambda uid: True)
        monkeypatch.setattr(switch, 'in_rollout_cohort', lambda uid, key: True)
        # Finish, episodes and builders keep reaching the owner's stored v3 work.
        assert switch.conversations_v3_enabled('synthetic') is True
        assert switch.v3_intake_held_out('synthetic') is True


def test_intake_with_known_membership(monkeypatch):
    holdout = _Holdout(monkeypatch)
    assert holdout.new_row()['recording'] is True
    holdout.member = True
    row = holdout.new_row()
    assert 'recording' not in row and 'v3_pending' not in row
    assert holdout.fallbacks == [] and set(holdout.reads) == {'conversations-v3-holdout'}
    # A rotation successor continues the capture in flight: still v3 for a held-out owner.
    successor = {'source': 'omi', 'data_protection_level': 'standard'}
    triggers.mark_new('synthetic', successor, continuation=True)
    assert successor['recording'] is True


def test_intake_with_unavailable_membership_admits_and_records_fallback(monkeypatch):
    holdout = _Holdout(monkeypatch)
    holdout.member = holdout.unavailable = True
    assert holdout.new_row()['recording'] is True
    assert holdout.fallbacks == [
        {
            'component': 'feature_flags',
            'from_mode': 'v3_holdout',
            'to_mode': 'admitted',
            'reason': 'unavailable',
            'outcome': 'degraded',
            'log': switch.logger,
        }
    ]


@pytest.mark.parametrize('value', ['off', 'false', '0', 'no'])
def test_holdout_env_off_ignores_cohort_and_skips_read(monkeypatch, value):
    holdout = _Holdout(monkeypatch)
    holdout.member = True
    monkeypatch.setenv('CONVERSATIONS_V3_HOLDOUT', value)
    assert holdout.new_row()['recording'] is True
    assert holdout.reads == []


def test_kill_switch_wins_without_a_holdout_read(monkeypatch):
    holdout = _Holdout(monkeypatch)
    monkeypatch.setenv('CONVERSATIONS_V3', 'off')
    assert 'recording' not in holdout.new_row()
    assert holdout.reads == []


def test_holdout_added_mid_capture_serves_the_active_window_then_legacy(monkeypatch):
    holdout = _Holdout(monkeypatch)
    window = {'row': None}
    _serve_live(monkeypatch, window)
    capturing = holdout.new_row()
    window['row'] = {'id': 'open', 'status': 'in_progress', 'tile_state': 'live', 'structured': {'title': 't'}}
    holdout.member = True
    # The capture already admitted keeps its stored marker; only the next generation is legacy.
    assert capturing['recording'] is True and 'recording' not in holdout.new_row()
    reads = len(holdout.reads)
    live = routes.get_live_conversation('synthetic', 'store')
    assert live['v3'] is True and live['conversation']['id'] == 'open'
    assert len(holdout.reads) == reads  # An active window is served without the membership read.
    window['row'] = None
    assert routes.get_live_conversation('synthetic', 'store') == {'v3': False, 'conversation': None}


def test_holdout_live_keeps_v3_when_the_window_lookup_is_capped(monkeypatch):
    holdout = _Holdout(monkeypatch)
    holdout.member = True
    window = {'row': None, 'complete': False}
    _serve_live(monkeypatch, window)
    fallbacks = []
    monkeypatch.setattr(routes, 'record_fallback', lambda **kw: fallbacks.append(kw))
    # A capped lookup has not proven there is no window: fail toward the existing one and count it.
    assert routes.get_live_conversation('synthetic', 'store') == {'v3': True, 'conversation': None}
    assert [(f['from_mode'], f['to_mode'], f['reason']) for f in fallbacks] == [('v3_holdout', 'v3_live', 'lookup_cap')]
    from utils.observability.fallback import bucket_reason

    assert bucket_reason(fallbacks[0]['reason']) == 'lookup_cap'  # Emitted as itself, not relabelled 'other'.
    window['complete'] = True
    assert routes.get_live_conversation('synthetic', 'store') == {'v3': False, 'conversation': None}
    assert len(fallbacks) == 1


def test_holdout_removed_mid_capture_readmits_the_next_row(monkeypatch):
    holdout = _Holdout(monkeypatch)
    window = {'row': None}
    _serve_live(monkeypatch, window)
    holdout.member = True
    capturing = holdout.new_row()
    assert routes.get_live_conversation('synthetic', 'store') == {'v3': False, 'conversation': None}
    holdout.member = False
    # The legacy capture in flight stays legacy; the next new row is v3 again.
    assert 'recording' not in capturing and holdout.new_row()['recording'] is True
    assert routes.get_live_conversation('synthetic', 'store') == {'v3': True, 'conversation': None}


def test_existing_v3_work_drains_for_a_held_out_owner(monkeypatch):
    from utils.conversations.v3 import finish, manual_cuts

    holdout = _Holdout(monkeypatch)
    holdout.member = True
    window = {'id': 'open', 'status': 'in_progress', 'v3_derived': True}
    acknowledged = []
    monkeypatch.setattr(finish, 'finish_no_pointer_enabled', lambda: True)
    monkeypatch.setattr(finish, 'conversations_v3_enabled', switch.conversations_v3_enabled)
    monkeypatch.setattr(finish.conversations_v3_live, 'live_window', lambda uid, **kw: window)
    monkeypatch.setattr(finish.conversations_v3_live, 'request_finish', lambda uid, wid, **kw: ('cut', 'rec'))
    monkeypatch.setattr(finish, '_acknowledge', lambda *a: acknowledged.append(a) or 'answer')
    assert finish.finish_live_window('synthetic') == 'answer'
    assert acknowledged == [('synthetic', window, 'cut', 'rec')]
    # End cuts follow new intake: a held-out owner gets experiment-off End handling.
    monkeypatch.setattr(manual_cuts, 'enabled', lambda uid: True)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', switch.conversations_v3_enabled)
    monkeypatch.setattr(manual_cuts, 'v3_intake_held_out', switch.v3_intake_held_out)
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', lambda *a: pytest.fail('held-out owner recorded a cut'))
    assert manual_cuts.record_end('synthetic') is None


class _MixedFinish:
    """Finish endpoint while a held-out owner's old v3 window coexists with a new legacy in-progress row."""

    def __init__(self, monkeypatch, *, window_live=True, member=True, unavailable=False):
        from types import SimpleNamespace

        from utils.conversations.v3 import finish

        holdout = _Holdout(monkeypatch)
        holdout.member, holdout.unavailable = member, unavailable
        self.legacy = {'id': 'legacy-row', 'status': 'in_progress', 'source': 'omi'}
        self.finished, self.finalized, self.woken, self.named = [], [], [], []
        window = {'id': 'old-window', 'status': 'in_progress', 'v3_derived': True}
        monkeypatch.setattr(routes, 'finish_live_window', finish.finish_live_window)
        monkeypatch.setattr(routes, 'retrieve_in_progress_conversation', lambda uid: self.legacy)
        monkeypatch.setattr(routes, 'is_listen_finalization_dispatch_enabled', lambda: True)
        monkeypatch.setattr(routes.byok, 'has_byok_keys', lambda: False)
        monkeypatch.setattr(routes, 'finalize_conversation', lambda cid, **kw: self.finalized.append(cid) or 'legacy')
        monkeypatch.setattr(routes.v3_end_answer, 'answer', lambda uid, cut_id, baseline, *a, **kw: baseline)
        monkeypatch.setattr(routes.v3_manual_cuts, 'wake', lambda uid, cut_id: self.woken.append(cut_id))
        monkeypatch.setattr(finish, 'finish_no_pointer_enabled', lambda: True)
        monkeypatch.setattr(finish, 'conversations_v3_enabled', switch.conversations_v3_enabled)
        live_db = finish.conversations_v3_live
        monkeypatch.setattr(live_db, 'live_window_by_id', lambda uid, wid, **kw: window if window_live else None)
        monkeypatch.setattr(
            live_db, 'request_finish', lambda uid, wid, **kw: self.finished.append(wid) or ('cut', 'rec')
        )
        monkeypatch.setattr(
            live_db,
            'request_named_finish',
            lambda uid, wid, **kw: self.named.append((wid, kw.get('strict'))) or (None, None, ''),
        )
        monkeypatch.setattr(
            finish,
            '_acknowledge',
            lambda uid, row, outcome, rid: SimpleNamespace(
                conversation=SimpleNamespace(id=row['id'], tile_state='writing')
            ),
        )
        monkeypatch.setattr(
            live_db, 'live_window', lambda *a, **kw: pytest.fail('a named Finish fell back to another window')
        )

    def finish(self, named):
        from fastapi import Response
        from models.conversation import ProcessConversationRequest

        request = ProcessConversationRequest(live_conversation_id=named) if named else None
        return routes.process_in_progress_conversation(request, 'synthetic', None, response=Response())


def test_named_v3_finish_closes_its_window_while_a_legacy_row_is_in_progress(monkeypatch):
    mixed = _MixedFinish(monkeypatch)
    answer = mixed.finish('old-window')
    assert answer.conversation.id == 'old-window' and mixed.finished == ['old-window']
    # The legacy row stays in progress: not finalized, not changed.
    assert mixed.finalized == [] and mixed.legacy == {'id': 'legacy-row', 'status': 'in_progress', 'source': 'omi'}
    assert mixed.woken == []  # The window cut answered as writing; the baseline path woke the builder.


def test_unnamed_finish_beside_an_old_v3_window_still_finalizes_the_legacy_row(monkeypatch):
    mixed = _MixedFinish(monkeypatch)
    assert mixed.finish(None) == 'legacy'
    assert mixed.finalized == ['legacy-row'] and mixed.finished == []
    # Naming the legacy row itself is the legacy Finish too.
    assert mixed.finish('legacy-row') == 'legacy'
    assert mixed.finalized == ['legacy-row', 'legacy-row'] and mixed.finished == []


def test_named_finish_miss_falls_back_to_the_legacy_finish(monkeypatch):
    mixed = _MixedFinish(monkeypatch, window_live=False)
    assert mixed.finish('old-window') == 'legacy'
    assert mixed.named == [('old-window', True)] and mixed.finalized == ['legacy-row'] and mixed.finished == []


@pytest.mark.parametrize('member,unavailable', [(False, False), (True, True)])
def test_named_finish_override_is_a_no_op_unless_holdout_is_confirmed(monkeypatch, member, unavailable):
    from utils.conversations.v3 import finish

    mixed = _MixedFinish(monkeypatch, member=member, unavailable=unavailable)
    monkeypatch.setattr(
        finish.conversations_v3_live, 'live_window_by_id', lambda *a, **kw: pytest.fail('non-member read the window')
    )
    # A non-member, or a membership read that failed, keeps today's Finish: the legacy row is finalized.
    assert mixed.finish('old-window') == 'legacy'
    assert mixed.finalized == ['legacy-row'] and mixed.finished == [] and mixed.named == []


def test_named_finish_beside_a_v3_recording_in_progress_keeps_today_path(monkeypatch):
    mixed = _MixedFinish(monkeypatch)
    mixed.legacy = {'id': 'session-recording', 'status': 'in_progress', 'recording': True}
    assert mixed.finish('old-window') == 'legacy'
    assert mixed.finalized == ['session-recording'] and mixed.finished == []


def test_held_out_owner_reads_legacy_home_with_v3_cards_and_held_pieces(monkeypatch):
    from tests.unit.test_home_held_sync_piece import piece

    holdout = _Holdout(monkeypatch)
    calls = []
    monkeypatch.setattr(
        routes.conversations_db, 'get_conversations_without_photos', lambda *a, **kw: calls.append(kw) or []
    )
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from utils.other import endpoints as auth

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'synthetic'
    with TestClient(app) as client:
        assert (
            client.get('/v1/conversations', headers={routes.list_page_headers.HOME_MODE_HEADER: 'auto'}).status_code
            == 200
        )
        holdout.member = True
        legacy = client.get('/v1/conversations', headers={routes.list_page_headers.HOME_MODE_HEADER: 'auto'})
    assert [kw['show_held'] for kw in calls] == [False, True]
    assert legacy.headers.get(routes.list_page_headers.HOME_MODE_HEADER) == 'legacy'
    # Legacy Home shows the owner's existing v3 card next to a new legacy piece held for notes.
    card = {'id': 'card', 'status': 'completed', 'v3_derived': True, 'structured': {'title': 't'}}
    for show_held, expected in ((True, True), (False, False)):
        kwargs = dict(presentation=True, hide_home=True, show_held=show_held)
        assert db.is_visible_conversation(card, **kwargs) is True
        assert db.is_visible_conversation(piece(), **kwargs) is expected


def test_runtime_resolver_reports_unknown_holdout_membership(monkeypatch):
    from utils import rollout_cohorts as runtime

    monkeypatch.setattr(runtime._cache, 'get', lambda uid: None)
    with pytest.raises(runtime.policy.RolloutCohortUnavailable):
        runtime._in_rollout_cohort('synthetic', 'conversations-v3-holdout')
    # Other cohorts keep reading an unknown membership as a plain miss.
    assert runtime._in_rollout_cohort('synthetic', 'conversations-v3') is False
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setattr(runtime._cache, 'get', lambda uid: {'prod': {'conversations-v3-holdout': True}})
    assert runtime._in_rollout_cohort('synthetic', 'conversations-v3-holdout') is True


def test_rollout_cohort_script_accepts_holdout_cohort(tmp_path, capsys):
    from scripts import rollout_cohort

    uid_file = tmp_path / 'uid'
    uid_file.write_text('synthetic-owner')
    argv = ['--uid-file', str(uid_file), '--cohort', 'conversations-v3-holdout', '--project', 'based-hardware-dev']
    assert rollout_cohort.main(argv + ['--environment', 'dev', '--add', '--dry-run']) == 0
    assert 'cohorts=conversations-v3-holdout' in capsys.readouterr().out


@pytest.mark.parametrize('channel,expected', [('beta', ['seen', 'capable', 'check']), ('store', ['capable', 'check'])])
def test_live_call_marks_capability_before_v3_check(monkeypatch, channel, expected):
    calls = []
    monkeypatch.setattr(routes.client_gate, 'note_client_seen', lambda uid: calls.append('seen'))
    monkeypatch.setattr(routes.v3_client_capability, 'note_capable', lambda uid: calls.append('capable'))
    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: calls.append('check') or False)
    assert routes.get_live_conversation('synthetic', channel) == {'v3': False, 'conversation': None}
    assert calls == expected


class _FakeRedis:
    def __init__(self):
        self.store, self.sets, self.fail = {}, [], False

    def set(self, key, value, ex=None):
        if self.fail:
            raise ConnectionError('redis down')
        self.sets.append((key, ex))
        self.store[key] = value

    def exists(self, key):
        if self.fail:
            raise ConnectionError('redis down')
        return 1 if key in self.store else 0


def test_capability_marker_refreshes_hourly_and_fails_closed(monkeypatch):
    from database import redis_db
    from utils.conversations.v3 import client_capability as capability

    fake = _FakeRedis()
    monkeypatch.setattr(redis_db, 'r', fake)
    capability.reset_for_tests()
    assert capability.capable_cached('u', now=0) is False
    capability.note_capable('u', now=10)
    # The noting process admits at once, despite its cached miss.
    assert capability.capable_cached('u', now=11) is True
    capability.note_capable('u', now=20)
    assert fake.sets == [('conversations_v3:client_capable:u', capability.TTL_SECONDS)]
    capability.note_capable('u', now=10 + capability.REFRESH_SECONDS)
    assert len(fake.sets) == 2
    # Another process (empty cache) reads the shared marker.
    capability.reset_for_tests()
    assert capability.capable_cached('u', now=0) is True
    capability.reset_for_tests()
    fake.fail = True
    capability.note_capable('v', now=0)  # never raises
    # A failed write does not make this process answer v3 for an owner the shared marker lacks.
    assert capability.capable_cached('v', now=1) is False
    capability.reset_for_tests()
    assert capability.capable_cached('u', now=0) is False  # read error fails closed
    fake.fail = False
    assert capability.capable_cached('u', now=1) is False  # and the miss is cached briefly
    capability.note_capable('v', now=2)  # a failed write is retried, not memoized
    assert fake.sets[-1][0] == 'conversations_v3:client_capable:v'
    capability.reset_for_tests()


@pytest.mark.parametrize('include', [False, True])
def test_visibility_predicate_requires_recording_opt_in(include):
    row = {'recording': True, 'status': 'completed', 'discarded': False}
    assert db.is_visible_conversation(row, include_recordings=include) is include
    assert db.is_visible_conversation({**row, 'recording': False, 'home_hidden': True})


@pytest.mark.parametrize('allow', [False, True])
def test_by_id_recording_opt_in(monkeypatch, allow):
    monkeypatch.setattr(db, 'get_conversation', lambda *a, **kw: {'id': 'r', 'recording': True})
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    if allow:
        assert routes._get_valid_conversation_by_id('synthetic', 'r', allow_recording=True)['id'] == 'r'
    else:
        with pytest.raises(HTTPException) as error:
            routes._get_valid_conversation_by_id('synthetic', 'r')
        assert error.value.status_code == 404


@pytest.mark.parametrize('trigger', list(ProcessingTrigger))
def test_all_processing_triggers_take_no_model_recording_path(monkeypatch, trigger):
    from utils.conversations import lifecycle
    from models.conversation import Conversation

    at = datetime(2026, 11, 16, tzinfo=timezone.utc)
    row = Conversation(id='r', created_at=at, started_at=at, finished_at=at, structured={}, recording=True)
    forbidden = MagicMock(side_effect=AssertionError('recording reached processing body'))
    monkeypatch.setattr(lifecycle, 'complete', lambda *a: True)
    monkeypatch.setattr(db, 'get_conversation', lambda *a: {'status': 'completed', 'recording': True})
    marked = []
    monkeypatch.setattr(service, 'changed', lambda *a, **kw: marked.append((a, kw)))
    disposition = []
    result = service.recording_short_path(forbidden)(
        'synthetic', 'en', row, trigger=trigger, derived_effects_disposition_observer=disposition.append
    )
    assert disposition[0].value == 'terminal_no_derived_effects'
    assert result.status.value == 'completed'
    assert marked
    forbidden.assert_not_called()


def test_non_v3_processing_is_unchanged():
    original = MagicMock(return_value='ordinary')
    assert service.recording_short_path(original)('synthetic', 'en', object()) == 'ordinary'
    original.assert_called_once()


@pytest.mark.parametrize(
    'source,marked',
    [('omi', True), ('phone', True), ('desktop', False), ('phone_call', False), ('external_integration', False)],
)
def test_only_pendant_creation_is_marked(monkeypatch, source, marked):
    monkeypatch.setattr(triggers, 'conversations_v3_enabled', lambda uid: True)
    row = {'source': source, 'data_protection_level': 'standard'}
    triggers.mark_new('synthetic', row)
    assert bool(row.get('recording')) is marked
    assert bool(row.get('terminal_no_derived_effects')) is marked


def test_kill_switch_does_not_suppress_existing_recordings(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3', 'off')
    called = []
    monkeypatch.setattr(service.store, 'mark_pending', lambda *a, **kw: True)
    monkeypatch.setattr(triggers, 'enqueue', lambda uid: called.append(uid))
    service.changed('synthetic', 'already-marked')
    assert called == ['synthetic']


def test_released_episode_and_home_kind_fallback(monkeypatch):
    monkeypatch.setattr(episodes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(episodes.client_gate, 'note_client_seen', lambda uid: None)
    assert episodes.get_live_episode('synthetic', 'beta') == {'enabled': False, 'episode': None}
    # The released decoder's closed vocabulary remains unchanged.
    from models.home_feed import HomeFeedCard

    assert set(HomeFeedCard.model_fields['kind'].annotation.__args__) == {'episode', 'conversation'}


def test_audio_alias_is_owner_checked(monkeypatch):
    calls = []

    def load(uid, cid):
        calls.append((uid, cid))
        if cid == 'c':
            return {'id': 'c'}
        if cid != 'r':
            return None
        return {'recording': True, 'claims': [{'conversation_id': 'c'}], 'audio_files': [{'id': 'file'}]}

    monkeypatch.setattr(db, 'get_conversation', load)
    assert audio.resolve('synthetic', {'id': 'c'}, {'id': 'alias', 'recording_id': 'r', 'recording_file_id': 'file'})[
        :2
    ] == ('r', {'id': 'file'})
    assert calls == [('synthetic', 'c'), ('synthetic', 'r')]
    with pytest.raises(HTTPException):
        audio.resolve('synthetic', {'id': 'different'}, {'id': 'file', 'recording_id': 'r'})


def test_deleted_spans_preserve_neighbours():
    assert audio.subtract_spans(0, 100, [(20, 30), (60, 120)]) == [(0, 20), (30, 60)]


def test_index_planted_recording_is_rejected_on_hydration(monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    client = StrictFirestore(
        {
            ('users', 'synthetic', 'conversations', 'r'): {'id': 'r', 'recording': True, 'status': 'completed'},
            ('users', 'synthetic', 'conversations', 'short'): {
                'id': 'short',
                'home_hidden': True,
                'status': 'completed',
            },
        }
    )
    monkeypatch.setattr(db, 'db', client)
    assert [r['id'] for r in db._get_conversations_by_id('synthetic', ['r', 'short'])] == ['short']
    assert len(db._get_conversations_by_id('synthetic', ['r', 'short'], include_recordings=True)) == 2


def test_counts_include_legacy_documents_without_recording_field(monkeypatch):
    from tests.unit.test_sync_donor_tombstone_visibility import _install_listing

    at = datetime(2026, 11, 16, tzinfo=timezone.utc)
    rows = {
        cid: {'id': cid, 'created_at': at, 'status': 'completed', 'discarded': False, **fields}
        for cid, fields in [
            ('legacy', {}),
            ('ordinary', {'recording': False}),
            ('recording', {'recording': True}),
            ('short', {'home_hidden': True}),
        ]
    }
    _install_listing(monkeypatch, rows)
    assert db.get_conversations_count('synthetic') == 3
    assert db.get_conversations_count('synthetic', hide_home=True) == 2


@pytest.mark.parametrize('update_only', [False, True])
def test_recordings_never_embed_even_on_completed_replay(monkeypatch, update_only):
    from types import SimpleNamespace
    from utils.conversations import process_conversation as process

    forbidden = MagicMock(side_effect=AssertionError('recording embedded'))
    monkeypatch.setattr(process, 'generate_embedding', forbidden)
    assert process.save_structured_vector('synthetic', SimpleNamespace(recording=True), update_only=update_only)
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    'statuses,capture', [('in_progress', True), ('completed', False), ('processing,completed', False)]
)
def test_released_capture_poll_keeps_recording_identity(monkeypatch, statuses, capture):
    from types import SimpleNamespace

    class CapturedRead(BaseException):
        pass

    bound = {}

    def read(*args, **kwargs):
        bound.update(kwargs)
        raise CapturedRead()

    monkeypatch.setattr(routes, 'list_read_budget_for_request', lambda *a, **kw: None)
    monkeypatch.setattr(db, 'get_conversations_without_photos', read)
    with pytest.raises(CapturedRead):
        routes.get_conversations(
            uid='synthetic',
            statuses=statuses,
            sources=None,
            start_date=None,
            end_date=None,
            folder_id=None,
            starred=None,
        )
    assert bound['include_recordings'] is capture
    assert bound['capture_only'] is capture
    if capture:
        assert db.is_visible_conversation(
            {'id': 'recording', 'recording': True, 'status': 'in_progress'}, include_recordings=True, capture_only=True
        )
        assert not db.is_visible_conversation(
            {'id': 'derived', 'v3_derived': True, 'status': 'in_progress'}, include_recordings=True, capture_only=True
        )


@pytest.mark.parametrize(
    'include_recordings,hide_home,expected', [(True, False, 'r'), (False, True, 'good'), (False, False, 'short')]
)
def test_cursor_refills_after_recording_and_hidden_rows(include_recordings, hide_home, expected):
    from tests.unit.test_sync_donor_tombstone_visibility import _ListingDoc, _ListingQuery

    anchor = _ListingDoc('anchor', {})
    docs = [anchor] + [
        _ListingDoc(cid, {'status': 'completed', 'discarded': False, **fields})
        for cid, fields in [('r', {'recording': True}), ('short', {'home_hidden': True}), ('good', {})]
    ]
    rows, last = db._collect_cursor_conversation_page(
        _ListingQuery(docs),
        limit=1,
        include_discarded=False,
        budget=None,
        bookmark=anchor,
        include_recordings=include_recordings,
        hide_home=hide_home,
    )
    assert len(rows) == 1 and rows[0]['id'] == expected
    assert last.id == expected


def _open_row(cid, last, **extra):
    return {
        'id': cid,
        'status': 'in_progress',
        'created_at': last,
        'started_at': last,
        'finished_at': last,
        'v3_derived': True,
        'tile_state': 'live',
        **extra,
    }


def _serve_windows(monkeypatch, rows, calls=None):
    """Stub the indexed v3 read the live route uses (database.conversations_v3_live)."""

    def recent(uid, *, now, max_idle, **kw):
        if calls is not None:
            calls.append(dict(now=now, max_idle=max_idle))
        served = rows() if callable(rows) else rows
        return served, len(served)

    monkeypatch.setattr(routes, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(routes.conversations_v3_live, 'recent_windows', recent)


def test_live_skips_a_capture_that_never_closed(monkeypatch):
    now = datetime.now(timezone.utc)
    seen = {}
    calls = []
    _serve_windows(monkeypatch, lambda: seen['rows'], calls)
    stale = _open_row('stale', now - routes.v3_live.MAX_IDLE - timedelta(minutes=1))
    # Only a days-old open row: nothing is in progress, so the client keeps its capture card.
    seen['rows'] = [stale]
    assert routes.get_live_conversation('u', 'beta') == {'v3': True, 'conversation': None}
    assert calls[-1]['max_idle'] == routes.v3_live.MAX_IDLE
    # A stale stub beside it does not hide the open conversation.
    seen['rows'] = [stale, _open_row('rec', now, recording=True), _open_row('open', now - timedelta(minutes=10))]
    assert routes.get_live_conversation('u', 'beta')['conversation']['id'] == 'open'
    # Naive stored times read as UTC; a row with no time at all is not served.
    seen['rows'] = [_open_row('naive', now.replace(tzinfo=None))]
    assert routes.get_live_conversation('u', 'beta')['conversation']['id'] == 'naive'
    seen['rows'] = [{'id': 'bare', 'status': 'in_progress', 'v3_derived': True, 'tile_state': 'live'}]
    assert routes.get_live_conversation('u', 'beta')['conversation'] is None


@pytest.mark.parametrize('recording, locked', [(False, False), (False, True), (True, False)])
def test_live_response_is_compact_and_never_a_recording(monkeypatch, recording, locked):
    started = datetime.now(timezone.utc) - timedelta(minutes=3)
    _serve_windows(
        monkeypatch,
        [
            {
                'id': 'c',
                'started_at': started,
                'status': 'in_progress',
                'created_at': started,
                'v3_derived': True,
                'tile_state': 'live',
                'recording': recording,
                'is_locked': locked,
                'v3_recording_ids': ['old-recording'] * 8 + ['raw-a', 'invalid/path', 'raw-b'],
                'transcript_segments': [{'text': 'private capture'}],
                'structured': {'title': 'Plan', 'emoji': '🌳', 'overview': 'omit'},
            }
        ],
    )
    result = routes.get_live_conversation('u', 'store')
    if recording:
        assert result['conversation'] is None
    else:
        from models.conversation import ConversationsLiveResponse

        wire = ConversationsLiveResponse(**result).model_dump(exclude_unset=True)
        assert 'transcript_segments' not in wire['conversation']
        if locked:
            assert wire['conversation']['is_locked'] is True
            assert 'v3_recording_ids' not in wire['conversation']
        else:
            assert wire['conversation']['v3_recording_ids'] == ['old-recording'] * 5 + ['raw-a', 'raw-b']
        assert wire['conversation']['structured'] == {'title': 'Plan', 'emoji': '🌳'}
        import json
        from pathlib import Path

        schema = json.loads(
            (Path(__file__).resolve().parents[3] / 'docs/api-reference/app-client-openapi.json').read_text()
        )
        required = schema['components']['schemas']['Conversation']['required']
        assert set(required) <= wire['conversation'].keys()
        assert wire['conversation']['finished_at'] is None


def _live_row(id, *, v3=True, minutes_ago=1, tile_state='live', **extra):
    now = datetime.now(timezone.utc)
    return {
        'id': id,
        'status': 'in_progress',
        'created_at': now - timedelta(minutes=minutes_ago + 5),
        'started_at': now - timedelta(minutes=minutes_ago + 5),
        'finished_at': now - timedelta(minutes=minutes_ago),
        'v3_derived': v3 or None,
        'tile_state': tile_state if v3 else None,
        'structured': {'title': '', 'emoji': ''},
        **extra,
    }


@pytest.mark.parametrize(
    'rows, expected',
    [
        # A legacy in-progress row (not v3-derived) is never the live tile, however new.
        ([_live_row('legacy', v3=False)], None),
        ([_live_row('legacy', v3=False), _live_row('window')], 'window'),
        # A v3 window whose last speech is past the idle bound is stale, not live.
        ([_live_row('stale', minutes_ago=121)], None),
        ([_live_row('writing', tile_state='writing')], None),
        ([_live_row('window', minutes_ago=119)], 'window'),
        # Hidden, deleted, discarded or finished windows are never the live tile.
        ([_live_row('hidden', home_hidden=True)], None),
        ([_live_row('deleted', deleted=True)], None),
        ([_live_row('discarded', discarded=True)], None),
        ([_live_row('done', status='processing')], None),
        # The index returns windows oldest-first: the newest open window wins.
        ([_live_row('older', minutes_ago=40), _live_row('newer', minutes_ago=2)], 'newer'),
    ],
)
def test_live_returns_only_a_recent_open_v3_window(monkeypatch, rows, expected):
    _serve_windows(monkeypatch, rows)
    result = routes.get_live_conversation('u', 'store')
    assert (result['conversation'] or {}).get('id') == expected


class _WindowQuery:
    """A Firestore query fake over v3 windows: records the shape and pages by limit/start_after."""

    def __init__(self, docs, log, filters=(), size=None, after=None, fields=None, bounds=()):
        self.docs, self.log, self.filters, self.size, self.after, self.fields = docs, log, filters, size, after, fields
        self.bounds = bounds

    def _clone(self, **kw):
        state = dict(filters=self.filters, size=self.size, after=self.after, fields=self.fields, bounds=self.bounds)
        state.update(kw)
        return _WindowQuery(self.docs, self.log, **state)

    def collection(self, name):
        return self

    def document(self, name):
        return self

    def where(self, *, filter):
        return self._clone(
            filters=(*self.filters, (filter.field_path, filter.op_string)),
            bounds=(*self.bounds, (filter.field_path, filter.op_string, filter.value)),
        )

    def _matches(self, doc):
        ops = {'==': lambda a, b: a == b, '>=': lambda a, b: a >= b, '<=': lambda a, b: a <= b, '<': lambda a, b: a < b}
        return all(ops[op](doc._data.get(field), value) for field, op, value in self.bounds)

    def select(self, fields):
        return self._clone(fields=list(fields))

    def order_by(self, field):
        assert field == 'finished_at'
        return self

    def limit(self, size):
        return self._clone(size=size)

    def start_after(self, snapshot):
        return self._clone(after=snapshot)

    def stream(self):
        self.log.append(dict(filters=self.filters, size=self.size, fields=self.fields))
        docs = sorted((d for d in self.docs if self._matches(d)), key=lambda d: d._data['finished_at'])
        start = 0 if self.after is None else docs.index(self.after) + 1
        return iter(docs[start : start + self.size])


class _Snap:
    def __init__(self, data):
        self.id, self._data = data['id'], data

    def to_dict(self):
        return dict(self._data)


def _live_read(monkeypatch, docs, log):
    from database import conversations_v3_live as live_db

    monkeypatch.setattr(live_db, 'prepare_conversation_for_read', lambda row, uid: row)
    now = datetime.now(timezone.utc)
    row = live_db.live_window(
        'u',
        now=now,
        max_idle=routes.v3_live.MAX_IDLE,
        pick=routes.v3_live.active,
        firestore_client=_WindowQuery(docs, log),
    )
    return live_db, row


def _finished(n, *, newest_minutes_ago):
    # n finished windows, one a minute, the newest ``newest_minutes_ago`` old.
    return [
        _Snap(_live_row(f'done-{i:03d}', minutes_ago=newest_minutes_ago + i, status='processing', tile_state='done'))
        for i in range(n)
    ]


def test_live_read_finds_a_speaking_window_in_the_recent_band(monkeypatch):
    # A busy account: 100 finished windows in the idle cap. The open window spoke a minute
    # ago, so the recent band holds it and the full window is never read.
    log = []
    live_db, row = _live_read(monkeypatch, _finished(100, newest_minutes_ago=20) + [_Snap(_live_row('open'))], log)
    assert row['id'] == 'open'
    assert len(log) == 1 and log[0]['size'] == live_db.PAGE
    # Indexed filters only (v3_derived, finished_at, started_at): legacy rows never enter the scan.
    assert log[0]['filters'] == (('v3_derived', '=='), ('finished_at', '>='), ('started_at', '<='))
    # The projection is unconditional and carries no transcript.
    assert 'transcript_segments' not in log[0]['fields'] and 'structured' in log[0]['fields']


def test_live_read_widens_to_the_idle_cap_for_a_quiet_open_window(monkeypatch):
    log = []
    docs = _finished(30, newest_minutes_ago=40) + [_Snap(_live_row('quiet', minutes_ago=30))]
    _, row = _live_read(monkeypatch, docs, log)
    assert row['id'] == 'quiet'
    assert len(log) == 2
    # The wider band excludes the recent one, so no recent window is read twice.
    assert log[1]['filters'][-1] == ('finished_at', '<')


def test_live_read_with_nothing_open_stops_at_its_cap_and_logs(monkeypatch, caplog):
    from database import conversations_v3_live as live_db

    monkeypatch.setattr(live_db, 'READ_CAP', 7)
    monkeypatch.setattr(live_db, 'PAGE', 3)
    log = []
    with caplog.at_level('WARNING', logger=live_db.__name__):
        _, row = _live_read(monkeypatch, _finished(4, newest_minutes_ago=1) + _finished(20, newest_minutes_ago=30), log)
    assert row is None
    # The cap is shared across both bands: 4 rows in the recent band, then 3 more.
    assert [call['size'] for call in log] == [3, 3, 3]
    assert 'stopped at its bound of 3 windows' in caplog.text
    # The lookup reports the capped miss as incomplete; a short scan that finds nothing is complete.
    now = datetime.now(timezone.utc)
    args = dict(now=now, max_idle=routes.v3_live.MAX_IDLE, pick=routes.v3_live.active)
    capped = _finished(4, newest_minutes_ago=1) + _finished(20, newest_minutes_ago=30)
    assert live_db.live_window_lookup('u', firestore_client=_WindowQuery(capped, []), **args) == (None, False)
    short = _finished(2, newest_minutes_ago=1)
    assert live_db.live_window_lookup('u', firestore_client=_WindowQuery(short, []), **args) == (None, True)


def test_merge_rejects_recording_before_admission(monkeypatch):
    from fastapi import BackgroundTasks
    from models.conversation import MergeConversationsRequest

    monkeypatch.setattr(db, 'get_conversation', lambda *a, **kw: {'id': 'r', 'recording': True})
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    with pytest.raises(HTTPException) as error:
        routes.merge_conversations(MergeConversationsRequest(conversation_ids=['r', 'c']), BackgroundTasks(), 'u')
    assert error.value.status_code == 404


def test_reprocess_rejects_recording_before_processing(monkeypatch):
    monkeypatch.setattr(db, 'get_conversation', lambda *a, **kw: {'id': 'r', 'recording': True})
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    with pytest.raises(HTTPException) as error:
        routes.reprocess_conversation('r', uid='u')
    assert error.value.status_code == 404


def test_joan_rejects_recording_before_prompt(monkeypatch):
    from routers import users

    monkeypatch.setattr(users, 'get_conversation', lambda *a: {'id': 'r', 'recording': True})
    monkeypatch.setattr(users, 'followup_question_prompt', lambda *a: pytest.fail('raw capture sent to prompt'))
    with pytest.raises(HTTPException) as error:
        users.delete_followup_question_endpoint('r', 'u')
    assert error.value.status_code == 404


def test_lapsed_beta_marker_restores_legacy_capture_and_episode_admission(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_STAGE', 'beta')
    monkeypatch.delenv('CONVERSATIONS_V3', raising=False)
    monkeypatch.setattr(switch, 'in_rollout_cohort', lambda *a: False)
    monkeypatch.setattr(switch.client_gate, 'client_seen_cached', lambda uid: False)
    monkeypatch.setattr(triggers, 'conversations_v3_enabled', switch.conversations_v3_enabled)
    row = {'source': 'omi', 'data_protection_level': 'standard'}
    triggers.mark_new('u', row)
    assert 'recording' not in row and 'v3_pending' not in row
    monkeypatch.setattr(episodes, 'conversations_v3_enabled', switch.conversations_v3_enabled)
    monkeypatch.setattr(episodes, 'episodes_enabled_for', lambda *a: True)
    monkeypatch.setattr(episodes, 'client_channel_admitted', lambda *a: True)
    assert episodes._admitted('u', 'store') is True


def test_episode_admission_is_cached_once_per_request(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    calls = []
    monkeypatch.setattr(episodes, 'conversations_v3_enabled', lambda uid: calls.append(uid) or True)
    monkeypatch.setattr(episodes.client_gate, 'note_client_seen', lambda *a: None)
    app = FastAPI()
    app.include_router(episodes.router)
    app.dependency_overrides[episodes.auth.get_current_user_uid] = lambda: 'u'
    assert TestClient(app).get('/v1/episodes/live', headers={'X-Omi-App-Channel': 'beta'}).status_code == 200
    assert calls == ['u']


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('992', 'pre_v3'),
        ('993', 'v3_capable'),
        ('1200', 'v3_capable'),
        ('', 'unknown'),
        ('1.0.599', 'unknown'),
        ('-1', 'unknown'),
    ],
)
def test_episode_build_bucket_uses_first_v3_build(monkeypatch, raw, expected):
    monkeypatch.setenv('CONVERSATIONS_V3_FIRST_APP_BUILD', '993')  # synthetic boundary, not a release assertion
    assert switch.episode_build_bucket(raw) == expected


def test_episode_request_uses_build_header_not_marketing_version(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    meter = MagicMock()
    monkeypatch.setenv('CONVERSATIONS_V3_FIRST_APP_BUILD', '993')
    monkeypatch.setattr(episodes.v3_metrics, 'EPISODE_CALLS', meter)
    request = SimpleNamespace(
        url=SimpleNamespace(path='/v1/episodes/live'),
        headers={'X-App-Version': '1.0.599', 'X-App-Build': '992'},
        scope={'route': SimpleNamespace(path='/v1/episodes/live')},
    )
    episodes._record_episode_request(request, 'u', 'store', False)
    meter.labels.assert_called_once_with('/v1/episodes/live', 'store', 'pre_v3', 'false')
    monkeypatch.delenv('CONVERSATIONS_V3_FIRST_APP_BUILD')
    assert switch.episode_build_bucket('992') == 'unknown'


@pytest.mark.parametrize(
    'mark, pending',
    [
        (None, False),
        ({'generation': 0, 'applied_generation': 0}, True),
        ({'generation': 2, 'applied_generation': 1}, True),
        ({'generation': 2, 'applied_generation': 2}, False),
    ],
)
def test_settled_partial_recording_is_not_pending_transcription(mark, pending):
    from utils.conversations.v3 import policy

    row = {'record_audio_partial': mark} if mark is not None else {}
    assert policy.transcription_pending(row) is pending


def test_projection_reads_hydrated_segments_with_speaker_corrections(monkeypatch):
    from types import SimpleNamespace

    from database import conversations as conversations_db, conversations_v3 as store

    raw = [{'text': 'hi', 'speaker_id': 0, 'is_user': False}]
    corrected = [{'text': 'hi', 'speaker_id': 0, 'is_user': True, 'person_id': 'p'}]
    monkeypatch.setattr(conversations_db, 'decode_transcript_segments_verified', lambda *a: raw)
    monkeypatch.setattr(
        conversations_db, 'prepare_conversation_for_read', lambda data, uid: {**data, 'transcript_segments': corrected}
    )
    snapshot = SimpleNamespace(exists=True, id='r', update_time=1, to_dict=lambda: {'transcript_segments': []})
    assert store.decode_row('u', snapshot)['transcript_segments'] == corrected


# The classification gate discovers new raw readers, including imported aliases.
READER_GUARD = Path(__file__).resolve().parents[2] / 'scripts' / 'check_conversation_readers.py'


def load_reader_guard():
    spec = importlib.util.spec_from_file_location('conversation_reader_guard', READER_GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_collection_reader_is_detected(tmp_path):
    path = tmp_path / 'backend/routers/unclassified.py'
    path.parent.mkdir(parents=True)
    path.write_text("def read(db):\n    return db.collection('conversations').stream()\n")
    assert list(load_reader_guard().references(tmp_path)) == [('backend/routers/unclassified.py', 'collection', 2)]
    assert load_reader_guard().check({}, root=tmp_path) == 1
    assert (
        load_reader_guard().check(
            {
                'backend/routers/unclassified.py:collection': {
                    'policy': 'conversations',
                    'reason': 'Synthetic product boundary',
                }
            },
            root=tmp_path,
        )
        == 0
    )


def test_alias_and_document_path_readers_are_detected(tmp_path):
    path = tmp_path / 'backend/utils/new_reader.py'
    path.parent.mkdir(parents=True)
    path.write_text(
        "from database.conversations import get_conversation as read_one\ndef read(db, uid, cid):\n    read_one(uid, cid)\n    return db.document(f'users/{uid}/conversations/{cid}').get()\n"
    )
    assert {operation for _, operation, _ in load_reader_guard().references(tmp_path)} == {'read_one', 'document_path'}


def test_attribute_collection_constant_is_detected(tmp_path):
    path = tmp_path / 'backend/database/recovery.py'
    path.parent.mkdir(parents=True)
    path.write_text('def read(db):\n    return db.collection(jobs.CONVERSATIONS_COLLECTION).stream()\n')
    assert list(load_reader_guard().references(tmp_path)) == [('backend/database/recovery.py', 'collection', 2)]


@pytest.mark.parametrize(
    'before, update, rearmed',
    [
        ({'recording': True}, {'audio_files': [{'id': 'f'}]}, True),
        ({'recording': True, 'v3_pending': True}, {'audio_files': [{'id': 'f'}]}, False),
        ({'recording': True}, {'audio_files': []}, False),
        ({}, {'audio_files': [{'id': 'f'}]}, False),
        ({'recording': True, 'deleted': True}, {'audio_files': [{'id': 'f'}]}, False),
    ],
)
def test_late_audio_on_a_settled_recording_rearms_the_builder(monkeypatch, before, update, rearmed):
    from utils.conversations.v3 import triggers as v3_triggers

    snapshot = MagicMock(exists=True, update_time=1)
    snapshot.to_dict.return_value = before
    ref = MagicMock()
    ref.get.return_value = snapshot
    monkeypatch.setattr(db, 'db', MagicMock())
    db.db.collection.return_value.document.return_value.collection.return_value.document.return_value = ref
    monkeypatch.setattr(db, '_prepare_conversation_for_write', lambda data, *a, **k: data)
    monkeypatch.setattr(db, 'retain_aliases', lambda files, _old: files)
    monkeypatch.setattr(db, 'guard_match_score_size', lambda *a: None)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda *a: None)
    calls = []
    monkeypatch.setattr(v3_triggers, 'changed', lambda uid, cid: calls.append((uid, cid)))
    assert db.update_conversation('u', 'r', update) is True
    assert calls == ([('u', 'r')] if rearmed else [])

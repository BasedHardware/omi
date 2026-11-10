"""Hermetic admission, cursor and privacy tests for closed-episode maintenance."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from config.episodes import COMPOSER_SWEEP_INTERVAL_SECONDS
from services import episode_compose_sweep as sweep

NOW = 2_000_000.0


def _at(*, seconds_ago: float = 3600) -> datetime:
    return datetime.fromtimestamp(NOW - seconds_ago, timezone.utc)


class _Ref:
    def __init__(self, store: dict, path: str):
        self.store = store
        self.path = path

    def get(self, *, transaction=None):
        return SimpleNamespace(to_dict=lambda: dict(self.store.get(self.path) or {}))


class _Transaction:
    _read_only = False
    _max_attempts = 1
    _id = b'synthetic'

    def _clean_up(self) -> None:
        pass

    def _begin(self, retry_id=None) -> None:
        pass

    def _commit(self) -> None:
        pass

    def _rollback(self) -> None:
        pass

    def set(self, ref: _Ref, row: dict) -> None:
        ref.store[ref.path] = dict(row)

    def update(self, ref: _Ref, updates: dict) -> None:
        ref.store[ref.path] = {**ref.store.get(ref.path, {}), **updates}


class _Client:
    def __init__(self):
        self.rows = {}

    def document(self, path: str) -> _Ref:
        return _Ref(self.rows, path)

    def transaction(self) -> _Transaction:
        return _Transaction()


class _Snapshot:
    def __init__(self, path: str, row: dict):
        self.reference = SimpleNamespace(path=path)
        self.id = path.rsplit('/', 1)[-1]
        self.row = row

    def to_dict(self) -> dict:
        return dict(self.row)


def _snapshot(episode_id: str, *, needs: bool = True, seconds_ago: float = 3600, **updates) -> _Snapshot:
    row = {
        'status': 'closed',
        'closed_at': _at(seconds_ago=seconds_ago),
        'needs': needs,
        **updates,
    }
    return _Snapshot(f'users/u/episodes/{episode_id}', row)


@pytest.fixture
def world(monkeypatch):
    client = _Client()
    page = []
    query = Mock(side_effect=lambda **kwargs: list(page))
    schedule = Mock(return_value=True)
    deletion = Mock(return_value=False)
    telemetry = Mock()
    monkeypatch.setattr(sweep, 'episodes_enabled', lambda: True)
    monkeypatch.setattr(sweep, 'episode_compose_sweep_enabled', lambda: True)
    monkeypatch.setattr(sweep, 'episode_composer_enabled', lambda: True)
    monkeypatch.setattr(sweep, 'closed_episodes_for_compose_sweep', query)
    monkeypatch.setattr(sweep.episodes_db, 'unseal', lambda uid, raw: dict(raw))
    monkeypatch.setattr(sweep.composer, 'needs_compose', lambda row: bool(row and row.get('needs')))
    monkeypatch.setattr(sweep.composer, 'schedule', schedule)
    monkeypatch.setattr(sweep, 'account_deletion_blocks_user_work', deletion)
    monkeypatch.setattr(sweep.metrics, 'record_compose_sweep', telemetry)
    return SimpleNamespace(
        client=client, page=page, query=query, schedule=schedule, deletion=deletion, telemetry=telemetry
    )


def test_env_switch_defaults_on_and_false_disables(monkeypatch):
    from config import episodes as config

    monkeypatch.delenv(config.EPISODE_COMPOSE_SWEEP_ENABLED_ENV, raising=False)
    assert config.episode_compose_sweep_enabled()
    for raw in ('false', '0', 'off', 'no'):
        monkeypatch.setenv(config.EPISODE_COMPOSE_SWEEP_ENABLED_ENV, raw)
        assert not config.episode_compose_sweep_enabled()


@pytest.mark.parametrize('switch', ['episodes_enabled', 'episode_compose_sweep_enabled', 'episode_composer_enabled'])
def test_disabled_tick_has_no_cursor_or_discovery_io(world, monkeypatch, switch):
    monkeypatch.setattr(sweep, switch, lambda: False)

    assert sweep.tick(now=NOW, client=world.client) == sweep.empty_counts()
    assert world.client.rows == {}
    world.query.assert_not_called()
    world.schedule.assert_not_called()


def test_newest_first_admission_caps_paid_work_and_advances_full_page(world, monkeypatch):
    monkeypatch.setattr(sweep, 'COMPOSER_SWEEP_SCAN_LIMIT', 5)
    monkeypatch.setattr(sweep, 'COMPOSER_SWEEP_SCHEDULE_LIMIT', 2)
    world.page.extend(
        [
            _snapshot('newest'),
            _snapshot('composed', needs=False),
            _snapshot('inflight'),
            _snapshot('older'),
            _snapshot('beyond-budget'),
        ]
    )
    world.schedule.side_effect = [True, False, True]

    counts = sweep.tick(now=NOW, client=world.client)

    assert counts == {
        'scanned': 5,
        'scheduled': 2,
        'skipped_composed': 1,
        'skipped_inflight': 1,
        'budget_exhausted': 1,
        'errors': 0,
    }
    assert world.schedule.call_args_list == [
        call('u', 'newest', throttle=True, foreground=False, deletion_fence=True),
        call('u', 'inflight', throttle=True, foreground=False, deletion_fence=True),
        call('u', 'older', throttle=True, foreground=False, deletion_fence=True),
    ]
    assert world.deletion.call_count == 3
    assert world.telemetry.call_args_list == [
        call('scheduled'),
        call('skipped_composed'),
        call('skipped_inflight'),
        call('scheduled'),
        call('budget_exhausted'),
    ]
    cursor = world.client.rows[sweep.CURSOR]
    assert cursor['path'] == 'users/u/episodes/beyond-budget'
    assert cursor['closed_at'] == _at()
    assert cursor['next_at'] == NOW + COMPOSER_SWEEP_INTERVAL_SECONDS
    assert cursor['lease_until'] == 0


def test_wraps_after_short_page_and_preserves_fresh_deletion_and_merge_fences(world):
    world.page.extend(
        [
            _snapshot('merged', recorded_merged_into='survivor'),
            _snapshot('fresh', seconds_ago=60),
            _snapshot('deleting'),
        ]
    )
    world.deletion.return_value = True

    counts = sweep.tick(now=NOW, client=world.client)

    assert counts['scanned'] == 3 and counts['scheduled'] == 0 and counts['errors'] == 0
    world.schedule.assert_not_called()
    world.deletion.assert_called_once_with('u', firestore_client=world.client)
    cursor = world.client.rows[sweep.CURSOR]
    assert cursor['path'] is None and cursor['closed_at'] is None


def test_poison_rows_count_errors_without_trapping_cursor(world, monkeypatch):
    monkeypatch.setattr(sweep, 'COMPOSER_SWEEP_SCAN_LIMIT', 2)
    world.page.extend(
        [
            _Snapshot('foreign/u/episodes/bad-path', {'closed_at': _at()}),
            _snapshot('bad-encryption'),
        ]
    )
    monkeypatch.setattr(sweep.episodes_db, 'unseal', Mock(side_effect=ValueError('synthetic')))

    counts = sweep.tick(now=NOW, client=world.client)

    assert counts['scanned'] == 2 and counts['errors'] == 2
    assert world.client.rows[sweep.CURSOR]['path'] == 'users/u/episodes/bad-encryption'
    assert world.telemetry.call_args_list == [call('error'), call('error')]


def test_deletion_authority_failure_fails_closed_without_trapping_cursor(world, monkeypatch):
    monkeypatch.setattr(sweep, 'COMPOSER_SWEEP_SCAN_LIMIT', 1)
    world.page.append(_snapshot('authority-error'))
    world.deletion.side_effect = RuntimeError('synthetic')

    counts = sweep.tick(now=NOW, client=world.client)

    assert counts['errors'] == 1 and counts['scheduled'] == 0
    world.schedule.assert_not_called()
    assert world.telemetry.call_args_list == [call('error')]
    assert world.client.rows[sweep.CURSOR]['path'] == 'users/u/episodes/authority-error'


def test_existing_lease_does_no_discovery(world):
    world.client.rows[sweep.CURSOR] = {'lease_until': NOW + 1, 'next_at': 0}

    assert sweep.tick(now=NOW, client=world.client) == sweep.empty_counts()
    world.query.assert_not_called()
    world.schedule.assert_not_called()


def test_existing_cursor_is_passed_to_keyset_query(world):
    previous = {'path': 'users/u/episodes/previous', 'closed_at': _at(seconds_ago=7200)}
    world.client.rows[sweep.CURSOR] = previous

    sweep.tick(now=NOW, client=world.client)

    assert world.query.call_args.kwargs['after']['path'] == previous['path']
    assert world.query.call_args.kwargs['after']['closed_at'] == previous['closed_at']
    assert world.client.rows[sweep.CURSOR]['path'] is None

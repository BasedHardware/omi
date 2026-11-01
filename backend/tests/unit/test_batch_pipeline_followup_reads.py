"""Count discovery reads through the real result query and followup selector."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_store import projection_page
from utils.batch_pipeline.projection_followup import ProjectionFollowups


class ResultQuery:
    """Read-only query fake; counts returned documents, including empty queries."""

    def __init__(self, rows):
        self.rows = rows
        self.reads = 0
        self.states = ()
        self.after = None

    def collection(self, _):
        return self

    def where(self, field, op, values):
        assert (field, op) == ('projection_state', 'in')
        self.states = values
        self.after = None
        return self

    def order_by(self, _):
        return self

    def start_after(self, cursor):
        self.after = (cursor['committed_at'], cursor['__name__'])
        return self

    def document(self, key):
        return key

    def limit(self, size):
        self.size = size
        return self

    def stream(self):
        rows = sorted(
            (row['committed_at'], key)
            for key, row in self.rows.items()
            if row['projection_state'] in self.states
            and (self.after is None or (row['committed_at'], key) > self.after)
        )[: self.size]
        self.reads += max(1, len(rows))
        return [SimpleNamespace(id=key, to_dict=lambda key=key: dict(self.rows[key])) for _, key in rows]


def scanner(rows):
    query = ResultQuery(rows)
    store = Mock()
    store.projection_page.side_effect = lambda **kw: projection_page(query, 'batch_pipeline_dev', **kw)
    store.projection_pending.side_effect = lambda **kw: projection_page(query, 'batch_pipeline_dev', **kw)[0]
    projector = Mock()
    projector.store.store = store

    def fetch(_, key):
        def get():
            query.reads += 1
            return SimpleNamespace(
                to_dict=lambda: {'policy_parts': {'projection': ProjectionPolicy(async_projection=True).to_dict()}}
            )

        return SimpleNamespace(get=get)

    def read(key):
        query.reads += 2  # ProjectionStore.read fetches both job and result.
        return {'policy_parts': {'projection': ProjectionPolicy(async_projection=True).to_dict()}}, rows[key], None

    projector.store.ref.side_effect = fetch
    projector.store.read.side_effect = read
    return ProjectionFollowups(projector), query


@pytest.mark.parametrize(
    'state,legacy_reads,new_reads', [('pending', 200, 1), ('persisted', 400, 200), ('ready', 400, 200)]
)
def test_blocked_backlog_discovery_reads_fall_on_every_pass(monkeypatch, state, legacy_reads, new_reads):
    rows = {
        f'synthetic-{index:03}': {
            'projection_state': state,
            'committed_at': index,
            **({'projection': {'state': state}} if state != 'pending' else {}),
        }
        for index in range(100)
    }
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED', 'false')
    old, old_query = scanner(rows)
    old.projector.store.ref.side_effect = lambda _, key: SimpleNamespace(get=lambda: legacy_get(old_query, rows[key]))
    old.candidates()
    assert old_query.reads == legacy_reads
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED')
    for _ in range(2):
        runner, query = scanner(rows)  # No warm cache needed, including on restart.
        found = runner.candidates()
        assert query.reads == new_reads
        assert len(found) == (0 if state == 'pending' else 100)
        assert runner.projector.store.ref.call_count == (0 if state == 'pending' else 100)
        runner.projector.store.read.assert_not_called()


def legacy_get(query, row):
    query.reads += 1
    return SimpleNamespace(to_dict=lambda: row)


def test_unpinned_legacy_policy_uses_existing_privacy_aware_resolution():
    rows = {'synthetic': {'projection_state': 'persisted', 'committed_at': 1}}
    runner, _ = scanner(rows)
    runner.projector.store.ref.return_value = SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: {}))
    runner.projector.store.ref.side_effect = None
    assert runner.candidates() == ['synthetic']
    runner.projector.store.read.assert_called_once_with('synthetic')


@pytest.mark.parametrize('pagination', ['true', 'false'])
def test_released_or_repaired_receipt_behind_cursor_returns_within_one_cycle(monkeypatch, pagination):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', pagination)
    rows = {
        f'synthetic-{index:03}': {
            'projection_state': 'persisted',
            'committed_at': index,
            'projection': {'state': 'persisted'},
        }
        for index in range(101)
    }
    rows['synthetic-000']['projection_state'] = 'quarantine_held'
    runner, _ = scanner(rows)
    assert 'synthetic-000' not in runner.candidates()
    # Release/repair returns to pending for assignment; it is not finishable yet.
    rows['synthetic-000'].update(projection_state='pending', projection={})
    assert 'synthetic-000' not in runner.candidates()
    # Assignment persists the repaired row behind the scanner's cursor.
    rows['synthetic-000'].update(projection_state='persisted', projection={'state': 'persisted'})
    seen = []
    for _ in range(3):
        seen.extend(runner.candidates())
    assert 'synthetic-000' in seen

import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

google_stub = sys.modules.setdefault('google', types.ModuleType('google'))
cloud_stub = sys.modules.setdefault('google.cloud', types.ModuleType('google.cloud'))
firestore_v1_stub = sys.modules.setdefault('google.cloud.firestore_v1', types.ModuleType('google.cloud.firestore_v1'))
firestore_v1_stub.transactional = lambda func: func
google_stub.cloud = cloud_stub

if 'database._client' not in sys.modules:
    client_stub = types.ModuleType('database._client')
    client_stub.db = MagicMock()
    client_stub.document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
    sys.modules['database._client'] = client_stub
else:
    sys.modules['database._client'].db = getattr(sys.modules['database._client'], 'db', MagicMock())

from database import memory_ledger  # noqa: E402


def _fact(fact_id, content, *, valid_from=None, valid_to=None):
    qualifiers = {}
    if valid_from:
        qualifiers['valid_from'] = valid_from
    if valid_to:
        qualifiers['valid_to'] = valid_to
    return {
        'id': fact_id,
        'content': content,
        'predicate': 'resides_in',
        'arguments': {'location': content.removeprefix('Lives in ')},
        'subject_entity_id': 'user',
        'qualifiers': qualifiers,
    }


def test_fold_commits_replays_head_and_valid_time():
    january = datetime(2026, 1, 15, tzinfo=timezone.utc)
    february = datetime(2026, 2, 1, tzinfo=timezone.utc)
    learned = datetime(2026, 6, 1, tzinfo=timezone.utc)
    fact = _fact('m1', 'Lives in NYC', valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), valid_to=january)
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=learned)

    assert 'm1' in memory_ledger.fold_commits([commit], valid_time=january)
    assert 'm1' not in memory_ledger.fold_commits([commit], valid_time=february)


def test_add_fact_normalizes_legacy_valid_at_for_replay():
    valid_from = datetime(2026, 6, 1, tzinfo=timezone.utc)
    before_valid = datetime(2026, 5, 31, tzinfo=timezone.utc)
    fact = _fact('m1', 'Lives in NYC')
    fact['valid_at'] = valid_from
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=valid_from)

    assert 'm1' not in memory_ledger.fold_commits([commit], valid_time=before_valid)
    assert 'm1' in memory_ledger.fold_commits([commit], valid_time=valid_from)
    assert commit['mutations'][0]['fact']['qualifiers']['valid_from'] == valid_from


def test_supersede_commit_flips_materialized_head_like_invalidate():
    first = memory_ledger.build_commit(
        None,
        [memory_ledger.add_fact(_fact('m1', 'Lives in NYC'))],
        commit_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    second = memory_ledger.build_commit(
        first['commit_id'],
        [memory_ledger.supersede_fact('m1', by='m2', kind='contradict')],
        commit_time=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    head = memory_ledger.fold_commits([first, second])

    assert 'm1' not in head


def test_valid_time_query_can_return_superseded_fact_for_past_window():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    old_fact = _fact('m1', 'Lives in NYC', valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(old_fact)], commit_time=june_1)
    second = memory_ledger.build_commit(
        first['commit_id'],
        [memory_ledger.supersede_fact('m1', by='m2', kind='contradict', valid_interval={'valid_to': june_2})],
        commit_time=june_2,
    )

    past_truth = memory_ledger.fold_commits([first, second], valid_time=datetime(2026, 5, 1, tzinfo=timezone.utc))
    current_head = memory_ledger.fold_commits([first, second])

    assert 'm1' in past_truth
    assert 'm1' not in current_head


def test_diff_returns_typed_mutations_between_parent_child():
    first = memory_ledger.build_commit(
        None,
        [memory_ledger.add_fact(_fact('m1', 'Lives in NYC'))],
        commit_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    mutation = memory_ledger.supersede_fact('m1', by='m2', kind='contradict')
    second = memory_ledger.build_commit(
        first['commit_id'],
        [mutation],
        commit_time=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    assert memory_ledger.diff(first, second) == [mutation]


def test_append_commit_to_history_is_idempotent_for_same_commit():
    state = {'current_head_commit_id': None}
    commits = {}
    mutations = [memory_ledger.add_fact(_fact('m1', 'Lives in NYC'))]

    first = memory_ledger.append_commit_to_history(state, commits, None, mutations)
    second = memory_ledger.append_commit_to_history(state, commits, first['commit']['parent_commit_id'], mutations)

    assert first['applied'] is True
    assert second['applied'] is False
    assert len(commits) == 1


def test_append_commit_to_history_rejects_sibling_heads():
    state = {'current_head_commit_id': None}
    commits = {}
    parent = None

    first = memory_ledger.append_commit_to_history(
        state,
        commits,
        parent,
        [memory_ledger.add_fact(_fact('m1', 'Lives in NYC'))],
    )

    try:
        memory_ledger.append_commit_to_history(
            state,
            commits,
            parent,
            [memory_ledger.add_fact(_fact('m2', 'Lives in SF'))],
        )
    except memory_ledger.HeadConflict as exc:
        assert exc.expected_parent == parent
        assert exc.current_head == first['commit']['commit_id']
    else:
        raise AssertionError('Expected same-parent sibling append to fail')

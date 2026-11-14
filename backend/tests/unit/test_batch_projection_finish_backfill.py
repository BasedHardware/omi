"""Hermetic stamp/checkpoint contract; real queries also have emulator coverage."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_projection_finish import PROJECTION_FINISH_DUE_FIELD as DUE
from database.batch_pipeline_projection_finish_backfill import (
    BACKFILL_VERSION,
    backfill_complete,
    backfill_ref,
    stamp_page,
)
from scripts import batch_pipeline_projection_finish_backfill as cli
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


def fixture():
    client = StrictFirestore(
        {
            ('batch_pipeline_dev_results', 'a'): {'projection_state': 'persisted'},
            ('batch_pipeline_dev_results', 'b'): {'projection_state': 'ready', DUE: 900.0},
            ('batch_pipeline_dev_results', 'c'): {'projection_state': 'completed'},
        }
    )
    store = SimpleNamespace(
        client=client, namespace='batch_pipeline_dev', projection_page=Mock(return_value=(['a', 'b', 'c'], None))
    )
    return store


def test_dry_run_and_atomic_checkpoint_use_strict_read_before_write_fixture():
    store = fixture()
    assert stamp_page(store, 100.0)['missing'] == 1
    assert not backfill_ref(store.client, store.namespace).get().exists
    assert stamp_page(store, 100.0, apply=True) == {
        'complete': True,
        'scanned': 3,
        'missing': 1,
        'stamped': 1,
    }
    rows = store.client.rows
    assert rows[('batch_pipeline_dev_results', 'a')][DUE] == 100.0
    assert rows[('batch_pipeline_dev_results', 'b')][DUE] == 900.0
    assert DUE not in rows[('batch_pipeline_dev_results', 'c')]
    assert backfill_complete(store.client, store.namespace)
    assert stamp_page(store, 200.0, apply=True)['scanned'] == 0


def test_apply_reads_the_page_in_one_batch_get_inside_the_transaction():
    store = fixture()
    batch_get = Mock(wraps=store.client.get_all)
    store.client.get_all = batch_get
    assert stamp_page(store, 100.0, apply=True)['stamped'] == 1
    assert batch_get.call_count == 1
    (references,), keywords = batch_get.call_args
    assert [reference.id for reference in references] == ['a', 'b', 'c']
    assert keywords['transaction'] is store.client.transactions[-1]


def test_apply_with_an_empty_page_issues_no_batch_get():
    store = fixture()
    store.projection_page.return_value = ([], None)
    batch_get = Mock(wraps=store.client.get_all)
    store.client.get_all = batch_get
    assert stamp_page(store, 100.0, apply=True) == {'complete': True, 'scanned': 0, 'missing': 0, 'stamped': 0}
    batch_get.assert_not_called()


def test_full_page_resumes_shared_checkpoint():
    store = fixture()
    store.projection_page.return_value = (['a'], (1.0, 'a'))
    assert not stamp_page(store, 100.0, size=1, apply=True)['complete']
    store.projection_page.return_value = ([], None)
    assert stamp_page(store, 200.0, size=1, apply=True)['complete']
    store.projection_page.assert_called_with(1, after=(1.0, 'a'), states=('persisted', 'ready'))


@pytest.mark.parametrize(
    'marker',
    [{}, {'complete': True}, {'version': 0, 'complete': True}, {'version': BACKFILL_VERSION, 'complete': False}],
)
def test_only_current_version_complete_marker_is_trusted(marker):
    store = fixture()
    ref = backfill_ref(store.client, store.namespace)
    store.client.rows[ref.path] = marker
    assert not backfill_complete(store.client, store.namespace)


@pytest.mark.parametrize(
    'arguments',
    [
        ['--stage', 'prod', '--apply'],
        ['--stage', 'prod', '--apply', '--confirm-writers-deployed'],
        ['--stage', 'dev', '--max-pages', '2'],
        ['--stage', 'dev', '--page-size', '201'],
        ['--stage', 'dev', '--max-pages', '0'],
    ],
)
def test_cli_rejects_unsafe_or_unbounded_invocation_before_opening_store(monkeypatch, arguments):
    monkeypatch.delenv('GCP_AGENT_TIER', raising=False)
    monkeypatch.setattr(cli.sys, 'argv', ['backfill', *arguments])
    constructor = Mock()
    monkeypatch.setattr(cli, 'FirestoreStore', constructor)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    constructor.assert_not_called()

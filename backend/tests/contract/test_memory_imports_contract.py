"""Dual-backend contract for memory imports (ADR-0044 facade + ADR-0002 store port).

`database/memory_imports.py` is the landing zone for a bulk import: the client POSTs batches of at most
100 items, each batch writes one content-addressed artifact per item and then folds its outcome into a
single per-run counter document. That counter document is the import's progress — it is what the run
status endpoint reports and what tells a user whether their several-thousand-item export finished.

    atomic_field_ops   `run_ref.set({'artifact_count': Increment(created), 'deduped_count':
                       Increment(deduped), ...}, merge=True)`. Increment is the only reason a run
                       spanning twenty batches can report a total: each batch knows what IT wrote and
                       nothing else. Translated as an assignment, the run document would end up holding
                       the LAST batch's numbers — a user importing 2,000 items would watch the counter
                       climb and then fall back to 100, and a run whose final batch was fully deduped
                       would report `artifact_count: 0` for an import that stored everything. Translated
                       as an append or a double-apply, the count would exceed the artifacts that exist,
                       and the run would never look complete.

                       Increment also has to survive `merge=True` alongside plain fields in the SAME
                       payload (`updated_at` is a literal in that dict). A backend that applied the
                       whole payload as a document merge would store the sentinel object itself, and the
                       counter would stop being a number.

The dedup branch is covered with it, because the counters are meaningless without it: the module calls
`create()` and treats `AlreadyExists`/`Conflict` as "seen before". Firestore raises
``google.api_core.exceptions.AlreadyExists``; Mongo raises ``DuplicateKeyError``, which the adapter maps
to the neutral ``errors.AlreadyExists`` and the facade re-raises as google's. If any link in that chain
broke, a re-import would not dedup — it would 500 mid-batch, and the artifacts already written would be
counted twice on the retry.

`db_client` is threaded explicitly (routers/memories.py passes `database._client.db`), so these tests
pass the same lazy handle the router does; ``bind_store`` has pointed it at this backend's client.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

NOW = datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)


@pytest.fixture
def imports(bind_store):
    """One user, one deterministic run id, and a teardown that removes both import collections."""
    run = uuid.uuid4().hex[:8]
    uid = f'imp-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for collection in ('memory_import_artifacts', 'memory_import_runs'):
        for document in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(document.path)


def _request(imports, items, **overrides):
    from models.memory_imports import MemoryImportBatchItem, MemoryImportBatchRequest

    payload = {
        'source_type': 'Gmail-Export',
        'import_run_id': f"run-{imports['run']}",
        'source_account_hash': f"acct-{imports['run']}",
        'importer_version': 'v1',
        'extractor_version': 'x1',
        'items': [MemoryImportBatchItem(**item) for item in items],
    }
    payload.update(overrides)
    return MemoryImportBatchRequest(**payload)


def _ingest(imports, items, *, now=NOW, **overrides):
    import database._client as db_client_module
    from database.memory_imports import ingest_memory_import_batch

    # The same handle routers/memories.py passes: `getattr(db_client_module, 'db', None)`.
    return ingest_memory_import_batch(
        imports['uid'], _request(imports, items, **overrides), db_client=db_client_module.db, now=now
    ).response


def _run_doc(imports, run_id):
    stored = imports['store'].get(f"users/{imports['uid']}/memory_import_runs/{run_id}")
    return stored.data if stored is not None and stored.exists else None


def _artifacts(imports):
    return imports['store'].query(f"users/{imports['uid']}/memory_import_artifacts")


def _items(count, *, prefix='note'):
    return [
        {'external_id': f'{prefix}-{index}', 'title': f'Title {index}', 'snippet': f'Snippet {index}'}
        for index in range(count)
    ]


# --- atomic field ops -------------------------------------------------------------------------------


def test_the_first_batch_counts_what_it_created(imports):
    """Increment applied to a run document that has just been created with zeroes: the counter must read
    the batch size, not the sentinel and not nothing."""
    response = _ingest(imports, _items(3))

    assert (response.artifacts_created, response.artifacts_deduped) == (3, 0)
    run = _run_doc(imports, response.run_id)
    assert run['artifact_count'] == 3
    assert run['deduped_count'] == 0


def test_successive_batches_add_up_instead_of_overwriting(imports):
    """The whole point of Increment. Three items, then two more under the same run id: the run must
    report five. An assignment would report two, and the user's progress bar would go backwards."""
    first = _ingest(imports, _items(3, prefix='a'))
    second = _ingest(imports, _items(2, prefix='b'))

    assert first.run_id == second.run_id, 'the run id is derived, so both batches land on one document'
    assert _run_doc(imports, second.run_id)['artifact_count'] == 5


def test_a_fully_deduped_batch_does_not_reset_the_total(imports):
    """`Increment(0)`. Re-sending a batch already stored must leave `artifact_count` where it was — an
    assignment would zero it, and a completed import would report that it stored nothing."""
    first = _ingest(imports, _items(3))
    repeat = _ingest(imports, _items(3))

    assert (repeat.artifacts_created, repeat.artifacts_deduped) == (0, 3)
    run = _run_doc(imports, repeat.run_id)
    assert run['artifact_count'] == 3, 'the created total survived a batch that created nothing'
    assert run['deduped_count'] == 3


def test_the_two_counters_advance_independently(imports):
    """A partially-overlapping batch: two items already seen, two new. Both increments are in the same
    merge payload, so a backend that applied only the last transform (or shared one value between them)
    shows up here and nowhere else."""
    _ingest(imports, _items(2))
    mixed = _ingest(imports, _items(4))

    assert (mixed.artifacts_created, mixed.artifacts_deduped) == (2, 2)
    run = _run_doc(imports, mixed.run_id)
    assert (run['artifact_count'], run['deduped_count']) == (4, 2)


def test_the_counters_stay_numbers_next_to_a_literal_field(imports):
    """`updated_at` is a plain string in the same `set(..., merge=True)` payload as the two sentinels. If
    the transform were stored rather than applied, the counter would be an object and the status endpoint
    would serialise garbage instead of a number."""
    response = _ingest(imports, _items(2))

    run = _run_doc(imports, response.run_id)
    assert isinstance(run['artifact_count'], int) and isinstance(run['deduped_count'], int)
    assert run['updated_at'] == NOW.isoformat()


def test_the_merge_does_not_wipe_the_run_identity(imports):
    """The counter write is a merge onto the document `create()` seeded with the run's identity — source
    type, importer version, status. A replacing write would leave a progress counter nobody can attribute
    to an import, and `status` would disappear from the run listing."""
    response = _ingest(imports, _items(2))

    run = _run_doc(imports, response.run_id)
    assert run['uid'] == imports['uid']
    assert run['source_type'] == 'gmail_export', 'the normalised form the module stores'
    assert run['importer_version'] == 'v1'
    assert run['extractor_version'] == 'x1'
    assert run['status'] == 'received'
    assert run['started_at'] == NOW.isoformat()


def test_a_later_batch_does_not_restart_the_run(imports):
    """The second batch's `create()` collides and is swallowed. If it were allowed to overwrite, the run
    would be reborn with `artifact_count: 0` and `started_at` moved forward on every batch."""
    later = datetime(2026, 7, 15, 9, 45, tzinfo=timezone.utc)

    first = _ingest(imports, _items(2, prefix='a'))
    _ingest(imports, _items(1, prefix='b'), now=later)

    run = _run_doc(imports, first.run_id)
    assert run['started_at'] == NOW.isoformat(), 'the run kept its original start'
    assert run['updated_at'] == later.isoformat(), 'but the merge moved the freshness stamp'
    assert run['artifact_count'] == 3


# --- dedup: the branch the counters are computed from -----------------------------------------------


def test_the_same_content_lands_on_one_artifact(imports):
    """Artifact ids are content-addressed, so a re-import must not create a second row. What the user
    would see otherwise is their mail archive duplicated on every retry of a failed upload."""
    _ingest(imports, _items(3))
    _ingest(imports, _items(3))

    assert len(_artifacts(imports)) == 3


def test_the_dedup_write_refreshes_without_discarding_the_artifact(imports):
    """The `except AlreadyExists` path re-sets three fields with `merge=True`. It has to MERGE: the title
    and snippet are the only copy of the imported content the backend keeps, and losing them would empty
    the imported item while leaving it counted."""
    later = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)

    _ingest(imports, _items(1))
    # Captured, not spelled out: the artifact body is serialised by pydantic (`model_dump(mode='json')`,
    # which renders UTC as 'Z'), while the run document writes a bare `.isoformat()`. Both backends agree
    # on each; hard-coding one format here would assert the serialiser, not the store.
    created_at = _artifacts(imports)[0].data['created_at']
    _ingest(imports, _items(1), now=later)

    artifact = _artifacts(imports)[0].data
    assert artifact['title'] == 'Title 0'
    assert artifact['snippet'] == 'Snippet 0'
    assert artifact['content_hash']
    assert artifact['source_state'] == 'active'
    assert artifact['updated_at'] == later.isoformat()
    assert artifact['created_at'] == created_at, 'the dedup merge must not restamp creation'


def test_a_second_run_reuses_the_artifact_and_reclaims_it(imports):
    """Two different runs over the same source: the artifact is deduped against the first run, and the
    merge repoints `run_id` at the second so the newer import owns it."""
    first = _ingest(imports, _items(1))
    second = _ingest(imports, _items(1), import_run_id=f"other-{imports['run']}")

    assert first.run_id != second.run_id
    assert second.artifacts_deduped == 1
    assert len(_artifacts(imports)) == 1
    assert _artifacts(imports)[0].data['run_id'] == second.run_id
    assert _run_doc(imports, second.run_id)['deduped_count'] == 1
    assert _run_doc(imports, first.run_id)['artifact_count'] == 1, 'the first run keeps its own tally'


def test_distinct_content_is_never_folded_together(imports):
    """The other half of content addressing: two genuinely different items must survive as two rows, or
    an import silently drops mail."""
    response = _ingest(imports, _items(2))

    assert response.artifacts_created == 2
    assert len({document.id for document in _artifacts(imports)}) == 2


def test_an_optional_field_left_empty_round_trips_as_null(imports):
    """`redacted_body` is None under the default 'summary' storage mode. A backend that dropped the key
    instead of storing null would make the redaction status unreadable — the field that says whether the
    full body was retained is the one the privacy review reads."""
    _ingest(imports, _items(1))

    artifact = _artifacts(imports)[0].data
    assert 'redacted_body' in artifact and artifact['redacted_body'] is None
    assert artifact['redaction_status'] == 'title_snippet_only'


def test_the_full_body_mode_stores_the_content_it_was_given(imports, monkeypatch):
    """The other storage mode, so the same document shape is proven with the optional field populated."""
    from database.memory_imports import MEMORY_IMPORT_BODY_STORAGE_MODE_ENV

    monkeypatch.setenv(MEMORY_IMPORT_BODY_STORAGE_MODE_ENV, 'full')

    _ingest(imports, [{'external_id': 'full-0', 'title': 'T', 'snippet': 'S', 'content': 'the whole body'}])

    artifact = _artifacts(imports)[0].data
    assert artifact['redacted_body'] == 'the whole body'
    assert artifact['redaction_status'] == 'importer_full_excerpt'


def test_an_empty_batch_still_registers_the_run(imports):
    """Zero items: the run document must exist with both counters at zero, so the client polling it gets
    a run rather than a 404 it would read as a lost import."""
    response = _ingest(imports, [])

    assert (response.artifacts_received, response.artifacts_created) == (0, 0)
    run = _run_doc(imports, response.run_id)
    assert (run['artifact_count'], run['deduped_count']) == (0, 0)
    assert _artifacts(imports) == []

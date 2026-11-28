"""create_import_job read ``job_data['id']`` directly, so a payload without an id
raised KeyError and a caller-supplied id reached Firestore unchecked -- a '/' in it
silently retargets the document path. get_import_jobs passed the caller's limit
straight through, so 0 or a negative value raised InvalidArgument and a huge value
built an unbounded query. The readers also accepted a blank uid.

These tests are hermetic: ``import_jobs.db`` is swapped for a recording fake, so no
Firestore client and no network are involved.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import database.import_jobs as import_jobs


def _install_fake_db(monkeypatch):
    state = SimpleNamespace(limits=[], sets=[], updates=[], deletes=[], ids=[])
    collection = MagicMock()

    def _document(doc_id):
        state.ids.append(doc_id)
        return SimpleNamespace(
            id=doc_id,
            set=lambda data, **kwargs: state.sets.append((doc_id, data)),
            update=lambda data, **kwargs: state.updates.append((doc_id, data)),
            delete=lambda: state.deletes.append(doc_id),
            get=lambda **kwargs: SimpleNamespace(exists=False),
        )

    query = MagicMock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.side_effect = lambda n: (state.limits.append(n), query)[1]
    query.stream.return_value = iter([])

    collection.document.side_effect = _document
    collection.where.return_value = query

    fake = MagicMock()
    fake.collection.return_value = collection
    monkeypatch.setattr(import_jobs, 'db', fake)
    return state


def _expect_value_error(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('expected ValueError')


def test_create_import_job_missing_id_raises_value_error(monkeypatch):
    _install_fake_db(monkeypatch)
    _expect_value_error(lambda: import_jobs.create_import_job({'uid': 'u1'}))


def test_create_import_job_rejects_path_traversal_and_blank_ids(monkeypatch):
    _install_fake_db(monkeypatch)
    for bad in ('../other', 'a/b', 'a\\b', 'a\x00b', '   ', '', None):
        _expect_value_error(lambda bad=bad: import_jobs.create_import_job({'id': bad}))


def test_create_import_job_writes_the_cleaned_id(monkeypatch):
    state = _install_fake_db(monkeypatch)

    job_id = import_jobs.create_import_job({'id': '  job-1  ', 'uid': 'u1'})

    assert job_id == 'job-1'
    assert state.ids == ['job-1']
    assert state.sets == [('job-1', {'id': 'job-1', 'uid': 'u1'})]


def test_get_import_jobs_clamps_limit_to_firestore_safe_bounds(monkeypatch):
    state = _install_fake_db(monkeypatch)

    import_jobs.get_import_jobs('u1', 0)
    import_jobs.get_import_jobs('u1', -5)
    import_jobs.get_import_jobs('u1', 10**9)
    import_jobs.get_import_jobs('u1')
    import_jobs.get_import_jobs('u1', 'nonsense')

    assert state.limits == [1, 1, 1000, 50, 50]


def test_get_import_jobs_rejects_invalid_uid(monkeypatch):
    _install_fake_db(monkeypatch)
    for bad in ('', '   ', 'a/b', None, 7):
        _expect_value_error(lambda bad=bad: import_jobs.get_import_jobs(bad))


def test_writers_and_readers_reject_invalid_job_ids(monkeypatch):
    _install_fake_db(monkeypatch)
    _expect_value_error(lambda: import_jobs.update_import_job('a/b', {'status': 'x'}))
    _expect_value_error(lambda: import_jobs.get_import_job('../x'))
    _expect_value_error(lambda: import_jobs.delete_import_job(''))
    _expect_value_error(lambda: import_jobs.update_import_job_progress('a/b', {'processed_files': 1}))
    _expect_value_error(lambda: import_jobs.update_import_job_unless_cancelled('', {'status': 'x'}))


def test_update_import_job_progress_still_rejects_unknown_fields(monkeypatch):
    _install_fake_db(monkeypatch)

    try:
        import_jobs.update_import_job_progress('job-1', {'status': 'cancelled'})
    except ValueError as exc:
        assert 'not import job progress fields' in str(exc)
    else:
        raise AssertionError('expected ValueError')

"""Actual grouped cold SDK commits retain original admission and page fencing."""

import pytest
from google.cloud.firestore_v1.types import CommitRequest, BatchGetDocumentsRequest

from database.jobstore.authority import AuthorityRefused
from database.batch_privacy_attempt import TOKEN_FIELD
from database.jobstore.cold_batch import apply_rows
from database.jobstore.cold_purge import erase_recording
from database.privacy_fence.protocol import lock
from tests.integration.test_jobstore_handoff import context  # noqa: F401
from tests.integration.test_jobstore_provider_projection import lane  # noqa: F401
from tests.integration.test_jobstore_cold_sink import cold, terminal, unit  # noqa: F401
from tests.integration.test_jobstore_provider_handoff import upload, terminal as settle
from tests.integration.test_jobstore_cold_crashes import (
    test_actual_cold_commit_exit_replays_without_resurrection_or_lost_custody as crash_copy,
)

pytestmark = pytest.mark.integration


def track_commits(c, monkeypatch):
    api = c.handoff.client._firestore_api
    actual, commits = api.commit, []

    def commit(*args, **kwargs):
        request = CommitRequest(kwargs.get('request') or args[0])
        result = actual(*args, **kwargs)
        writes = [w for w in request.writes if w.update and 'cold_only' in w.update.fields]
        if writes:
            commits.append({w.update.fields['recording_id'].string_value for w in writes})
        return result

    monkeypatch.setattr(api, 'commit', commit)
    return commits


def test_actual_sdk_page_has_one_guarded_cold_commit_per_recording(cold, monkeypatch):
    c = cold
    commits = track_commits(c, monkeypatch)
    assert c.sink.page(limit=100) == len(c.rows)
    assert commits == [{c.view.identity}]
    expected = {}
    for row in c.rows:
        expected[c.sink.ref(row[2], row[3]).path] = row
    for path, row in expected.items():
        value = c.handoff.client.document(path).get().to_dict()
        assert value['seq'] == row[0] and value['body'] == row[6]
        assert value['original_deadlines'] == {'one': 20000, 'two': 20000}
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq,committed_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (c.rows[-1][0], c.rows[-1][0])


def test_actual_bulk_read_has_no_sql_slot_or_owner_guard(cold, monkeypatch):
    c = cold
    api = c.handoff.client._firestore_api
    actual, reads = api.batch_get_documents, []
    actual_commit, writes = api.commit, []
    paths = {c.sink.ref(r[2], r[3]).path for r in c.rows}
    family_reads = []

    def free():
        with c.handoff.pool.connection(timeout=2) as one, c.handoff.pool.connection(timeout=2) as two:
            with one.transaction():
                one.execute("SET LOCAL lock_timeout='2s'")
                lock(one, c.rows[0][5], exclusive=True)
            assert two.execute('SELECT 1').fetchone() == (1,)

    def get(*args, **kwargs):
        request = BatchGetDocumentsRequest(kwargs.get('request') or args[0])
        requested = [path.partition('/documents/')[2] for path in request.documents]
        family_reads.extend(path for path in requested if path.split('/')[0] == 'jobstore_handoffs')
        if len(requested) > 1 and set(requested) == paths:
            free()
            reads.append(len(request.documents))
        return actual(*args, **kwargs)

    def commit(*args, **kwargs):
        request = CommitRequest(kwargs.get('request') or args[0])
        if any(w.update and 'cold_only' in w.update.fields for w in request.writes):
            free()
            writes.append(True)
        return actual_commit(*args, **kwargs)

    monkeypatch.setattr(api, 'batch_get_documents', get)
    monkeypatch.setattr(api, 'commit', commit)
    c.sink.page(limit=100)
    assert reads == [len(paths)]
    assert len(family_reads) == len(paths) + 4
    assert writes == [True]


def test_grouped_page_never_mixes_original_recording_admissions(cold, context, monkeypatch):
    c = cold
    adapter, binding, _, _ = upload(context, monkeypatch, count=1)
    adapter.deliver(binding.job_id)
    (job,) = adapter.units.claim(1, now=201, lease_seconds=30, backlog_share=0)
    assert settle(adapter, job)
    commits = track_commits(c, monkeypatch)
    with c.handoff.pool.connection() as conn:
        count = conn.execute(
            'SELECT count(*) FROM queue_journal WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone()[0]
    assert c.sink.page(limit=100) == count
    assert len(commits) == 2 and {next(iter(s)) for s in commits} == {c.view.identity, binding.job_id}
    assert all(len(s) == 1 for s in commits)


def test_changed_late_journal_body_refuses_page_before_any_cold_write(cold, monkeypatch):
    c = cold
    commits = track_commits(c, monkeypatch)
    bad = list(c.rows[-1])
    bad[6] = {**bad[6], 'namespace': 'foreign'}
    with pytest.raises(AuthorityRefused, match='version/payload'):
        apply_rows(c.sink, [*c.rows[:-1], tuple(bad)], timeout=1.5)
    assert not commits
    assert not any(c.sink.ref(r[2], r[3]).get().exists for r in c.rows)


@pytest.mark.parametrize('change', ['token', 'epoch'])
def test_grouped_writing_transaction_rechecks_real_authority(cold, monkeypatch, change):
    c = cold
    actual = c.sink.admit_original
    commits = track_commits(c, monkeypatch)

    def admit(original):
        admission = actual(original)
        if change == 'token':
            c.handoff.client.collection('batch_pipeline_privacy').document(original['owner_key']).update(
                {TOKEN_FIELD: 'successor'}
            )
        else:
            c.handoff.authority.ref.update({'epoch': 4})
        return admission

    monkeypatch.setattr(c.sink, 'admit_original', admit)
    with pytest.raises(AuthorityRefused):
        c.sink.page(limit=100)
    assert not commits


def test_grouped_delayed_page_only_acks_actual_erasure_barrier(cold, monkeypatch):
    c = cold
    c.sink.page(limit=100)
    retained, cid, identity, manifest = terminal(c)
    with unit(c) as authority:
        retained.retire_private(c.uid, identity, manifest, authority, conversation=cid)
        erase_recording(retained, c.uid, identity, manifest, authority, conversation=cid)
    commits = track_commits(c, monkeypatch)
    apply_rows(c.sink, list(reversed(c.rows)), timeout=1.5)
    assert not commits and not any(c.sink.ref(r[2], r[3]).get().exists for r in c.rows)


def test_reversed_group_keeps_latest_original_version_without_advancing_checkpoint(cold):
    c = cold
    apply_rows(c.sink, list(reversed(c.rows)), timeout=1.5)
    latest = {}
    for row in c.rows:
        latest[c.sink.ref(row[2], row[3]).path] = row
    for path, row in latest.items():
        value = c.handoff.client.document(path).get().to_dict()
        assert value['seq'] == row[0] and value['body'] == row[6]
    with c.handoff.pool.connection() as conn:
        assert conn.execute(
            'SELECT applied_seq FROM queue_authority WHERE namespace=%s', (c.handoff.ticket.namespace,)
        ).fetchone() == (0,)


@pytest.mark.parametrize('gap', ['before', 'after'])
def test_actual_group_commit_exit_retains_whole_original_recording_custody(cold, gap):
    c = cold
    crash_copy(c, 'copy', gap, copy_limit=100)
    latest = {}
    for row in c.rows:
        latest[c.sink.ref(row[2], row[3]).path] = row
    for path, row in latest.items():
        value = c.handoff.client.document(path).get().to_dict()
        assert value['seq'] == row[0] and value['body'] == row[6]

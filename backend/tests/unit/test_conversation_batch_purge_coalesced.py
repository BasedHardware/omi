"""Shared traversal parity/read growth. Lease and transaction races use the emulator suite."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from database import batch_pipeline_conversation_purge as purge
from database.batch_pipeline_privacy import privacy_owner_key
from tests.unit.test_conversation_batch_purge_resumable import BatchPlane
from tests.unit.test_conversation_delete_gate_wait import _Client, _Ref, UID

NS = 'batch_pipeline_prod'
KEY = privacy_owner_key(UID)


class Progress:
    def __init__(self, members=None):
        self.position, self.journals, self.members = {}, {}, members
        self.checkpoints = 0
        self.stop = None

    def checkpoint(self, position, *, add_segments=None):
        if add_segments:
            ns, ids = add_segments
            self.journals.setdefault(ns, set()).update(ids)
        self.position = dict(position)
        self.checkpoints += 1

    def segments(self, namespace):
        if self.members is not None:
            return set().union(*(member.segments(namespace) for member in self.members.values()))
        return set(self.journals.get(namespace, set()))

    def pending_segments(self, namespace, limit):
        return sorted(self.segments(namespace))[:limit]

    def segments_done(self, namespace, segment_ids):
        if self.members is not None:
            for member in self.members.values():
                member.segments_done(namespace, segment_ids)
        else:
            self.journals.setdefault(namespace, set()).difference_update(segment_ids)

    @contextmanager
    def unit(self):
        yield SimpleNamespace(remote=lambda call, **kwargs: call(), fence=lambda txn: None)

    def settle_stuck(self, resolve):
        pass

    def expired(self):
        return self.stop is not None and self.stop(self)


def seed(monkeypatch, *, count=5, unmatched=350):
    client = _Client()
    plane = BatchPlane(monkeypatch, client)
    for n in range(count):
        cid = f'c{n}'
        client.collection('users').document(UID).collection('deleted_conversations').document(cid).set({'id': cid})
        plane.add('jobs', f'mine-{n}', conversation_id=cid, priority=1)
        plane.add('results', f'mine-{n}', projection={'conversation_id': cid})
        plane.add('artifacts', f'a-{n}', segment_id=f'mine-{n}', uri=f'gs://test/a-{n}')
        plane.add('intakes', f'i-{n}', segment_ids=[f'mine-{n}'])
        plane.add('artifacts', f'parked-{n}', segment_id=f'mine-{n}', owner_key='corrupt')
    # Shared nested provenance: one erasure, a journal for each member.
    plane.add('results', 'overlap', source_conversation_ids=[f'c{n}' for n in range(count)])
    plane.add('projections', 'overlap-dependent', segment_id='overlap')
    for table in (*purge.DISCOVER_TABLES, *purge.DEPENDENT_TABLES):
        for n in range(unmatched):
            plane.add(table, f'z-unmatched-{n:04}', conversation_id='retained', priority=1)
    return client, plane


def test_five_deletions_share_owner_pages_and_unmatched_result_gets(monkeypatch):
    client, plane = seed(monkeypatch)
    original = {key: dict(value) for key, value in client.docs.items()}
    result_gets = []
    get = _Ref.get

    def counted_get(ref, *args, **kwargs):
        if '_results/z-unmatched-' in ref.path:
            result_gets.append(ref.path)
        return get(ref, *args, **kwargs)

    monkeypatch.setattr(_Ref, 'get', counted_get)
    members = {f'c{n}': Progress() for n in range(5)}
    progress = Progress(members)
    purge.purge_conversations(UID, members, progress, firestore_client=client, delete_uri=lambda *args: None)
    shared_reads = len(plane.reads)
    assert len(result_gets) == 350
    result_gets.clear()
    shared_docs = dict(client.docs)
    shared_erased = sorted(plane.erased)
    assert all(not member.segments(NS) for member in members.values())
    assert len([read for read in plane.reads if read[:2] == (NS, 'jobs')]) == 5
    # Pages grow with owner rows (4 nonempty pages + EOF), not five members.
    assert shared_reads < 70
    client.docs = original
    plane.reads.clear()
    plane.erased.clear()
    for cid in members:
        purge.purge_conversation(UID, cid, Progress(), firestore_client=client, delete_uri=lambda *args: None)
    assert dict(client.docs) == shared_docs
    assert sorted(set(plane.erased)) == sorted(set(shared_erased))
    assert len(result_gets) == 5 * 350
    assert len(plane.reads) >= shared_reads * 4
    assert len([read for read in plane.reads if read[:2] == (NS, 'jobs')]) == 25


def test_crash_during_association_fanout_replays_page_before_any_binding_erase(monkeypatch):
    client, plane = seed(monkeypatch, unmatched=0)
    members = {f'c{n}': Progress() for n in range(5)}
    progress = Progress(members)
    saved = members['c2'].checkpoint

    def crash(*args, **kwargs):
        raise RuntimeError('crash between member association writes')

    members['c2'].checkpoint = crash
    with pytest.raises(RuntimeError, match='association'):
        purge.purge_conversations(UID, members, progress, firestore_client=client, delete_uri=lambda *args: None)
    assert plane.erased == []
    assert progress.position.get('after') is None
    members['c2'].checkpoint = saved
    purge.purge_conversations(UID, members, progress, firestore_client=client, delete_uri=lambda *args: None)
    assert plane.doc('artifacts', 'a-2') is None
    assert plane.doc('projections', 'overlap-dependent') is None


def test_handback_after_first_binding_erase_never_strands_segment_dependents(monkeypatch):
    client, plane = seed(monkeypatch, unmatched=0)
    members = {f'c{n}': Progress() for n in range(5)}
    progress = Progress(members)
    original = progress.segments_done

    def interrupted(namespace, ids):
        original(namespace, ids)
        raise RuntimeError('stop after binding and journal deletion')

    progress.segments_done = interrupted
    with pytest.raises(RuntimeError, match='binding'):
        purge.purge_conversations(UID, members, progress, firestore_client=client, delete_uri=lambda *args: None)
    # Each member resumes its original empty cursor with its OWN remaining bindings.
    for cid, member in members.items():
        purge.purge_conversation(UID, cid, member, firestore_client=client, delete_uri=lambda *args: None)
    for n in range(5):
        assert plane.doc('artifacts', f'a-{n}') is None
        assert plane.doc('intakes', f'i-{n}') is None
        assert plane.doc('artifacts', f'parked-{n}') is None


def test_switch_defaults_on_and_explicit_false_survives_global_parser_mode(monkeypatch):
    from database import batch_pipeline_conversation_purge_scans as scans

    monkeypatch.delenv(scans.SWITCH, raising=False)
    assert scans.enabled()
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    for value in ('false', 'off', '0', 'no', ' FALSE '):
        monkeypatch.setenv(scans.SWITCH, value)
        assert not scans.enabled()


def test_group_wal_sweep_hands_off_before_metadata_even_with_many_originals(monkeypatch):
    client, plane = seed(monkeypatch, count=2, unmatched=0)
    members = {'c0': Progress(), 'c1': Progress()}
    progress = Progress(members)
    progress.stop = lambda p: p.checkpoints >= 1
    listed = []

    def originals(uid, cid, *, limit):
        listed.append(cid)
        return [f'gs://test/record-wal/{cid}/{i}#1' for i in range(limit)]

    monkeypatch.setattr(purge, 'conversation_objects', originals)
    with pytest.raises(purge.PurgeCheckpointed):
        purge.purge_conversations(UID, members, progress, firestore_client=client)
    assert listed == ['c0']
    assert len(plane.objects) == purge.UNIT_MAX_ROWS
    assert plane.erased == []  # WAL units can yield before metadata discovery.


def test_group_wal_sweep_resumes_and_erases_both_members_and_new_orphans(monkeypatch):
    client, plane = seed(monkeypatch, count=2, unmatched=0)
    members = {'c0': Progress(), 'c1': Progress()}
    progress = Progress(members)
    originals = {cid: {f'gs://test/record-wal/{cid}/first#1'} for cid in members}
    first = {cid: next(iter(uris)) for cid, uris in originals.items()}
    listed, erased = [], []

    def remaining(uid, cid, *, limit):
        listed.append(cid)
        return sorted(originals[cid])[:limit]

    def delete(uid, uri, **kwargs):
        plane.objects.append(uri)
        if '/record-wal/' in uri:
            cid = uri.split('/record-wal/')[1].split('/')[0]
            assert uri in originals[cid]  # never delete an already-erased generation
            originals[cid].remove(uri)
            erased.append(uri)

    from utils.batch_pipeline import retention

    monkeypatch.setattr(purge, 'conversation_objects', remaining)
    monkeypatch.setattr(retention, 'delete_batch_object', delete)
    progress.stop = lambda p: p.checkpoints >= 1
    with pytest.raises(purge.PurgeCheckpointed):
        purge.purge_conversations(UID, members, progress, firestore_client=client)
    assert erased == [first['c0']] and originals['c1']
    assert plane.erased == []
    # Re-list c0 too: an orphan arriving between runs is still owed even though
    # the previous generation's original was deleted before the interruption.
    late = 'gs://test/record-wal/c0/crash-orphan#2'
    originals['c0'].add(late)
    progress.stop = None
    listed.clear()
    purge.purge_conversations(UID, members, progress, firestore_client=client)
    assert set(listed) == set(members) and not any(originals.values())
    assert set(erased) == {*first.values(), late} and len(erased) == 3
    assert progress.position['ns'] == len(purge.NAMESPACES)
    assert all(not member.segments(NS) for member in members.values())
    for n in range(2):
        assert plane.doc('artifacts', f'a-{n}') is None
        assert plane.doc('artifacts', f'parked-{n}') is None
        assert plane.doc('intakes', f'i-{n}') is None

"""Hermetic repair contracts, using the strict transaction boundary fake."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts import repair_recovery_dead_letter_untitled as repair
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.conversations.deterministic_minimum import deterministic_minimum_title
from utils.conversations.recovery import verified_recovery_discard

UID = 'private-full-user-id'
CID = 'conversation-one'
JOB_ID = 'job-one'
JOB_PATH = (repair.JOBS, JOB_ID)
ROW_PATH = ('users', UID, 'conversations', CID)
TEXT = 'We need to move the release to Thursday. Alice will finish the deployment.'


def row(text=''):
    return {
        'source': 'omi',
        'status': 'completed',
        'discarded': False,
        'deleted': False,
        'finalization_status': 'dead_letter',
        'finalization_job_id': JOB_ID,
        'structured': {'title': '', 'overview': '', 'sections': [], 'action_items': [], 'events': []},
        'transcript_segments': [{'id': 's1', 'text': text, 'start': 0, 'end': 2}],
        'started_at': datetime(2026, 2, 1, tzinfo=timezone.utc),
        'finished_at': datetime(2026, 2, 1, tzinfo=timezone.utc),
    }


def job():
    return dict(repair.JOB_FILTERS, uid=UID, conversation_id=CID)


class Client(StrictFirestore):
    """Strict document transactions plus a separate discovery-only query double."""

    def transaction(self, **kwargs):
        return super().transaction()

    def collection(self, name):
        if name == repair.JOBS:
            return Query(self)
        return super().collection(name)


class Query:
    def __init__(self, client):
        self.client = client
        self.filters = []
        self.after = ''
        self.take = 200

    def document(self, name):
        return self.client.document(f'{repair.JOBS}/{name}')

    def where(self, *, filter):
        assert filter.op_string == '=='
        self.filters.append((filter.field_path, filter.value))
        return self

    def order_by(self, name):
        assert name == '__name__'
        return self

    def limit(self, take):
        self.take = take
        return self

    def start_after(self, cursor):
        self.after = cursor['__name__'].path[-1]
        return self

    def stream(self):
        snapshots = []
        for path, data in sorted(self.client.rows.items()):
            if len(path) != 2 or path[0] != repair.JOBS or path[-1] <= self.after:
                continue
            if all(data.get(k) == v for k, v in self.filters):
                snapshots.append(SimpleNamespace(id=path[-1], to_dict=lambda data=data: deepcopy(data)))
        return snapshots[: self.take]


def setup(tmp_path, *, apply=False, kept=False, text='', name='run'):
    client = Client({JOB_PATH: job(), ROW_PATH: row(text)})
    runtime = repair.Runtime(
        client,
        decode=lambda data, uid: data['transcript_segments'],
        protections=lambda ref, data, job, tx: None,
        converge=lambda uid, cid: None,
    )
    config = {'apply': apply, 'include_kept_titles': kept, 'uids': [], 'conversation_ids': [], 'rollback': None}
    log = repair.RunLog(tmp_path / name, config)
    return client, runtime, log


def evaluate(runtime, log):
    result = repair.evaluate(runtime, log, JOB_ID, limiter=repair.RateLimiter(100000))
    log.finish(result, result['outcome'])
    return result


@pytest.mark.parametrize(
    ('change', 'reason'),
    [
        ({'deleted': True}, 'deleted'),
        ({'status': 'processing'}, 'not_completed'),
        ({'discarded': True}, 'not_visible'),
        ({'discarded': None}, 'not_visible'),
        ({'finalization_status': 'completed'}, 'not_dead_letter'),
        ({'finalization_job_id': 'new-job'}, 'job_binding_changed'),
        ({'structured': {'title': '', 'overview': 'rich'}}, 'rich_structure'),
        ({'structured': {'title': 'user title'}}, 'nonempty_title'),
        ({'structured': None}, 'invalid_structure'),
        ({'user_title': 'my notes'}, 'user_title'),
        ({'photos': [{}]}, 'photos'),
        ({'has_photos': True}, 'photos'),
        ({'sync_relevance_user_kept': True}, 'user_kept'),
        ({'starred': True}, 'user_curated'),
        ({'folder_user_set': True}, 'user_curated'),
        ({'sync_live_target': True}, 'user_curated'),
        ({'visibility': 'shared'}, 'user_curated'),
    ],
)
def test_eligibility_predicate(tmp_path, change, reason):
    client, runtime, log = setup(tmp_path, apply=True)
    client.rows[ROW_PATH].update(change)
    assert evaluate(runtime, log)['outcome'] == reason
    assert not client.transactions


def test_missing_conversation(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    del client.rows[ROW_PATH]
    assert evaluate(runtime, log)['outcome'] == 'missing_conversation'


def test_job_no_longer_candidate(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    client.rows[JOB_PATH]['status'] = 'completed'
    assert evaluate(runtime, log)['outcome'] == 'job_not_candidate'


def test_release_probe(tmp_path, monkeypatch):
    _, runtime, log = setup(tmp_path, apply=True)
    monkeypatch.setattr(repair, 'is_release_probe_uid', lambda uid: True)
    assert evaluate(runtime, log)['outcome'] == 'release_probe'


def test_protected_content_predicate(tmp_path, monkeypatch):
    _, runtime, log = setup(tmp_path, apply=True)
    monkeypatch.setattr(repair, 'structured_has_protected_content', lambda *args: True)
    assert evaluate(runtime, log)['outcome'] == 'protected_structure'


def test_subcollection_photos(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    runtime.protections = lambda *args: 'photos'
    assert evaluate(runtime, log)['outcome'] == 'photos'
    assert not client.transactions


def test_class_r_writes_verified_discard_and_only_two_fields(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    original = deepcopy(client.rows[ROW_PATH])
    calls = []
    runtime.converge = lambda uid, cid: calls.append((uid, cid))
    result = evaluate(runtime, log)
    assert result['class'] == 'R' and result['outcome'] == 'written'
    current = client.rows[ROW_PATH]
    assert verified_recovery_discard(current['discarded'], current['relevance_decision'])
    assert current == dict(original, discarded=True, relevance_decision=current['relevance_decision'])
    assert set(client.transactions[0].updates[0][1]) == {'discarded', 'relevance_decision'}
    assert calls == [(UID, CID)]
    assert log.unseal(result['before'])['relevance_decision'] == {'present': False}


def test_class_k_title_matches_shared_helper(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text=TEXT)
    result = evaluate(runtime, log)
    expected = deterministic_minimum_title(SimpleNamespace(transcript_segments=[SimpleNamespace(text=TEXT)]))
    assert result['class'] == 'K' and result['outcome'] == 'written'
    # Strict fixture stores dotted patches literally; the production SDK applies
    # the field path. Assert the exact SDK patch rather than alter that fixture.
    assert client.transactions[0].updates[0][1] == {'structured.title': expected}
    assert client.rows[ROW_PATH]['discarded'] is False


def test_class_k_disabled(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True, text=TEXT)
    result = evaluate(runtime, log)
    assert result['class'] == 'K' and result['outcome'] == 'kept_titles_disabled'
    assert not client.transactions


def test_dry_run_writes_nothing_including_projection(tmp_path):
    client, runtime, log = setup(tmp_path)
    runtime.converge = lambda *args: pytest.fail('dry-run projection write')
    original = deepcopy(client.rows)
    summary = repair.run(runtime, log, workers=2)
    assert summary['classes']['R'] == 1
    assert client.rows == original and not client.transactions


@pytest.mark.parametrize('mutation', ['transcript', 'restore', 'job', 'structure', 'photos'])
def test_cas_aborts_changed_row(tmp_path, mutation):
    client, runtime, log = setup(tmp_path, apply=True)
    original = client.transaction

    def transaction(**kwargs):
        if mutation == 'transcript':
            client.rows[ROW_PATH]['transcript_segments'][0]['text'] = TEXT
        elif mutation == 'restore':
            client.rows[ROW_PATH]['sync_relevance_user_kept'] = True
        elif mutation == 'job':
            client.rows[JOB_PATH]['status'] = 'completed'
        elif mutation == 'structure':
            client.rows[ROW_PATH]['structured']['title'] = 'new title'
        else:
            runtime.protections = lambda *args: 'photos'
        return original(**kwargs)

    client.transaction = transaction
    assert evaluate(runtime, log)['outcome'] != 'written'
    assert all(not tx.updates for tx in client.transactions)


@pytest.mark.parametrize('protection', ['calendar_overlap', 'calendar_connected_unverified'])
def test_calendar_protection_becomes_kept_title_only(tmp_path, protection):
    client, runtime, log = setup(tmp_path, apply=True)
    runtime.protections = lambda *args: protection
    assert evaluate(runtime, log)['class'] == 'K'
    assert not client.transactions


def test_calendar_error_never_discards(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    runtime.protections = lambda *args: (_ for _ in ()).throw(RuntimeError(TEXT))
    assert evaluate(runtime, log)['outcome'] == 'error'
    assert not client.transactions


def test_wake_word_legacy_segment_id_keeps(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True, text='Hey Omi')
    client.rows[ROW_PATH]['transcript_segments'][0].pop('id')
    result = evaluate(runtime, log)
    assert result['class'] == 'K' and result['rule'] == 'wake_word'
    assert not client.transactions


def test_rollback_restores_missing_field_and_only_untouched_rows(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    original = deepcopy(client.rows[ROW_PATH])
    evaluate(runtime, log)
    target = repair.RunLog(tmp_path / 'rollback', log.config)
    summary = repair.rollback(runtime, log, target, qps=100000)
    assert summary['outcomes']['written'] == 1
    # Fixture carries the SDK sentinel; it does not emulate deletes.
    assert client.transactions[-1].updates[0][1]['relevance_decision'] is repair.firestore.DELETE_FIELD
    assert client.rows[ROW_PATH]['discarded'] == original['discarded']


@pytest.mark.parametrize('changed', ['restore', 'title', 'content', 'decision'])
def test_rollback_refuses_touched_rows(tmp_path, changed):
    client, runtime, log = setup(tmp_path, apply=True)
    evaluate(runtime, log)
    if changed == 'restore':
        client.rows[ROW_PATH]['sync_relevance_user_kept'] = True
    elif changed == 'title':
        client.rows[ROW_PATH]['structured']['title'] = 'user edited'
    elif changed == 'content':
        client.rows[ROW_PATH]['transcript_segments'][0]['text'] = TEXT
    else:
        client.rows[ROW_PATH]['relevance_decision']['reason'] = 'other'
    target = repair.RunLog(tmp_path / 'rollback', log.config)
    assert repair.rollback(runtime, log, target)['outcomes'] == {'rollback_changed': 1}
    assert not client.transactions[-1].updates


def test_resume_skips_processed_mid_page(tmp_path):
    client, runtime, log = setup(tmp_path)
    evaluate(runtime, log)
    resumed = repair.RunLog(log.path, log.config, resume=True)
    assert repair.run(runtime, resumed)['processed'] == 0
    assert resumed.processed == {JOB_ID}
    assert resumed.cursor == JOB_ID


def test_resume_reconciles_crash_after_commit(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    result = repair.evaluate(runtime, log, JOB_ID, limiter=repair.RateLimiter(100000))
    assert result['outcome'] == 'written'
    resumed = repair.RunLog(log.path, log.config, resume=True)
    assert repair.run(runtime, resumed)['processed'] == 0
    assert resumed.results[result['decision_id']]['outcome'] == 'written'
    assert len(client.transactions) == 1


def test_resume_mode_change_and_directory_reuse_refused(tmp_path):
    _, _, log = setup(tmp_path)
    with pytest.raises(FileExistsError):
        repair.RunLog(log.path, log.config)
    with pytest.raises(ValueError):
        repair.RunLog(log.path, dict(log.config, apply=True), resume=True)


def test_no_private_content_in_logs_or_audit(tmp_path, caplog):
    _, runtime, log = setup(tmp_path, kept=True, text=TEXT)
    evaluate(runtime, log)
    serialized = (log.path / 'audit.jsonl').read_text() + caplog.text
    assert TEXT not in serialized and UID not in serialized
    assert TEXT.split('.')[0] not in serialized


def test_helper_decode_failure_cannot_be_empty_transcript(tmp_path, monkeypatch, caplog):
    _, runtime, log = setup(tmp_path)
    repair.install_private_log_filters()
    monkeypatch.setenv('ENCRYPTION_SECRET', 'x' * 32)

    def decode(data, uid):
        repair.logging.getLogger('database.conversations').error('%s %s', TEXT, UID)
        return dict(data, transcript_segments=[])

    monkeypatch.setattr(
        repair.importlib, 'import_module', lambda name: SimpleNamespace(_decrypt_conversation_data=decode)
    )
    with pytest.raises(repair.CannotClassify, match='transcript_decode_failed'):
        repair.decode_transcript(dict(row(), transcript_segments='encrypted'), UID)
    assert TEXT not in caplog.text and UID not in caplog.text


def test_key_unavailable_counts_unclassified(tmp_path, monkeypatch):
    client, runtime, log = setup(tmp_path)
    monkeypatch.delenv('ENCRYPTION_SECRET', raising=False)
    client.rows[ROW_PATH]['transcript_segments'] = 'encrypted'
    runtime.decode = repair.decode_transcript
    summary = repair.run(runtime, log)
    assert summary['skip_reasons'] == {'decryption_key_unavailable': 1}
    assert summary['classes'] == {}


def test_sustained_errors_stop_nonzero_and_leave_cursor(tmp_path):
    client, runtime, log = setup(tmp_path)
    for i in range(8):
        client.rows[(repair.JOBS, f'job-{i}')] = job()
    runtime.decode = lambda *args: (_ for _ in ()).throw(RuntimeError(TEXT))
    # Bind all test job IDs so the failure occurs during decode.
    for path in [p for p in client.rows if p[0] == repair.JOBS]:
        client.rows[path]['conversation_id'] = path[-1]
        data = row()
        data['finalization_job_id'] = path[-1]
        client.rows[('users', UID, 'conversations', path[-1])] = data
    summary = repair.run(runtime, log, workers=2, error_window=4)
    assert summary['processed'] == 4 and summary['exit_code'] == 2
    assert summary['stopped_error_rate'] and log.cursor is None


def test_backoff_retries_aborted_only_and_bounds_attempts(monkeypatch):
    sleeps = []
    monkeypatch.setattr(repair.time, 'sleep', sleeps.append)
    attempts = []

    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise repair.Aborted('contention')
        return 'written'

    assert repair.retry_write(repair.RateLimiter(100000), operation) == 'written'
    assert len(attempts) == 3
    assert any(delay >= 0.25 for delay in sleeps)


def test_external_source_empty_transcript_never_discards(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True)
    client.rows[ROW_PATH]['source'] = 'external_integration'
    assert evaluate(runtime, log)['outcome'] == 'non_audio_source'
    assert not client.transactions


def test_dry_rollback_pending_intent_never_converges(tmp_path):
    client, runtime, source = setup(tmp_path, apply=True)
    result = repair.evaluate(runtime, source, JOB_ID, limiter=repair.RateLimiter(100000))
    assert result['outcome'] == 'written'
    runtime.converge = lambda *args: pytest.fail('dry rollback projection write')
    target = repair.RunLog(tmp_path / 'rollback', dict(source.config, apply=False))
    original = deepcopy(client.rows)
    assert repair.rollback(runtime, source, target)['outcomes'] == {'dry_run': 1}
    assert client.rows == original


def test_wrapped_aborted_retries(monkeypatch):
    monkeypatch.setattr(repair.time, 'sleep', lambda delay: None)
    attempts = []

    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            try:
                raise repair.Aborted('contention')
            except repair.Aborted as error:
                raise ValueError('SDK retries exhausted') from error
        return 'written'

    assert repair.retry_write(repair.RateLimiter(100000), operation) == 'written'
    assert len(attempts) == 2


def test_resume_pending_before_commit_retries(tmp_path):
    client, runtime, source = setup(tmp_path, apply=True)
    result = repair.evaluate(runtime, source, JOB_ID, limiter=repair.RateLimiter(100000))
    # Simulate a lost intent before the commit reached Firestore.
    client.rows[ROW_PATH] = row()
    resumed = repair.RunLog(source.path, source.config, resume=True)
    assert repair.run(runtime, resumed)['classes']['written'] == 1


def test_canary_limit_and_filters(tmp_path):
    client, runtime, source = setup(tmp_path)
    for i in range(3):
        jid = f'job-{i}'
        client.rows[(repair.JOBS, jid)] = dict(job(), conversation_id=jid)
        client.rows[('users', UID, 'conversations', jid)] = dict(row(), finalization_job_id=jid)
    assert repair.run(runtime, source, limit=2, page_size=2)['processed'] == 2
    resumed = repair.RunLog(source.path, source.config, resume=True)
    assert repair.run(runtime, resumed, limit=2, page_size=2)['processed'] == 2
    filtered = repair.RunLog(tmp_path / 'filtered', dict(source.config, conversation_ids=[CID]))
    assert repair.run(runtime, filtered)['processed'] == 1


def test_cas_detects_revision_change_even_when_values_returned_to_original(tmp_path, monkeypatch):

    client, runtime, log = setup(tmp_path, apply=True)
    original = StrictFirestoreDocument.get

    def get(ref, transaction=None, **kwargs):
        snapshot = original(ref, transaction=transaction, **kwargs)
        snapshot.update_time = 2 if transaction is not None and ref.path == ROW_PATH else 1
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    assert evaluate(runtime, log)['outcome'] == 'cas_changed'
    assert not client.transactions[0].updates


def test_kept_title_rollback_sdk_patch(tmp_path):
    client, runtime, source = setup(tmp_path, apply=True, kept=True, text=TEXT)
    result = evaluate(runtime, source)
    # Represent Firestore's field-path result to exercise rollback's whole-row CAS.
    patch = client.rows[ROW_PATH].pop('structured.title')
    client.rows[ROW_PATH]['structured']['title'] = patch
    target = repair.RunLog(tmp_path / 'rollback', source.config)
    assert repair.rollback(runtime, source, target)['outcomes'] == {'written': 1}
    assert client.transactions[-1].updates[0][1] == {'structured.title': ''}


def test_uid_filter_persists_hash_only(tmp_path):
    client, runtime, source = setup(tmp_path)
    target = repair.RunLog(tmp_path / 'filtered', dict(source.config, uids=[repair.digest(UID)]))
    assert UID not in (target.path / 'config.json').read_text()
    assert repair.run(runtime, target)['processed'] == 1


def test_rollback_limit_resume_skips_processed(tmp_path):
    client, runtime, source = setup(tmp_path, apply=True)
    evaluate(runtime, source)
    target = repair.RunLog(tmp_path / 'rollback', source.config)
    assert repair.rollback(runtime, source, target, limit=1, workers=2)['outcomes'] == {'written': 1}
    resumed = repair.RunLog(target.path, target.config, resume=True)
    assert repair.rollback(runtime, source, resumed)['outcomes'] == {}

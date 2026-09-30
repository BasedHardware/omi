"""Hermetic repair contracts, using the strict transaction boundary fake."""

from copy import deepcopy
from datetime import datetime, timezone
import json
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
def test_protected_rule_discard_skips_even_with_kept_titles_enabled(tmp_path, protection):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text='yeah okay')
    original = deepcopy(client.rows)
    runtime.protections = lambda *args: protection
    result = evaluate(runtime, log)
    assert result['outcome'] == 'discard_protected'
    assert result['class'] is None
    assert client.rows == original and not client.transactions


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


@pytest.mark.parametrize('protection', ['calendar_overlap', 'calendar_connected_unverified'])
@pytest.mark.parametrize('text', ['', ' \t\n '])
def test_empty_transcript_discards_despite_calendar_protection(tmp_path, protection, text):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text=text)
    runtime.protections = lambda *args: protection
    original = deepcopy(client.rows[ROW_PATH])
    result = evaluate(runtime, log)
    assert result['class'] == 'R' and result['rule'] == 'empty_transcript'
    assert result['outcome'] == 'written'
    current = client.rows[ROW_PATH]
    assert verified_recovery_discard(current['discarded'], current['relevance_decision'])
    assert current == dict(original, discarded=True, relevance_decision=current['relevance_decision'])
    assert set(client.transactions[0].updates[0][1]) == {'discarded', 'relevance_decision'}


def test_empty_rule_never_reads_calendar_but_still_checks_photo_subcollection(tmp_path):
    client, runtime, log = setup(tmp_path)
    calls = []

    class Photos:
        def select(self, fields):
            assert fields == []
            return self

        def limit(self, limit):
            assert limit == 1
            return self

        def stream(self, transaction=None):
            calls.append('photos')
            return []

    def collection(name):
        assert name == 'photos'
        return Photos()

    runtime.protections = None
    # No client access is allowed: calendar/timezone lookups would fail here.
    runtime.client = None
    cls, rule, updates = repair.classify(runtime, row(), job(), SimpleNamespace(collection=collection))
    assert cls == 'R' and rule == 'empty_transcript'
    assert updates['discarded'] is True and calls == ['photos']


@pytest.mark.parametrize('verdict', ['keep', None])
@pytest.mark.parametrize('text', ['', ' \t\n '])
def test_empty_non_discard_never_gets_fallback_title(tmp_path, monkeypatch, verdict, text):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text=text)
    original = deepcopy(client.rows)
    monkeypatch.setattr(repair, 'deterministic_relevance', lambda *args: (verdict, 'synthetic_unknown'))
    monkeypatch.setattr(
        repair, 'deterministic_minimum_title', lambda *args, **kwargs: pytest.fail('empty fallback title')
    )
    result = evaluate(runtime, log)
    assert result['outcome'] == 'empty_not_discardable' and result['class'] is None
    assert client.rows == original and not client.transactions


def test_rule_discard_with_wake_word_protection_skips_title(tmp_path, monkeypatch):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text='Hey Omi')
    monkeypatch.setattr(repair, 'deterministic_relevance', lambda *args: ('discard', 'synthetic_discard'))
    result = evaluate(runtime, log)
    assert result['outcome'] == 'discard_protected' and result['class'] is None
    assert not client.transactions


def test_new_calendar_protection_at_cas_skips_nonempty_rule_discard(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text='yeah okay')
    runtime.protections = lambda ref, data, job, tx: 'calendar_overlap' if tx is not None else None
    result = evaluate(runtime, log)
    assert result['outcome'] == 'discard_protected'
    assert all(not tx.updates for tx in client.transactions)


def test_empty_rule_keeps_other_protection_fences(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True, kept=True)
    runtime.protections = lambda *args: 'other_protection'
    result = evaluate(runtime, log)
    assert result['outcome'] == 'discard_protected' and result['class'] is None
    assert not client.transactions


@pytest.mark.parametrize(
    ('audio_files', 'bucket'),
    [
        ([], '0'),
        ([{'duration': 0}], '0'),
        ([{'duration': 0.01}], '<5s'),
        ([{'duration': 4.999}], '<5s'),
        ([{'duration': 2}, {'duration': 3}], '5-30s'),
        ([{'duration': 29.999}], '5-30s'),
        ([{'duration': 15}, {'duration': 15}], '30-120s'),
        ([{'duration': 120}], '30-120s'),
        ([{'duration': 60}, {'duration': 60.001}], '>120s'),
        (None, 'unknown'),
        ({'duration': 3}, 'unknown'),
        ([None], 'unknown'),
        ([{}], 'unknown'),
        ([{'duration': 5}, {}], 'unknown'),
        ([{'duration': -1}], 'unknown'),
        ([{'duration': True}], 'unknown'),
        ([{'duration': '5'}], 'unknown'),
        ([{'duration': float('nan')}], 'unknown'),
        ([{'duration': float('inf')}], 'unknown'),
        ([{'duration': 10**400}], 'unknown'),
        ([{'duration': 1e308}, {'duration': 1e308}], 'unknown'),
    ],
)
def test_total_audio_duration_buckets(audio_files, bucket):
    assert repair.audio_duration_bucket({'audio_files': audio_files}) == bucket


def test_missing_audio_duration_is_unknown_even_with_capture_timestamps():
    assert repair.audio_duration_bucket(row()) == 'unknown'


@pytest.mark.parametrize('kept', [False, True])
def test_dry_run_breakdown_source_rule_duration_shape(tmp_path, monkeypatch, kept):
    client, runtime, log = setup(tmp_path, kept=kept)
    # One R in every bucket, across several capture sources; K includes a known
    # import source. Arbitrary legacy source text must never become a log label.
    cases = [
        ('omi', '', [], 'R', 'empty_transcript', '0'),
        ('phone', '', [{'duration': 2}, {'duration': 2}], 'R', 'empty_transcript', '<5s'),
        ('desktop', '', [{'duration': 2}, {'duration': 3}], 'R', 'empty_transcript', '5-30s'),
        ('omi', '', [{'duration': 15}, {'duration': 15}], 'R', 'empty_transcript', '30-120s'),
        ('phone', '', [{'duration': 121}], 'R', 'empty_transcript', '>120s'),
        ('desktop', '', None, 'R', 'empty_transcript', 'unknown'),
        ('external_integration', TEXT, [{'duration': 60}, {'duration': 61}], 'K', 'ambiguous', '>120s'),
        ('omi', 'yeah okay', None, 'discard_protected', 'filler_only', 'unknown'),
        (TEXT, ' \t ', [{'duration': 0}], 'empty_not_discardable', 'synthetic_unknown', '0'),
    ]
    client.rows.clear()
    original_rule = repair.deterministic_relevance
    monkeypatch.setattr(
        repair,
        'deterministic_relevance',
        lambda texts, seconds: (None, 'synthetic_unknown') if texts == [' \t '] else original_rule(texts, seconds),
    )
    runtime.protections = lambda ref, data, job, tx: (
        'calendar_overlap' if data['transcript_segments'][0]['text'] == 'yeah okay' else None
    )
    expected = {'R': {}, 'K': {}, 'discard_protected': {}, 'empty_not_discardable': {}}
    for i, (source, text, audio_files, category, rule, bucket) in enumerate(cases):
        jid = f'job-{i}'
        client.rows[(repair.JOBS, jid)] = dict(job(), conversation_id=jid)
        data = dict(row(text), source=source, finalization_job_id=jid)
        if audio_files is not None:
            data['audio_files'] = audio_files
        client.rows[('users', UID, 'conversations', jid)] = data
        source_label = 'unknown' if source == TEXT else source
        buckets = (
            expected[category]
            .setdefault(source_label, {})
            .setdefault(rule, {'0': 0, '<5s': 0, '5-30s': 0, '30-120s': 0, '>120s': 0, 'unknown': 0})
        )
        buckets[bucket] += 1
    original = deepcopy(client.rows)
    summary = repair.run(runtime, log, workers=3, page_size=4)
    assert summary['processed'] == len(cases) and summary['exit_code'] == 0
    assert summary['classes'] == {'R': 6, 'K': 1, 'dry_run': 7 if kept else 6}
    assert summary['skip_reasons'] == dict(
        {'discard_protected': 1, 'empty_not_discardable': 1}, **({} if kept else {'kept_titles_disabled': 1})
    )
    assert summary['breakdown'] == expected
    for category in expected:
        total = sum(sum(buckets.values()) for by_rule in expected[category].values() for buckets in by_rule.values())
        counts = summary['classes'] if category in ('R', 'K') else summary['skip_reasons']
        assert total == counts[category]
    assert json.loads((log.path / 'summary.json').read_text()) == summary
    serialized = (log.path / 'summary.json').read_text() + (log.path / 'audit.jsonl').read_text()
    assert TEXT not in serialized and UID not in serialized
    assert client.rows == original and not client.transactions

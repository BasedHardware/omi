"""Hermetic repair contracts, using the strict transaction boundary fake."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import threading
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from scripts import repair_recovery_dead_letter_untitled as repair
from models.client_processing import ClientProcessing
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreTransaction,
)
from utils.conversations.deterministic_minimum import deterministic_minimum_title
from utils.conversations.recovery import verified_recovery_discard
from utils.conversations.transcript_hash import transcript_sha256_for_binding

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
        converge=lambda uid, cid: True,
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
    runtime.converge = lambda uid, cid: calls.append((uid, cid)) or True
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


def bound_projection(data):
    digest = transcript_sha256_for_binding(data['transcript_segments'])
    assert digest is not None
    return ClientProcessing.model_validate(
        {
            'schema_version': 1,
            'transcript_sha256': digest,
            'structure': {'title': 'Local saved title', 'overview': TEXT},
            'action_items': [{'description': 'Send the release plan', 'completed': False}],
            'provenance': {
                'model_id': 'local-model',
                'runtime': 'local',
                'device_class': 'desktop',
                'generated_at': '2026-02-01T00:00:00Z',
            },
        }
    ).model_dump(mode='json')


def test_bound_client_projection_protects_filler_capture(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text='yeah okay')
    client.rows[ROW_PATH]['client_processing'] = bound_projection(client.rows[ROW_PATH])
    original = deepcopy(client.rows)
    assert evaluate(runtime, log)['outcome'] == 'client_processing_content'
    assert client.rows == original and not client.transactions


@pytest.mark.parametrize(
    'projection',
    [
        {'structure': {'title': 'Saved title'}},
        {'structure': {'overview': TEXT}},
        {'structure': {'sections': [{'heading': 'Notes', 'body_markdown': TEXT}]}},
        {'structure': {}, 'action_items': [{'description': 'Saved task'}]},
        {'structure': {'events': [{'title': 'Saved meeting'}]}},
        'undecodable',
    ],
)
def test_client_projection_display_fields_protected(tmp_path, projection):
    client, runtime, log = setup(tmp_path, apply=True)
    client.rows[ROW_PATH]['client_processing'] = projection
    assert evaluate(runtime, log)['outcome'] == 'client_processing_content'
    assert not client.transactions


def test_late_client_projection_is_rechecked_inside_transaction(tmp_path):
    client, runtime, log = setup(tmp_path, apply=True, text='yeah okay')
    transaction = client.transaction

    def late_projection(**kwargs):
        client.rows[ROW_PATH]['client_processing'] = bound_projection(client.rows[ROW_PATH])
        return transaction(**kwargs)

    client.transaction = late_projection
    assert evaluate(runtime, log)['outcome'] == 'client_processing_content'
    assert client.rows[ROW_PATH]['discarded'] is False
    assert all(not tx.updates for tx in client.transactions)


def fault_after_mutation(monkeypatch, client):
    write = repair.write_cas
    attempts = []

    def committed_then_timeout(*args, **kwargs):
        attempts.append(1)
        receipt = write(*args, **kwargs)
        assert receipt['outcome'] == 'written'
        # Model the SDK's field-path result without extending the strict fake.
        if 'structured.title' in client.rows[ROW_PATH]:
            client.rows[ROW_PATH]['structured']['title'] = client.rows[ROW_PATH].pop('structured.title')
        raise repair.DeadlineExceeded('commit response lost')

    monkeypatch.setattr(repair, 'write_cas', committed_then_timeout)
    return attempts


@pytest.mark.parametrize('text', ['', TEXT])
def test_commit_response_timeout_reconciles_before_retry_and_rollback(tmp_path, monkeypatch, text):
    client, runtime, log = setup(tmp_path, apply=True, kept=True, text=text)
    calls = []
    runtime.converge = lambda *args: calls.append(1) or True
    attempts = fault_after_mutation(monkeypatch, client)
    result = evaluate(runtime, log)
    assert result['outcome'] == 'written' and len(attempts) == 1
    assert log.results[result['decision_id']]['projection_status'] == 'complete'
    assert calls == [1]
    resumed = repair.RunLog(log.path, log.config, resume=True)
    assert repair.run(runtime, resumed)['processed'] == 0
    assert len(client.transactions) == 1 and calls == [1]
    target = repair.RunLog(tmp_path / 'rollback', log.config)
    assert repair.rollback(runtime, resumed, target)['outcomes'] == {'written': 1}
    assert client.rows[ROW_PATH]['discarded'] is False
    if text:
        assert client.transactions[-1].updates[0][1] == {'structured.title': ''}


def test_error_receipt_after_ambiguous_commit_recovers_on_resume(tmp_path, monkeypatch):
    client, runtime, log = setup(tmp_path, apply=True)
    calls = []
    runtime.converge = lambda *args: calls.append(1) or True
    attempts = fault_after_mutation(monkeypatch, client)
    reconcile = repair.reconcile_intent
    monkeypatch.setattr(
        repair, 'reconcile_intent', lambda *args: (_ for _ in ()).throw(repair.DeadlineExceeded('read unavailable'))
    )
    result = evaluate(runtime, log)
    assert result['outcome'] == 'error' and len(attempts) == 1 and not calls
    assert client.rows[ROW_PATH]['discarded'] is True
    monkeypatch.setattr(repair, 'reconcile_intent', reconcile)
    resumed = repair.RunLog(log.path, log.config, resume=True)
    summary = repair.run(runtime, resumed)
    assert summary['exit_code'] == 0 and summary['processed'] == 0
    assert resumed.results[result['decision_id']]['outcome'] == 'written'
    assert resumed.results[result['decision_id']]['projection_status'] == 'complete'
    assert calls == [1] and len(client.transactions) == 1
    target = repair.RunLog(tmp_path / 'rollback', log.config)
    assert repair.rollback(runtime, resumed, target)['outcomes'] == {'written': 1}


def test_retry_refusal_reconciles_a_commit_that_became_visible_later(tmp_path, monkeypatch):
    client, runtime, source = setup(tmp_path, apply=True)
    write, reconcile = repair.write_cas, repair.reconcile_intent
    attempts, observations = [], []
    monkeypatch.setattr(repair.time, 'sleep', lambda *args: None)

    def operation(*args, **kwargs):
        attempts.append(1)
        result = write(*args, **kwargs)
        if len(attempts) == 1:
            raise repair.DeadlineExceeded('commit still in flight')
        assert result['outcome'] == 'not_visible'
        return result

    def observe(*args):
        observations.append(1)
        return None if len(observations) == 1 else reconcile(*args)

    monkeypatch.setattr(repair, 'write_cas', operation)
    monkeypatch.setattr(repair, 'reconcile_intent', observe)
    result = evaluate(runtime, source)
    assert result['outcome'] == 'written' and len(attempts) == 2
    assert source.results[result['decision_id']]['projection_status'] == 'complete'
    assert sum(bool(tx.updates) for tx in client.transactions) == 1


def test_crash_during_projection_keeps_durable_pending_receipt(tmp_path):
    client, runtime, source = setup(tmp_path, apply=True)
    runtime.converge = lambda *args: (_ for _ in ()).throw(SystemExit('simulated crash'))
    with pytest.raises(SystemExit):
        evaluate(runtime, source)
    assert client.rows[ROW_PATH]['discarded'] is True
    resumed = repair.RunLog(source.path, source.config, resume=True)
    assert len(resumed.pending_projections()) == 1
    runtime.converge = lambda *args: True
    summary = repair.run(runtime, resumed)
    assert summary['processed'] == 0 and summary['projection_pending'] == 0 and summary['exit_code'] == 0
    assert len(client.transactions) == 1


@pytest.mark.parametrize('receipt', ['error', 'not_visible'])
def test_rollback_recovers_prior_error_or_terminal_refusal_receipt(tmp_path, receipt):
    client, runtime, source = setup(tmp_path, apply=True)
    result = evaluate(runtime, source)
    source.finish(result, receipt)  # old script's incorrect response classification
    target = repair.RunLog(tmp_path / 'rollback', source.config)
    assert repair.rollback(runtime, source, target)['outcomes'] == {'written': 1}
    assert source.results[result['decision_id']]['outcome'] == 'written'
    assert client.rows[ROW_PATH]['discarded'] is False


@pytest.mark.parametrize('failure', ['false', 'exception', 'none'])
def test_pending_projection_retried_on_resume_without_mutation(tmp_path, failure, caplog):
    client, runtime, log = setup(tmp_path, apply=True)
    calls = []

    def converge(*args):
        calls.append(1)
        # The mutation receipt must already be durable before indexing starts.
        assert log.pending_projections()
        if failure == 'exception':
            raise RuntimeError(f'{TEXT} {UID}')
        return False if failure == 'false' else None

    runtime.converge = converge
    summary = repair.run(runtime, log)
    assert summary['classes']['written'] == 1
    assert summary['projection_pending'] == 1 and summary['exit_code'] == 2
    assert len(client.transactions) == 1 and calls == [1]
    resumed = repair.RunLog(log.path, log.config, resume=True)
    runtime.converge = lambda *args: calls.append(1) or False
    summary = repair.run(runtime, resumed)
    assert summary['processed'] == 0 and summary['projection_pending'] == 1 and summary['exit_code'] == 2
    runtime.converge = lambda *args: calls.append(1) or True
    resumed = repair.RunLog(log.path, log.config, resume=True)
    summary = repair.run(runtime, resumed)
    assert summary['processed'] == 0 and summary['projection_pending'] == 0 and summary['exit_code'] == 0
    assert calls == [1, 1, 1] and len(client.transactions) == 1
    assert next(iter(resumed.results.values()))['projection_status'] == 'complete'
    assert TEXT not in caplog.text and UID not in caplog.text


def test_real_sync_helper_false_is_pending(tmp_path, monkeypatch):
    _, runtime, log = setup(tmp_path, apply=True)
    runtime.converge = None
    monkeypatch.setattr(
        repair.importlib,
        'import_module',
        lambda name: SimpleNamespace(sync_conversation_index_after_write=lambda *args, **kwargs: False),
    )
    summary = repair.run(runtime, log)
    assert summary['projection_pending'] == 1 and summary['exit_code'] == 2


def test_legacy_written_receipt_without_projection_status_retries(tmp_path):
    client, runtime, source = setup(tmp_path, apply=True)
    evaluate(runtime, source)
    legacy = dict(next(iter(source.results.values())))
    legacy.pop('projection_status')
    source.append('results.jsonl', legacy)
    resumed = repair.RunLog(source.path, source.config, resume=True)
    calls = []
    runtime.converge = lambda *args: calls.append(1) or True
    summary = repair.run(runtime, resumed)
    assert summary['processed'] == 0 and summary['projection_pending'] == 0
    assert summary['exit_code'] == 0 and calls == [1] and len(client.transactions) == 1


def test_rollback_pending_projection_resumes_without_repeat_restore(tmp_path):
    client, runtime, source = setup(tmp_path, apply=True)
    evaluate(runtime, source)
    target = repair.RunLog(tmp_path / 'rollback', source.config)
    runtime.converge = lambda *args: False
    summary = repair.rollback(runtime, source, target)
    assert summary['outcomes'] == {'written': 1}
    assert summary['projection_pending'] == 1 and summary['exit_code'] == 2
    resumed = repair.RunLog(target.path, target.config, resume=True)
    runtime.converge = lambda *args: True
    summary = repair.rollback(runtime, source, resumed)
    assert summary['outcomes'] == {} and summary['projection_pending'] == 0 and summary['exit_code'] == 0
    assert len(client.transactions) == 2


def test_rollback_commit_response_timeout_reconciles_restored_state(tmp_path, monkeypatch):
    client, runtime, source = setup(tmp_path, apply=True)
    original = deepcopy(client.rows[ROW_PATH])
    evaluate(runtime, source)
    target = repair.RunLog(tmp_path / 'rollback', source.config)

    def commit_response_lost(transaction):
        # The fake records the SDK delete sentinel literally. Supply the
        # actual server after-state before injecting a lost commit response.
        client.rows[ROW_PATH] = deepcopy(original)
        raise repair.DeadlineExceeded('rollback response lost')

    monkeypatch.setattr(StrictFirestoreTransaction, '_commit', commit_response_lost)
    summary = repair.rollback(runtime, source, target, qps=100000)
    assert summary['outcomes'] == {'written': 1} and summary['exit_code'] == 0
    assert len(client.transactions) == 2 and client.rows[ROW_PATH] == original
    assert next(iter(target.results.values()))['projection_status'] == 'complete'


@pytest.mark.parametrize('journal', ['audit.jsonl', 'results.jsonl'])
@pytest.mark.parametrize('mode', ['resume', 'rollback'])
@pytest.mark.parametrize('tail', [b'{"decision_id":"torn', b'{"title":"\xe2\x82'])
def test_torn_journal_tail_recovers_with_counted_warning(tmp_path, caplog, journal, mode, tail):
    client, runtime, source = setup(tmp_path, apply=True)
    result = evaluate(runtime, source)
    prefix = (source.path / journal).read_bytes()
    with (source.path / journal).open('ab') as file:
        file.write(tail)
    resumed = repair.RunLog(source.path, source.config, resume=True)
    if mode == 'resume':
        # New decisions must append after recovery without corrupting the journal.
        jid = 'job-two'
        client.rows[(repair.JOBS, jid)] = dict(job(), conversation_id=jid)
        client.rows[('users', UID, 'conversations', jid)] = dict(row(), finalization_job_id=jid)
        summary = repair.run(runtime, resumed)
        assert summary['processed'] == 1 and summary['journal_warnings'] == {journal: 1}
    else:
        target = repair.RunLog(tmp_path / 'rollback', source.config)
        summary = repair.rollback(runtime, resumed, target)
        assert summary['outcomes'] == {'written': 1}
        assert summary['journal_warnings']['source'] == {journal: 1}
    assert summary['exit_code'] == 0
    assert resumed.results[result['decision_id']]['outcome'] == 'written'
    assert (source.path / journal).read_bytes().startswith(prefix)
    assert all(isinstance(json.loads(line), dict) for line in (source.path / journal).read_bytes().splitlines())
    assert [path.read_bytes() for path in source.path.glob(f'{journal}.torn-*')] == [tail]
    assert caplog.text.count('journal_tail_dropped') == 1


@pytest.mark.parametrize('journal', ['audit.jsonl', 'results.jsonl'])
@pytest.mark.parametrize('corruption', ['middle', 'terminated_tail', 'non_object'])
def test_malformed_journal_is_rejected_except_unterminated_tail(tmp_path, journal, corruption):
    _, _, source = setup(tmp_path, apply=True)
    evaluate(repair.Runtime(None), source)  # an ordinary bounded error receipt
    path = source.path / journal
    with path.open('ab') as file:
        file.write(b'[]\n' if corruption == 'non_object' else b'not-json\n')
        if corruption == 'middle':
            file.write(b'{}\n')
    with pytest.raises(ValueError, match='malformed journal'):
        source.read(journal)
    assert not source.journal_warnings


@pytest.mark.parametrize('journal', ['audit.jsonl', 'results.jsonl'])
def test_complete_json_without_newline_can_be_appended_safely(tmp_path, journal):
    _, runtime, source = setup(tmp_path)
    evaluate(runtime, source)
    path = source.path / journal
    path.write_bytes(path.read_bytes()[:-1])
    records = source.read(journal)
    source.append(journal, records[0])
    assert source.read(journal) == records * 2
    assert not source.journal_warnings


def test_cli_resume_locks_run_before_recovering_journals(tmp_path, monkeypatch, capsys):
    client, runtime, source = setup(tmp_path)
    evaluate(runtime, source)
    with (source.path / 'results.jsonl').open('ab') as file:
        file.write(b'{"decision_id":"torn')
    run_log = repair.RunLog

    def locked_log(path, config, *, resume=False):
        assert resume
        with (path / 'run.lock').open('a') as probe:
            with pytest.raises(BlockingIOError):
                repair.fcntl.flock(probe.fileno(), repair.fcntl.LOCK_EX | repair.fcntl.LOCK_NB)
        return run_log(path, config, resume=resume)

    monkeypatch.setattr(repair, 'RunLog', locked_log)
    monkeypatch.setattr(repair.sys, 'argv', ['repair', '--resume', str(source.path)])
    monkeypatch.setattr(
        repair.importlib, 'import_module', lambda name: SimpleNamespace(get_firestore_client=lambda: client)
    )
    assert repair.main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['processed'] == 0 and summary['journal_warnings'] == {'results.jsonl': 1}


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


def test_resume_pending_before_commit_retries(tmp_path, monkeypatch):
    client, runtime, source = setup(tmp_path, apply=True)
    write = repair.write_cas
    monkeypatch.setattr(repair.time, 'sleep', lambda *args: None)
    monkeypatch.setattr(repair, 'write_cas', lambda *args, **kwargs: (_ for _ in ()).throw(repair.Aborted('no commit')))
    result = repair.evaluate(runtime, source, JOB_ID, limiter=repair.RateLimiter(100000))
    # Durable intent exists, but no mutation or result receipt was persisted.
    assert result['outcome'] == 'error' and client.rows[ROW_PATH] == row()
    monkeypatch.setattr(repair, 'write_cas', write)
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


class FakeStorage:
    """Version-fenced GCS boundary; no credentials, sockets or cloud clients."""

    def __init__(self):
        self.objects = {}
        self.uploads = []
        self.serial = 0
        self.lock = threading.RLock()

    def bucket(self, name):
        return SimpleNamespace(name=name, blob=lambda key: FakeBlob(self, name, key))

    def list_blobs(self, bucket, *, prefix, max_results=None):
        return [
            FakeBlob(self, name, key)
            for name, key in list(self.objects)
            if name == bucket.name and key.startswith(prefix)
        ][:max_results]


class FakeBlob:
    def __init__(self, storage, bucket, name):
        self.storage = storage
        self.bucket = bucket
        self.name = name
        self.generation = None

    def reload(self, **kwargs):
        from google.api_core.exceptions import NotFound

        if (self.bucket, self.name) not in self.storage.objects:
            raise NotFound('missing object')
        self.generation = self.storage.objects[(self.bucket, self.name)][0]

    def upload_from_string(self, data, *, if_generation_match, content_type=None, **kwargs):
        from google.api_core.exceptions import PreconditionFailed

        with self.storage.lock:
            key = (self.bucket, self.name)
            current = self.storage.objects.get(key, (0, None))[0]
            if current != if_generation_match:
                raise PreconditionFailed('generation mismatch')
            self.storage.serial += 1
            self.generation = self.storage.serial
            self.storage.objects[key] = (self.generation, data.encode() if isinstance(data, str) else data)
            self.storage.uploads.append((self.name, if_generation_match))

    def download_as_bytes(self, *, if_generation_match, **kwargs):
        from google.api_core.exceptions import PreconditionFailed

        generation, data = self.storage.objects[(self.bucket, self.name)]
        if generation != if_generation_match:
            raise PreconditionFailed('generation mismatch')
        return data


def artifact(storage, uri='gs://test-bucket/repair/run'):
    return repair.ArtifactMirror(uri, storage)


def remote_file(storage, name, prefix='repair/run/'):
    _, raw = storage.objects[('test-bucket', prefix + 'manifest.json')]
    entry = json.loads(raw)['files'][name]
    generation, data = storage.objects[('test-bucket', entry['object'])]
    assert generation == entry['generation']
    return data


def test_artifact_new_run_refuses_any_existing_object_and_racing_reservation():
    from google.api_core.exceptions import PreconditionFailed

    storage = FakeStorage()
    storage.bucket('test-bucket').blob('repair/run/orphan').upload_from_string(b'x', if_generation_match=0)
    with pytest.raises(ValueError, match='not empty'):
        artifact(storage).create()
    # A prefix sibling is not in scope; the reservation still fences a race.
    first = artifact(storage, 'gs://test-bucket/repair/run-other')
    second = artifact(storage, 'gs://test-bucket/repair/run-other')
    first.create()
    with pytest.raises(repair.LeaseLost):
        second.publish({})


def test_artifact_resume_downloads_key_journals_and_checkpoint(tmp_path, caplog):
    _, runtime, source = setup(tmp_path)
    storage = FakeStorage()
    source.artifacts = artifact(storage)
    source.artifacts.create()
    evaluate(runtime, source)
    source.checkpoint(JOB_ID)
    restored = tmp_path / 'download'
    restored.mkdir()
    (restored / 'results.jsonl').write_text('unpublished local debris')
    source.artifacts.lease.close()
    resumed_mirror = artifact(storage)
    resumed_mirror.download(restored)
    resumed = repair.RunLog(restored, source.config, resume=True)
    assert resumed.cursor == JOB_ID and resumed.processed == {JOB_ID}
    assert (restored / 'audit.key').read_bytes() == (source.path / 'audit.key').read_bytes()
    assert (restored / 'audit.key').stat().st_mode & 0o777 == 0o600
    assert (source.path / 'audit.key').read_text() not in caplog.text
    assert list(tmp_path.glob('download.before-download-*'))
    assert not (restored / 'run.lock').exists()


def test_artifact_upload_after_reconcile_and_each_drained_page(tmp_path):
    _, runtime, log = setup(tmp_path)
    storage = FakeStorage()
    log.artifacts = artifact(storage)
    log.artifacts.create()
    seen = []
    original = log.artifacts.upload

    def observe(path):
        original(path)
        seen.append((log.cursor, len(log.read('audit.jsonl'))))

    log.artifacts.upload = observe
    repair.run(runtime, log, workers=1, page_size=1, max_writes_per_second=100000)
    assert seen == [(None, 0), (JOB_ID, 1)]
    assert json.loads(remote_file(storage, 'checkpoint.json'))['cursor'] == JOB_ID
    assert json.loads(remote_file(storage, 'results.jsonl'))['outcome'] == 'dry_run'
    assert remote_file(storage, 'audit.jsonl') == (log.path / 'audit.jsonl').read_bytes()
    # Unchanged files are not re-uploaded; immutable uploads always require 0.
    key_uploads = [name for name, _ in storage.uploads if name.endswith('/audit.key')]
    assert len(key_uploads) == 1
    assert all(match == 0 for name, match in storage.uploads if '/_snapshots/' in name)


def test_artifact_concurrent_writer_detected_preserves_complete_previous_snapshot(tmp_path):
    _, _, log = setup(tmp_path)
    storage = FakeStorage()
    first = artifact(storage)
    first.create()
    first.upload(log.path)
    path = tmp_path / 'second'
    path.mkdir()
    second = artifact(storage)
    with pytest.raises(repair.LeaseLost):
        second.download(path)
    assert not (path / 'audit.key').exists()
    (log.path / 'summary.json').write_text('{"writer":1}')
    first.upload(log.path)
    assert json.loads(remote_file(storage, 'summary.json')) == {'writer': 1}


def artifact_cli(monkeypatch, storage, client, args):
    monkeypatch.setattr(repair.storage, 'Client', lambda: storage)
    monkeypatch.setattr(repair.sys, 'argv', ['repair', *args])
    monkeypatch.setattr(
        repair.importlib, 'import_module', lambda name: SimpleNamespace(get_firestore_client=lambda: client)
    )


@pytest.mark.parametrize('mode', ['stop', 'error', 'interrupt', 'sigterm'])
def test_artifact_cli_finally_uploads_on_stop_error_and_interrupt(tmp_path, monkeypatch, mode):
    client, _, unused = setup(tmp_path)
    storage = FakeStorage()
    path = tmp_path / 'cli'
    artifact_cli(
        monkeypatch, storage, client, ['--run-dir', str(path), '--artifact-uri', 'gs://test-bucket/repair/run']
    )

    def run(runtime, log, **kwargs):
        log.append('audit.jsonl', {'decision_id': 'intent'})
        log.append('results.jsonl', {'outcome': 'error'})
        if mode == 'error':
            raise RuntimeError('stopped')
        if mode == 'interrupt':
            raise KeyboardInterrupt()
        if mode == 'sigterm':
            repair.signal.getsignal(repair.signal.SIGTERM)(repair.signal.SIGTERM, None)
        log.save('summary.json', {'exit_code': 2, 'stopped_error_rate': True})
        return {'exit_code': 2, 'stopped_error_rate': True}

    monkeypatch.setattr(repair, 'run', run)
    if mode == 'stop':
        assert repair.main() == 2
        assert json.loads(remote_file(storage, 'summary.json'))['stopped_error_rate']
    else:
        with pytest.raises({'error': RuntimeError, 'interrupt': KeyboardInterrupt, 'sigterm': InterruptedError}[mode]):
            repair.main()
    for name in ('audit.key', 'config.json', 'audit.jsonl', 'results.jsonl'):
        assert remote_file(storage, name) == (path / name).read_bytes()


def test_artifact_cli_resume_downloads_before_runlog(tmp_path, monkeypatch):
    client, runtime, source = setup(tmp_path)
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    evaluate(runtime, source)
    source.checkpoint(JOB_ID)
    mirror.upload(source.path)
    mirror.lease.close()
    path = tmp_path / 'ephemeral'
    artifact_cli(monkeypatch, storage, client, ['--resume', str(path), '--artifact-uri', 'gs://test-bucket/repair/run'])
    assert repair.main() == 0
    assert json.loads((path / 'summary.json').read_text())['processed'] == 0
    assert (path / 'audit.key').read_bytes() == (source.path / 'audit.key').read_bytes()


@pytest.mark.parametrize('suffix', ['/audit.jsonl', ''])
def test_artifact_cli_gs_rollback_downloads_source_and_mirrors_target(tmp_path, monkeypatch, suffix):
    client, runtime, source = setup(tmp_path, apply=True)
    assert evaluate(runtime, source)['outcome'] == 'written'
    storage = FakeStorage()
    source.artifacts = artifact(storage)
    source.artifacts.create()
    source.mirror()
    source.artifacts.lease.close()
    target = tmp_path / 'rollback'
    artifact_cli(
        monkeypatch,
        storage,
        client,
        [
            '--run-dir',
            str(target),
            '--rollback',
            'gs://test-bucket/repair/run' + suffix,
            '--artifact-uri',
            'gs://test-bucket/repair/rollback',
            '--apply',
            '--max-writes-per-second',
            '100000',
        ],
    )
    monkeypatch.setattr(repair.Runtime, 'sync', lambda *args: True)
    assert repair.main() == 0
    assert client.rows[ROW_PATH]['discarded'] is False
    assert json.loads(remote_file(storage, 'summary.json', prefix='repair/rollback/'))['outcomes'] == {'written': 1}
    assert remote_file(storage, 'audit.key', prefix='repair/rollback/') == (target / 'audit.key').read_bytes()


def test_artifact_failed_publication_keeps_previous_snapshot_and_can_resume(tmp_path, monkeypatch):
    _, runtime, source = setup(tmp_path)
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    mirror.upload(source.path)
    evaluate(runtime, source)
    original = mirror.manifest.upload_from_string

    def fail(*args, **kwargs):
        raise repair.ServiceUnavailable('offline')

    monkeypatch.setattr(mirror.manifest, 'upload_from_string', fail)
    with pytest.raises(repair.ServiceUnavailable):
        mirror.upload(source.path)
    # The uploaded audit is an orphan, never a partial published snapshot.
    _, data = storage.objects[('test-bucket', 'repair/run/manifest.json')]
    assert 'audit.jsonl' not in json.loads(data)['files']
    monkeypatch.setattr(mirror.manifest, 'upload_from_string', original)
    path = tmp_path / 'recover'
    path.mkdir()
    mirror.lease.close()
    resumed = artifact(storage)
    resumed.download(path)
    resumed.upload(source.path)
    assert remote_file(storage, 'audit.jsonl') == (source.path / 'audit.jsonl').read_bytes()


@pytest.mark.parametrize('corruption', ['checksum', 'path'])
def test_artifact_corrupt_manifest_fails_before_overwriting_local_files(tmp_path, corruption):
    _, _, log = setup(tmp_path)
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    mirror.upload(log.path)
    name = ('test-bucket', 'repair/run/manifest.json')
    generation, raw = storage.objects[name]
    snapshot = json.loads(raw)
    if corruption == 'checksum':
        snapshot['files']['audit.key']['sha256'] = 'invalid'
    else:
        snapshot['files']['../audit.key'] = snapshot['files'].pop('audit.key')
    storage.objects[name] = (generation, json.dumps(snapshot).encode())
    path = tmp_path / 'download'
    path.mkdir()
    (path / 'audit.key').write_bytes(b'local original')
    mirror.lease.close()
    with pytest.raises(ValueError):
        artifact(storage).download(path)
    assert (path / 'audit.key').read_bytes() == b'local original'


def test_artifact_nested_rollback_source_files_round_trip(tmp_path):
    _, _, log = setup(tmp_path)
    source = log.path / 'rollback-source'
    source.mkdir()
    (source / 'audit.key').write_bytes(b'source key')
    (source / 'run.lock').touch()
    storage = FakeStorage()
    mirror = artifact(storage)
    mirror.create()
    mirror.upload(log.path)
    assert remote_file(storage, 'rollback-source/audit.key') == b'source key'
    restored = tmp_path / 'restored'
    restored.mkdir()
    mirror.lease.close()
    artifact(storage).download(restored)
    assert (restored / 'rollback-source' / 'audit.key').read_bytes() == b'source key'
    assert not (restored / 'rollback-source' / 'run.lock').exists()


class DiskLost(BaseException):
    """Uncatchable process/disk loss; intentionally bypasses exit uploads."""


class ManualClock:
    def __init__(self):
        self.now = repair.time.time()

    def __call__(self):
        return self.now

    def expire(self):
        self.now += repair.RunLease.TTL + 1


def durable_run(log, storage, clock, uri='gs://test-bucket/repair/run'):
    mirror = artifact(storage, uri)
    mirror.lease.clock = clock
    mirror.create()
    log.artifacts = mirror
    log.mirror()
    return mirror


def recovered_run(tmp_path, storage, clock, config, uri='gs://test-bucket/repair/run', name='fresh'):
    path = tmp_path / name
    path.mkdir()
    mirror = artifact(storage, uri)
    mirror.lease.clock = clock
    mirror.download(path)
    log = repair.RunLog(path, config, resume=True)
    log.artifacts = mirror
    return log


def durable_objects(storage, kind, prefix='repair/run/'):
    return [
        json.loads(data)
        for (bucket, name), (_, data) in storage.objects.items()
        if bucket == 'test-bucket' and name.startswith(prefix + kind + '/')
    ]


def assert_durable_before_updates(monkeypatch, client, storage, prefix='repair/run/'):
    """Assert at the actual write boundary, independently of exit/checkpoints."""
    original = lambda **kwargs: Client.transaction(client, **kwargs)
    observed = []

    def transaction(**kwargs):
        tx = original(**kwargs)
        update = tx.update

        def checked(ref, patch):
            current = client.rows[ref.path]
            after = repair.patched(
                current,
                {
                    field: (
                        {'present': False}
                        if value is repair.firestore.DELETE_FIELD
                        else {'present': True, 'value': value}
                    )
                    for field, value in patch.items()
                },
            )
            matches = [
                intent
                for intent in durable_objects(storage, 'intents', prefix)
                if intent.get('before_digest') == repair.digest(current)
                and intent.get('after_digest') == repair.digest(after)
            ]
            assert matches, 'mutation has no published write-ahead intent'
            assert remote_file(storage, 'audit.key', prefix=prefix)
            observed.append(matches[-1]['decision_id'])
            update(ref, patch)
            for field, value in patch.items():
                if value is repair.firestore.DELETE_FIELD:
                    client.rows[ref.path].pop(field, None)
            if 'structured.title' in client.rows[ref.path]:
                client.rows[ref.path]['structured']['title'] = client.rows[ref.path].pop('structured.title')

        tx.update = checked
        return tx

    monkeypatch.setattr(client, 'transaction', transaction)
    return observed


@pytest.mark.parametrize('text', ['', TEXT])
def test_disk_loss_after_commit_before_checkpoint_recovers_intent_receipt_and_rollback(tmp_path, monkeypatch, text):
    client, runtime, source = setup(tmp_path, apply=True, kept=True, text=text)
    storage, clock = FakeStorage(), ManualClock()
    durable_run(source, storage, clock)
    observed = assert_durable_before_updates(monkeypatch, client, storage)
    write = repair.write_cas

    def commit_then_lose_disk(*args, **kwargs):
        result = write(*args, **kwargs)
        assert result['outcome'] == 'written'
        raise DiskLost()

    monkeypatch.setattr(repair, 'write_cas', commit_then_lose_disk)
    with pytest.raises(DiskLost):
        evaluate(runtime, source)
    assert len(observed) == 1
    assert not durable_objects(storage, 'receipts')
    assert 'audit.jsonl' not in json.loads(storage.objects[('test-bucket', 'repair/run/manifest.json')][1])['files']
    clock.expire()  # no graceful shutdown, release, checkpoint or finally upload
    recovered = recovered_run(tmp_path, storage, clock, source.config)
    assert not recovered.artifacts.lease.ready
    with pytest.raises(repair.LeaseLost, match='reconciliation'):
        recovered.before_mutation()
    monkeypatch.setattr(repair, 'write_cas', write)
    summary = repair.run(runtime, recovered, max_writes_per_second=100000)
    assert summary['processed'] == 0 and summary['projection_pending'] == 0
    assert len(client.transactions) == 1
    result = next(iter(recovered.results.values()))
    assert result['outcome'] == 'written' and result['projection_status'] == 'complete'
    assert durable_objects(storage, 'receipts')[-1]['projection_status'] == 'complete'
    target = repair.RunLog(tmp_path / 'undo', dict(source.config, rollback='source'))
    durable_run(target, storage, clock, 'gs://test-bucket/repair/undo')
    assert_durable_before_updates(monkeypatch, client, storage, prefix='repair/undo/')
    assert repair.rollback(runtime, recovered, target, qps=100000)['outcomes'] == {'written': 1}
    assert client.rows[ROW_PATH]['discarded'] is False
    assert client.rows[ROW_PATH]['structured']['title'] == ''


def test_frozen_run_publishes_each_page_and_recovers_all_written_rows(tmp_path, monkeypatch):
    client, runtime, log = setup(tmp_path, apply=True)
    storage, clock = FakeStorage(), ManualClock()
    durable_run(log, storage, clock)
    client.rows.clear()
    for index in range(6):
        cid, jid = f'conversation-{index}', f'job-{index}'
        client.rows[(repair.JOBS, jid)] = dict(job(), conversation_id=cid)
        client.rows[('users', UID, 'conversations', cid)] = dict(row(), finalization_job_id=jid)
    decode = runtime.decode

    def one_error(data, uid):
        if data['finalization_job_id'] == 'job-0':
            raise ValueError('ordinary read error')
        return decode(data, uid)

    runtime.decode = one_error
    pages = []
    upload = log.artifacts.upload

    def record_page(path):
        upload(path)
        pages.append(len(log.read('audit.jsonl')))

    monkeypatch.setattr(log.artifacts, 'upload', record_page)
    observed = assert_durable_before_updates(monkeypatch, client, storage)
    summary = repair.run(runtime, log, workers=2, page_size=2, max_writes_per_second=100000)
    assert summary['exit_code'] == 2 and summary['classes']['written'] == 5
    assert log.cursor is None  # error freezes discovery advancement only
    assert pages == [0, 2, 4, 6]
    assert len(observed) == 5 and len(durable_objects(storage, 'intents')) == 6
    clock.expire()
    recovered = recovered_run(tmp_path, storage, clock, log.config)
    repair.reconcile_pending(runtime, recovered)
    assert len([receipt for receipt in recovered.results.values() if receipt['outcome'] == 'written']) == 5


def test_rollback_disk_loss_has_durable_target_intent_and_recovers_completion(tmp_path, monkeypatch):
    client, runtime, source = setup(tmp_path, apply=True)
    storage, clock = FakeStorage(), ManualClock()
    durable_run(source, storage, clock)
    assert evaluate(runtime, source)['outcome'] == 'written'
    target = repair.RunLog(tmp_path / 'undo', dict(source.config, rollback='source'))
    uri = 'gs://test-bucket/repair/undo'
    durable_run(target, storage, clock, uri)
    observed = assert_durable_before_updates(monkeypatch, client, storage, prefix='repair/undo/')

    def lose_receipt(*args, **kwargs):
        raise DiskLost()

    monkeypatch.setattr(target, 'finish', lose_receipt)
    with pytest.raises(DiskLost):
        repair.rollback(runtime, source, target, qps=100000)
    assert client.rows[ROW_PATH]['discarded'] is False and len(observed) == 1
    assert durable_objects(storage, 'intents', prefix='repair/undo/')
    assert not durable_objects(storage, 'receipts', prefix='repair/undo/')
    clock.expire()
    restored_source = recovered_run(tmp_path, storage, clock, source.config, name='source-fresh')
    restored_target = recovered_run(tmp_path, storage, clock, target.config, uri, name='target-fresh')
    summary = repair.rollback(runtime, restored_source, restored_target, qps=100000)
    assert summary['projection_pending'] == 0 and not summary['outcomes']
    assert len(client.transactions) == 2  # forward and original rollback only
    assert next(iter(restored_target.results.values()))['outcome'] == 'written'
    assert durable_objects(storage, 'receipts', prefix='repair/undo/')[-1]['projection_status'] == 'complete'


def test_two_concurrent_resumes_admit_only_one_writer_and_all_writes_are_audited(tmp_path, monkeypatch):
    client, runtime, source = setup(tmp_path, apply=True)
    other_job, other_cid = 'job-two', 'conversation-two'
    client.rows[(repair.JOBS, other_job)] = dict(job(), conversation_id=other_cid)
    other_path = ('users', UID, 'conversations', other_cid)
    client.rows[other_path] = dict(row(), finalization_job_id=other_job)
    storage, clock = FakeStorage(), ManualClock()
    durable_run(source, storage, clock)
    clock.expire()
    barrier = threading.Barrier(2)

    def resume(name):
        path = tmp_path / name
        path.mkdir()
        mirror = artifact(storage)
        mirror.lease.clock = clock
        barrier.wait(timeout=5)
        try:
            mirror.download(path)
            log = repair.RunLog(path, source.config, resume=True)
            log.artifacts = mirror
            return log, mirror
        except repair.LeaseLost:
            return None, mirror

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(resume, name) for name in ('one', 'two')]
        runs = [future.result() for future in futures]
    assert sum(run is not None for run, _ in runs) == 1
    winner = next(run for run, _ in runs if run is not None)
    loser_mirror = next(mirror for run, mirror in runs if run is None)
    observed = assert_durable_before_updates(monkeypatch, client, storage)
    repair.reconcile_pending(runtime, winner)
    assert evaluate(runtime, winner)['outcome'] == 'written'
    # Even a losing writer that continues classification on a different row
    # cannot publish an intent or enter that row's Firestore transaction.
    loser = repair.RunLog(tmp_path / 'losing-work', source.config)
    loser.artifacts = loser_mirror
    with pytest.raises(repair.LeaseLost):
        repair.evaluate(runtime, loser, other_job, limiter=repair.RateLimiter(100000))
    with pytest.raises(repair.LeaseLost):
        source.before_mutation()
    assert client.rows[other_path]['discarded'] is False
    assert len(observed) == 1 and len(client.transactions) == 1
    assert len(durable_objects(storage, 'intents')) == 1


@pytest.mark.parametrize('stage', ['intent_upload', 'lease_after_intent', 'lease_inside_transaction'])
def test_artifact_or_lease_failure_prevents_mutation(tmp_path, monkeypatch, stage):
    client, runtime, log = setup(tmp_path, apply=True)
    storage, clock = FakeStorage(), ManualClock()
    mirror = durable_run(log, storage, clock)
    original = FakeBlob.upload_from_string

    def upload(blob, *args, **kwargs):
        if '/intents/' in blob.name:
            if stage == 'intent_upload':
                raise repair.ServiceUnavailable('unavailable')
            result = original(blob, *args, **kwargs)
            if stage == 'lease_after_intent':
                key = ('test-bucket', 'repair/run/lease.json')
                generation, data = storage.objects[key]
                storage.objects[key] = (generation + 1000, data)
            return result
        return original(blob, *args, **kwargs)

    monkeypatch.setattr(FakeBlob, 'upload_from_string', upload)
    if stage == 'lease_inside_transaction':

        def expire_during_revalidation(ref, data, job, transaction):
            if transaction is not None:
                clock.expire()
            return None

        runtime.protections = expire_during_revalidation
    with pytest.raises(repair.ArtifactError):
        evaluate(runtime, log)
    assert client.rows[ROW_PATH]['discarded'] is False
    assert all(not transaction.updates for transaction in client.transactions)


def test_receipt_upload_failure_is_recovered_from_published_intent(tmp_path, monkeypatch):
    client, runtime, source = setup(tmp_path, apply=True)
    storage, clock = FakeStorage(), ManualClock()
    durable_run(source, storage, clock)
    original = FakeBlob.upload_from_string

    def fail_receipt(blob, *args, **kwargs):
        if '/receipts/' in blob.name:
            raise repair.ServiceUnavailable('no receipt')
        return original(blob, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(FakeBlob, 'upload_from_string', fail_receipt)
        with pytest.raises(repair.ArtifactError):
            evaluate(runtime, source)
    assert client.rows[ROW_PATH]['discarded'] is True
    assert len(durable_objects(storage, 'intents')) == 1 and not durable_objects(storage, 'receipts')
    clock.expire()
    resumed = recovered_run(tmp_path, storage, clock, source.config)
    summary = repair.run(runtime, resumed, max_writes_per_second=100000)
    assert summary['projection_pending'] == 0 and len(client.transactions) == 1


def test_ambiguous_intent_upload_requires_identical_durable_bytes_before_commit(tmp_path, monkeypatch):
    client, runtime, log = setup(tmp_path, apply=True)
    storage, clock = FakeStorage(), ManualClock()
    durable_run(log, storage, clock)
    observed = assert_durable_before_updates(monkeypatch, client, storage)
    original = FakeBlob.upload_from_string

    def response_lost(blob, *args, **kwargs):
        result = original(blob, *args, **kwargs)
        if '/intents/' in blob.name:
            raise repair.DeadlineExceeded('response lost')
        return result

    monkeypatch.setattr(FakeBlob, 'upload_from_string', response_lost)
    assert evaluate(runtime, log)['outcome'] == 'written' and len(observed) == 1


def test_lease_heartbeat_renews_periodically_and_stops_on_lost_generation(tmp_path, monkeypatch):
    _, _, log = setup(tmp_path)
    storage, clock = FakeStorage(), ManualClock()
    mirror = durable_run(log, storage, clock)
    called = threading.Event()
    renew = mirror.lease.renew

    def observed(**kwargs):
        try:
            renew(**kwargs)
        finally:
            called.set()

    monkeypatch.setattr(mirror.lease, 'TTL', 0.03)
    monkeypatch.setattr(mirror.lease, 'renew', observed)
    generation = mirror.lease.generation
    mirror.lease.start()
    assert called.wait(timeout=2)
    assert mirror.lease.generation > generation
    called.clear()
    key = ('test-bucket', 'repair/run/lease.json')
    with storage.lock:
        generation, data = storage.objects[key]
        storage.objects[key] = (generation + 1000, data)
    assert called.wait(timeout=2)
    mirror.lease.close()
    assert mirror.lease.lost and mirror.lease.stop.is_set()

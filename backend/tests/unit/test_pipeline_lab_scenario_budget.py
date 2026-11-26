"""Pipeline-lab scenario budgets: the Firestore op counter, the no-op write detector, budget checks and the
format additions (budget, account, seed, repeated Finish taps, response / recording / paging checks).

Pure: the GAPIC API is a fake with the same request and response shapes the Firestore SDK uses."""

import copy
from contextlib import ExitStack
from types import SimpleNamespace

import pytest
from google.cloud.firestore_v1.types import firestore as firestore_types, write as write_types, document
from google.protobuf import timestamp_pb2

from testing.pipeline_lab.scenario import budget, home
from testing.pipeline_lab.scenario.checks import evaluate, finish_tap_row, outcome
from testing.pipeline_lab.scenario.spec import ScenarioError, parse_scenario, plan_events, seed_plan
from testing.pipeline_lab.scenario.verdict import scenario_verdict

ROOT = 'projects/demo-lab/databases/(default)/documents'


def doc(path):
    return f'{ROOT}/{path}'


def stamp(seconds, nanos=0):
    return timestamp_pb2.Timestamp(seconds=seconds, nanos=nanos)


class FakeApi:
    """The GAPIC members the wrapper intercepts, answering with real proto-plus response types."""

    def __init__(self):
        self.found = {}
        self.commit_results = []
        self.transport = 'transport'

    def batch_get_documents(self, request=None, **kwargs):
        for name in request['documents']:
            if name in self.found:
                yield firestore_types.BatchGetDocumentsResponse(found=document.Document(name=name))
            else:
                yield firestore_types.BatchGetDocumentsResponse(missing=name)

    def run_query(self, request=None, **kwargs):
        for name in self.found:
            if name.startswith(request['parent'] + '/' + request['structured_query'].from_[0].collection_id + '/'):
                yield firestore_types.RunQueryResponse(document=document.Document(name=name))

    def commit(self, request=None, **kwargs):
        response = firestore_types.CommitResponse(commit_time=stamp(100, 5))
        for update_time in self.commit_results:
            response.write_results.append(write_types.WriteResult(update_time=update_time))
        return response


def counted(api=None):
    api = api or FakeApi()
    client = SimpleNamespace(_firestore_api=api, _firestore_api_internal=api)
    counter = budget.OpCounter()
    stack = ExitStack()
    budget.install(stack, client, counter)
    counter.start()
    return client._firestore_api_internal, counter, api, stack


def query(parent, collection):
    from google.cloud.firestore_v1.types import query as query_types

    structured = query_types.StructuredQuery(
        from_=[query_types.StructuredQuery.CollectionSelector(collection_id=collection)]
    )
    return {'parent': parent, 'structured_query': structured}


def update(name):
    return write_types.Write(update=document.Document(name=name))


# ---- the counter -----------------------------------------------------------------------------------


def test_reads_are_counted_per_document_including_missing_and_empty_queries():
    wrapped, counter, api, stack = counted()
    api.found = {doc('users/u/conversations/a'): 1, doc('users/u/conversations/b'): 1}
    list(wrapped.batch_get_documents(request={'documents': [doc('users/u/conversations/a'), doc('testers/x')]}))
    assert len(list(wrapped.run_query(request=query(doc('users/u'), 'conversations')))) == 2
    list(wrapped.run_query(request=query(ROOT, 'testers')))  # empty: billed one read
    summary = counter.summary()
    assert summary['reads'] == 5
    assert summary['by_path']['users/conversations']['reads'] == 3
    assert summary['by_path']['testers']['reads'] == 2
    assert summary['by_collection']['users']['reads'] == 3
    stack.close()


def test_commit_counts_writes_and_deletes_and_flags_no_op_writes():
    wrapped, counter, api, stack = counted()
    # The second update kept the document's previous update_time: the write changed nothing.
    api.commit_results = [stamp(100, 5), stamp(90, 0), write_types.WriteResult()._pb.update_time]
    writes = [
        update(doc('users/u/conversations/a')),
        update(doc('users/u/conversation_v3_leases/k')),
        write_types.Write(delete=doc('users/u/conversations/c')),
    ]
    wrapped.commit(request={'database': 'd', 'writes': writes})
    summary = counter.summary()
    assert (summary['writes'], summary['deletes'], summary['noop_writes']) == (2, 1, 1)
    assert summary['by_path']['users/conversation_v3_leases']['noop_writes'] == 1
    (site,) = summary['noop_sites']
    assert site.startswith('tests/unit/test_pipeline_lab_scenario_budget.py:')
    stack.close()


def test_a_failed_commit_counts_nothing():
    api = FakeApi()

    def aborted(request=None, **kwargs):
        raise RuntimeError('aborted')

    api.commit = aborted
    wrapped, counter, _, stack = counted(api)
    with pytest.raises(RuntimeError):
        wrapped.commit(request={'writes': [update(doc('users/u/conversations/a'))]})
    assert counter.summary()['writes'] == 0
    stack.close()


def test_lab_scope_is_shown_but_not_budgeted_and_counting_waits_for_start():
    wrapped, counter, api, stack = counted()
    counter.stop()
    list(wrapped.batch_get_documents(request={'documents': [doc('users/u')]}))
    counter.start()
    with budget.lab_io():
        list(wrapped.batch_get_documents(request={'documents': [doc('users/u')]}))
    with budget.scope('home'):
        list(wrapped.batch_get_documents(request={'documents': [doc('users/u')]}))
    summary = counter.summary()
    assert summary['reads'] == 1
    assert summary['by_scope']['lab']['reads'] == 1
    assert summary['by_scope']['home']['reads'] == 1
    assert summary['by_scope']['pipeline']['reads'] == 0
    stack.close()


def test_install_restores_the_real_api_and_delegates_other_members():
    api = FakeApi()
    client = SimpleNamespace(_firestore_api=api, _firestore_api_internal=api)
    with ExitStack() as stack:
        budget.install(stack, client, budget.OpCounter())
        assert isinstance(client._firestore_api_internal, budget.CountingFirestoreApi)
        assert client._firestore_api_internal.transport == 'transport'
    assert client._firestore_api_internal is api


def test_collection_path_and_call_site():
    assert budget.collection_path(doc('users/u/conversations/c')) == ('users', 'users/conversations')
    assert budget.collection_path(doc('testers')) == ('testers', 'testers')
    assert budget.collection_path(ROOT) == ('(root)', '(root)')
    frames = [
        SimpleNamespace(
            filename=str(budget.BACKEND / 'utils/conversations/v3/service.py'), lineno=10, name='reconcile'
        ),
        SimpleNamespace(filename=str(budget.BACKEND / 'database/conversations_v3_leases.py'), lineno=72, name='renew'),
        SimpleNamespace(filename=str(budget.BACKEND / 'database/transcript_pointer.py'), lineno=410, name='<lambda>'),
        SimpleNamespace(filename=str(budget.BACKEND / 'database/_client.py'), lineno=5, name='commit'),
        SimpleNamespace(filename='/x/site-packages/google/cloud/firestore_v1/batch.py', lineno=1, name='commit'),
    ]
    assert budget.call_site(frames) == (
        'database/conversations_v3_leases.py:72 renew <- utils/conversations/v3/service.py:10 reconcile'
    )


def test_vendor_counts_and_budget_evaluation():
    vendor = budget.vendor_counts(
        transcribe_calls=1, cassette_plays=1, llm_paths=['/v1/chat/completions', '/v1/chat/completions?x=1']
    )
    assert vendor['stt'] == 2 and vendor['llm'] == 2
    assert vendor['llm_by_path'] == {'/v1/chat/completions': 2}
    ops = {'reads': 10, 'writes': 3, 'deletes': 0, 'noop_writes': 1, 'vendor_calls': vendor}
    assert budget.evaluate_budget('reads', 10, ops)[0] is True
    assert budget.evaluate_budget('noop_writes', 0, ops) == (False, 'noop_writes=1 (budget 0)', 1)
    assert budget.evaluate_budget('stt', 1, ops)[0] is False
    assert budget.evaluate_budget('reads', 10, None)[0] is False
    rows = budget.table_rows(ops, {'reads': 12, 'vendor_calls': {'stt': 1}})
    assert {r['key']: r['ok'] for r in rows} == {
        'reads': True, 'writes': None, 'deletes': None, 'noop_writes': None, 'vendor stt': False, 'vendor llm': None,
    }  # fmt: skip


# ---- the format -------------------------------------------------------------------------------------

FILL = [{'fill': [0, 40], 'every': 4, 'words': 10}]
BASE = {
    'name': 'tiny',
    'origins': [{'id': 'O'}],
    'recordings': [{'id': 'B', 'origin': 'O', 'session': 'S1', 'audio': [0, 40], 'transcript_at': 90, 'speech': FILL}],
    'finish': {'at': 38, 'again_at': [38.5]},
    'expect': [{'conversation_of': '@finish', 'visible': True}],
}


def scenario(**changes):
    raw = copy.deepcopy(BASE)
    raw.update(changes)
    return parse_scenario(raw)


def test_budget_block_becomes_labelled_checks():
    parsed = scenario(budget={'writes': 40, 'noop_writes': 0, 'vendor_calls': {'stt': 1}, 'note': 'why'})
    labels = [c.label for c in parsed.checks if c.budget]
    assert labels == ['budget_writes', 'budget_noop_writes', 'budget_vendor_stt']
    assert parsed.budget['note'] == 'why'
    failing = scenario(
        budget={'writes': 1, 'reads': 5},
        expect=[{'label': 'shown', 'conversation_of': '@finish', 'visible': True}],
        expected_failure={'reason': 'x', 'checks': ['budget_writes']},
    )
    ops = {'writes': 2, 'reads': 5}
    results = [
        evaluate(c, [{'handle': 'h', 'recordings': ['B'], 'visible': True}], 'B', {'ops': ops}) for c in failing.checks
    ]
    assert [r.ok for r in results] == [True, True, False]  # shown, budget_reads (5 <= 5), budget_writes (2 > 1)
    assert outcome(failing, results) == 'xfail'
    with pytest.raises(ScenarioError):
        scenario(budget={'writes': -1})
    with pytest.raises(ScenarioError):
        scenario(budget={'vendor_calls': {'tts': 1}})
    with pytest.raises(ScenarioError):
        scenario(budget={'note': 'nothing capped'})


def test_finish_taps_account_and_live_lane_plan():
    parsed = scenario(account={'private_cloud_sync_enabled': True, 'sync_off_at': 45})
    kinds = [(parsed.offset(e.instant), e.kind, e.ref) for e in plan_events(parsed)]
    assert (38.0, 'finish', 'finish') in kinds and (38.5, 'finish', 'finish#2') in kinds
    assert (45.0, 'account', 'sync_off') in kinds
    live = scenario(account={'private_cloud_sync_enabled': False}, finish={'at': 50})
    assert not live.batch_lane
    assert 'admission' not in {e.kind for e in plan_events(live)}
    with pytest.raises(ScenarioError):
        scenario(finish={'at': 38, 'again_at': [37]})
    with pytest.raises(ScenarioError):
        scenario(account={'private_cloud_sync_enabled': False, 'sync_off_at': 3})


def test_new_check_targets_validate():
    parsed = scenario(
        expect=[
            {'label': 'r', 'finish_response': 2, 'outcome': 'in_progress'},
            {'label': 'f', 'recording': 'B', 'fast_finish': 'written'},
            {'label': 'h', 'conversation_of': 'B', 'holders': 1, 'home_titled': True},
            {'label': 'p', 'home_paging': 'visible_once'},
        ],
        seed=[{'kind': 'visible', 'count': 2}, {'kind': 'recording', 'count': 1}],
    )
    assert [c.label for c in parsed.checks] == ['r', 'f', 'h', 'p']
    bad = [
        {'finish_response': 3, 'outcome': 'in_progress'},  # only two taps
        {'finish_response': 1, 'outcome': 'maybe'},
        {'recording': 'B', 'visible': True},
        {'conversation_of': 'B', 'holders': True},
        {'home_paging': 'visible_once', 'at': 10},
        {'recording': 'B', 'conversation_of': 'B', 'fast_finish': 'written'},
    ]
    for row in bad:
        with pytest.raises(ScenarioError):
            scenario(expect=[row], seed=[{'kind': 'visible', 'count': 1}])
    with pytest.raises(ScenarioError):  # paging needs seeded visible rows
        scenario(expect=[{'home_paging': 'visible_once'}])


def test_seed_plan_keeps_order_and_unique_handles():
    parsed = scenario(seed=[{'kind': 'visible', 'count': 2}, {'kind': 'below_word_minimum', 'count': 3}])
    plan = seed_plan(parsed)
    assert [kind for _, kind, _ in plan] == ['visible'] * 2 + ['below_word_minimum'] * 3
    assert [minutes for _, _, minutes in plan] == [1, 2, 3, 4, 5]
    assert len({home.handle_of(doc_id) for doc_id, _, _ in plan}) == 5
    with pytest.raises(ScenarioError):
        scenario(seed=[{'kind': 'archived', 'count': 1}])


def test_new_checks_evaluate_from_facts():
    parsed = scenario(
        expect=[
            {'label': 'r', 'finish_response': 1, 'outcome': 'no_pointer', 'titled': True, 'recordings_include': ['B']},
            {'label': 'f', 'recording': 'B', 'fast_finish': 'privacy_blocked'},
            {'label': 'h', 'conversation_of': 'B', 'holders': 1},
        ]
    )
    tap = finish_tap_row(
        'no_pointer',
        {'id': 'scn-b', 'recording': True, 'structured': {'title': 'T'}},
        lambda i: 'B' if i == 'scn-b' else '?',
    )
    assert tap['recordings'] == ['B'] and tap['titled'] and not tap['has_notes']
    facts = {'finish_taps': [tap], 'fast_finish': {}}
    rows = [
        {'handle': 'h1', 'recordings': ['B'], 'visible': True},
        {'handle': 'h2', 'recordings': ['B'], 'visible': False},
    ]
    r, f, h = [evaluate(c, rows, 'B', facts) for c in parsed.checks]
    assert r.ok
    assert not f.ok and "'none'" in f.detail
    assert not h.ok and h.detail == 'holders=2 (want 1)'


def test_paging_check_and_walk():
    visible, hidden = ['aaaaaaaa', 'bbbbbbbb'], ['cccccccc']
    verdict = home.paging_verdict({'pages': [{}], 'handles': ['aaaaaaaa', 'aaaaaaaa', 'cccccccc']}, visible, hidden)
    assert verdict['missing'] == ['bbbbbbbb'] and verdict['duplicated'] == ['aaaaaaaa']
    assert verdict['hidden_seen'] == ['cccccccc']
    parsed = scenario(expect=[{'label': 'p', 'home_paging': 'visible_once'}], seed=[{'kind': 'visible', 'count': 1}])
    assert not evaluate(parsed.checks[0], [], None, {'paging': verdict}).ok
    good = home.paging_verdict({'pages': [{}], 'handles': visible}, visible, hidden)
    assert evaluate(parsed.checks[0], [], None, {'paging': good}).ok


def test_walk_pages_follows_storage_count_cursor_and_has_more():
    import asyncio

    pages = {
        '0': (
            ['a1', 'a2'],
            {'x-omi-conversation-page-size': '50', 'x-omi-has-more': 'true', 'x-omi-next-cursor': 'c1'},
        ),
        '50': (['b1'], {'x-omi-conversation-page-size': '40', 'x-omi-has-more': 'false'}),
    }
    seen = []

    async def app(scope, receive, send):
        query = dict(part.split('=', 1) for part in scope['query_string'].decode().split('&'))
        seen.append((query['offset'], query.get('cursor'), dict(scope['headers']).get(b'x-omi-home-page-mode')))
        ids, headers = pages[query['offset']]
        body = ('[' + ','.join('{"id": "%s"}' % i for i in ids) + ']').encode()
        raw = [(k.encode(), v.encode()) for k, v in {**headers, 'x-omi-home-page-mode': 'indexed'}.items()]
        await send({'type': 'http.response.start', 'status': 200, 'headers': raw})
        await send({'type': 'http.response.body', 'body': body})

    walk = asyncio.run(home.walk_pages(app))
    assert walk['handles'] == ['a1', 'a2', 'b1'] and 'error' not in walk
    assert seen == [('0', None, b'auto'), ('50', 'c1', b'indexed')]
    assert [p['has_more'] for p in walk['pages']] == [True, False]


def test_verdict_row_carries_ops_and_budget_actuals():
    parsed = scenario(budget={'reads': 3})
    ops = {'reads': 4, 'writes': 1, 'deletes': 0, 'noop_writes': 0, 'vendor_calls': {'stt': 0, 'llm': 2}}
    result = {
        'outcome': 'failed',
        'checks': [{'check': c.describe(), 'ok': False} for c in parsed.checks],
        'ops': ops,
        'budget': parsed.budget,
        'conversations': [],
    }
    row = scenario_verdict('tiny', result, parsed)
    assert row['ops']['reads'] == 4
    budget_row = row['checks'][-1]
    assert budget_row['label'] == 'budget_reads'
    assert budget_row['expected'] == {'budget': 'reads', 'at_most': 3}
    assert budget_row['actual'] == {'budget': 'reads', 'count': 4}
    assert {r['key']: r['count'] for r in row['ops_table']}['vendor llm'] == 2


def test_reads_through_a_wall_clock_cache_are_kept_apart():
    from testing.pipeline_lab.determinism import WALL_CLOCK_FIELDS

    wrapped, counter, _, stack = counted()
    list(wrapped.batch_get_documents(request={'documents': [doc('dream_control/global'), doc('users/u')]}))
    summary = counter.summary()
    assert summary['reads'] == 1
    assert summary['wall_clock_reads'] == {'dream_control': 1}
    assert 'dream_control' not in summary['by_collection']
    assert 'wall_clock_reads' in WALL_CLOCK_FIELDS
    stack.close()


def test_write_sites_are_traced_only_when_asked():
    api = FakeApi()
    api.commit_results = [stamp(100, 5)]
    client = SimpleNamespace(_firestore_api=api, _firestore_api_internal=api)
    for traced in (False, True):
        counter = budget.OpCounter(write_sites=traced)
        with ExitStack() as stack:
            budget.install(stack, client, counter)
            counter.start()
            client._firestore_api_internal.commit(request={'writes': [update(doc('users/u'))]})
        summary = counter.summary()
        assert ('write_sites' in summary) is traced
        if traced:
            (site,) = summary['write_sites']
            assert site.startswith('users writes: tests/unit/test_pipeline_lab_scenario_budget.py:')

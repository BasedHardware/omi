"""guard_eval excludes only Sync 503s matched one-to-one to a designed-refusal record.

Offline: Cloud Logging is an in-memory fake keyed on the filter it receives.
"""

import json
from unittest.mock import Mock, patch

import pytest

from scripts import guard_eval

CANDIDATE, INVERSE = 'backend-sync-candidate', 'backend-sync-inverse'
START, END = 1795644000, 1795644300


def trace(number, side='c'):
    return f'{side}{number:031x}'


def request_log(revision, status, number, side='c'):
    return {
        'resource': {'labels': {'revision_name': revision}},
        'httpRequest': {'status': status},
        'trace': f'projects/based-hardware/traces/{trace(number, side)}',
    }


def record(revision, number, side='c', *, at=START + 150, text=None):
    # The shared text formatter: '%(levelname)s %(name)s: %(message)s' on stdout.
    line = text or (
        f'INFO routers.sync: sync_upload_refused uid=u{number} status=503 '
        f'reason=backfill_day_cap trace={trace(number, side)}'
    )
    return {
        'resource': {'labels': {'revision_name': revision}},
        'textPayload': line,
        'timestamp': guard_eval.stamp(at).replace('Z', '.250000000Z'),
    }


@pytest.fixture
def telemetry():
    return guard_eval.Telemetry(Mock(), 'based-hardware', 'us-central1')


ROUTE = guard_eval.policy_for('backend-sync')['routes']['sync-local-files']


def read(telemetry, responses, records):
    calls = []

    def respond(url, params, body):
        calls.append((params['fields'], body['filter']))
        stdout = 'run.googleapis.com%2Fstdout' in body['filter']
        return {'entries': records if stdout else responses}

    with patch.object(telemetry, 'request', side_effect=respond):
        counts = telemetry.refusal_counts('backend-sync', CANDIDATE, INVERSE, START, END, ROUTE)
    return counts, calls


def side(route, records):
    errors = sum(value for status, value in route.items() if int(status) >= 500)
    successes = 10 * sum(value for status, value in route.items() if int(status) < 400)
    return {
        'service': {'2xx': successes, '5xx': errors},
        'routes': {'sync-local-files': route},
        'refusal_records': {'sync-local-files': {'503': records.get(503, 0)}},
    }


def score(candidate_route, candidate_records, inverse_route, inverse_records):
    policy = guard_eval.policy_for('backend-sync', ['sync-local-files'])
    return guard_eval.evaluate(policy, side(candidate_route, candidate_records), side(inverse_route, inverse_records))


def test_mixed_designed_and_real_dispatch_503s_trip_when_real_503s_regress(telemetry):
    # Candidate: one designed backfill_day_cap refusal with its record, plus
    # sync_dispatch_unavailable 503s, which write no record. Inverse: one
    # designed refusal and one real 503.
    responses = [request_log(CANDIDATE, 503, n) for n in range(41)]
    responses += [request_log(INVERSE, 503, n, '1') for n in range(2)]
    counts, _ = read(telemetry, responses, [record(CANDIDATE, 0), record(INVERSE, 0, '1')])
    assert counts == {CANDIDATE: {503: 1}, INVERSE: {503: 1}}
    result = score({'200': 400, '503': 41}, counts[CANDIDATE], {'200': 400, '503': 2}, counts[INVERSE])
    assert result['verdict'] == 'TRIP', result
    route = result['checks']['sync-local-files']
    assert (route['candidate']['5xx'], route['candidate']['excluded_5xx']) == (40, 1)
    assert (route['inverse']['5xx'], route['inverse']['excluded_5xx']) == (1, 1)
    # A blanket 503 exclusion would have hidden every one of these.
    assert score({'200': 400, '503': 41}, {503: 41}, {'200': 400, '503': 2}, {503: 2})['verdict'] == 'PASS'


def test_designed_refusals_alone_do_not_trip(telemetry):
    responses = [request_log(CANDIDATE, 503, n) for n in range(2500)]
    records = [record(CANDIDATE, n, at=START + 30 + n % 240) for n in range(2500)]
    counts, _ = read(telemetry, responses, records)
    assert counts == {CANDIDATE: {503: 2500}, INVERSE: {}}
    result = score({'200': 150, '503': 2500}, counts[CANDIDATE], {'200': 400}, counts[INVERSE])
    assert result['verdict'] == 'PASS', result
    assert result['checks']['sync-local-files']['candidate']['5xx'] == 0


def test_more_records_than_503s_is_insufficient_data(telemetry):
    result = score({'200': 400, '503': 5}, {503: 6}, {'200': 400}, {})
    assert (result['verdict'], result['reason'], result['checks']) == (
        'INSUFFICIENT_DATA',
        'refusal_records_records_exceed_route_responses',
        {},
    )
    responses = [request_log(CANDIDATE, 503, n) for n in range(5)]
    with pytest.raises(guard_eval.RefusalRecordsUnreconciled) as raised:
        read(telemetry, responses, [record(CANDIDATE, n) for n in range(6)])
    assert raised.value.reason == 'unmatched_record'


@pytest.mark.parametrize(
    'reason, records',
    [
        ('revision_mismatch', [record(INVERSE, 0)]),
        ('duplicate_record', [record(CANDIDATE, 0), record(CANDIDATE, 0)]),
        (
            'unparseable_record',
            [record(CANDIDATE, 0, text='INFO routers.sync: sync_upload_refused uid=u0 status=503 reason=x')],
        ),
    ],
)
def test_unreconcilable_records_raise(telemetry, reason, records):
    responses = [request_log(CANDIDATE, 503, 0), request_log(INVERSE, 503, 0, '1')]
    with pytest.raises(guard_eval.RefusalRecordsUnreconciled) as raised:
        read(telemetry, responses, records)
    assert raised.value.reason == reason


def test_duplicate_request_trace_is_unreconcilable(telemetry):
    with pytest.raises(guard_eval.RefusalRecordsUnreconciled) as raised:
        read(telemetry, [request_log(CANDIDATE, 503, 0), request_log(CANDIDATE, 503, 0)], [])
    assert raised.value.reason == 'duplicate_request_trace'


def test_unread_or_undeclared_records_are_insufficient_data():
    policy = guard_eval.policy_for('backend-sync', ['sync-local-files'])
    unread = {'service': {'2xx': 4000, '5xx': 5}, 'routes': {'sync-local-files': {'200': 400, '503': 5}}}
    undeclared = {
        'service': {'2xx': 4000, '5xx': 5},
        'routes': {'sync-local-files': {'200': 400, '500': 5}},
        'refusal_records': {'sync-local-files': {'500': 5}},
    }
    for reason, aggregate in (('unread', unread), ('undeclared_status', undeclared)):
        result = guard_eval.evaluate(policy, aggregate, aggregate)
        assert (result['verdict'], result['reason']) == ('INSUFFICIENT_DATA', 'refusal_records_' + reason)


def test_records_beyond_service_5xx_hold():
    policy = guard_eval.policy_for('backend-sync')
    aggregate = {
        'service': {'2xx': 5000, '5xx': 1},
        'routes': {'sync-local-files': {'503': 2}},
        'refusal_records': {'sync-local-files': {'503': 2}},
    }
    result = guard_eval.evaluate(policy, aggregate, aggregate)
    assert (result['verdict'], result['reason']) == ('INSUFFICIENT_DATA', 'refusal_records_exceed_service_5xx')


def test_read_window_holds_on_unreconciled_records(telemetry):
    series = {CANDIDATE: {'2xx': 900}, INVERSE: {'2xx': 900}}
    failure = guard_eval.RefusalRecordsUnreconciled('unmatched_record')
    with patch.object(guard_eval, 'Telemetry', return_value=telemetry), patch.object(
        telemetry, 'service_counts', return_value=series
    ), patch.object(telemetry, 'log_counts', return_value={CANDIDATE: {}, INVERSE: {}}), patch.object(
        telemetry, 'route_counts', return_value={CANDIDATE: {503: 1}, INVERSE: {}}
    ), patch.object(
        telemetry, 'refusal_counts', side_effect=failure
    ):
        result = guard_eval.read_window('backend-sync', CANDIDATE, INVERSE, START, END, route_names=[])
    assert (result['verdict'], result['reason'], result['checks']) == (
        'INSUFFICIENT_DATA',
        'refusal_records_unmatched_record',
        {},
    )


def test_read_window_scores_matched_records(telemetry):
    series = {CANDIDATE: {'2xx': 4000, '5xx': 41}, INVERSE: {'2xx': 4000, '5xx': 2}}
    logs = {CANDIDATE: {503: 41}, INVERSE: {503: 2}}
    routes = {CANDIDATE: {200: 400, 503: 41}, INVERSE: {200: 400, 503: 2}}
    with patch.object(guard_eval, 'Telemetry', return_value=telemetry), patch.object(
        telemetry, 'service_counts', return_value=series
    ), patch.object(telemetry, 'log_counts', return_value=logs), patch.object(
        telemetry, 'route_counts', return_value=routes
    ), patch.object(
        telemetry, 'refusal_counts', return_value={CANDIDATE: {503: 1}, INVERSE: {503: 1}}
    ):
        result = guard_eval.read_window(
            'backend-sync', CANDIDATE, INVERSE, START, END, route_names=['sync-local-files']
        )
    assert result['verdict'] == 'TRIP', result
    assert result['checks']['sync-local-files']['candidate']['excluded_5xx'] == 1


def test_edge_records_are_ignored_and_filters_scope_route_revision_and_window(telemetry):
    slack = guard_eval.REFUSAL_RECORD_SLACK_SECONDS
    records = [
        record(CANDIDATE, 0, at=END + slack - 1),  # its request is in the window
        record(CANDIDATE, 7, at=START - slack + 1),  # request before the window
        record(CANDIDATE, 8, at=END + 30),  # request after the window
    ]
    counts, calls = read(telemetry, [request_log(CANDIDATE, 503, 0)], records)
    assert counts == {CANDIDATE: {503: 1}, INVERSE: {}}
    (request_fields, request_filter), (record_fields, record_filter) = calls
    assert request_fields == 'entries(resource/labels,httpRequest/status,trace),nextPageToken'
    assert 'run.googleapis.com%2Frequests' in request_filter
    assert 'httpRequest.requestUrl =~ "^https?://[^/?#]+/v2/sync-local-files/?(?:[?#]|$)"' in request_filter
    assert '(httpRequest.status=503)' in request_filter
    assert record_fields == 'entries(resource/labels,textPayload,timestamp),nextPageToken'
    assert 'logName="projects/based-hardware/logs/run.googleapis.com%2Fstdout"' in record_filter
    assert 'textPayload:"sync_upload_refused "' in record_filter
    assert f'timestamp>"{guard_eval.stamp(START - slack)}"' in record_filter
    assert f'timestamp<="{guard_eval.stamp(END + slack)}"' in record_filter


def test_record_reads_share_the_page_budget(telemetry):
    telemetry.log_pages_left = 1
    with patch.object(telemetry, 'request', return_value={'entries': [], 'nextPageToken': 'more'}):
        with pytest.raises(guard_eval.LogPageBudgetExceeded):
            telemetry.refusal_counts('backend-sync', CANDIDATE, INVERSE, START, END, ROUTE)


@pytest.mark.parametrize(
    'route',
    [
        {'refusal_statuses': [503]},
        {'designed_refusals': {'record': 'sync_upload_refused', 'statuses': [429]}},
        {'designed_refusals': {'record': 'Bad Name', 'statuses': [503]}},
        {'designed_refusals': {'record': 'sync_upload_refused', 'statuses': []}},
        {'designed_refusals': {'record': 'sync_upload_refused', 'statuses': [503], 'x': 1}},
        {'designed_refusals': [503]},
    ],
)
def test_policy_rejects_the_blanket_exclusion_and_malformed_specs(monkeypatch, tmp_path, route):
    config = json.loads(guard_eval.CONFIG.read_text())
    config['services']['backend-sync']['sync-local-files'] = {
        'method': 'POST',
        'path': '/v2/sync-local-files',
        **route,
    }
    broken = tmp_path / 'guard.json'
    broken.write_text(json.dumps(config))
    monkeypatch.setattr(guard_eval, 'CONFIG', broken)
    with pytest.raises(ValueError):
        guard_eval.policy_for('backend-sync')

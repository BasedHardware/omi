"""Owner-lab replay bench: runner mechanics, report statistics, invariants. Synthetic only."""

import io
import json
import socket
import urllib.error

import pytest

import utils.llm.notes_output_contract  # noqa: F401 - warm the import outside the per-test CPU guard
from testing.owner_lab import invariants, replay_bench, report
from testing.owner_lab.invariants import LabelledCase
from utils.llm.notes_identity import NotesIdentity

# ---- runner: interleave, resume, retry ----


def test_interleave_covers_every_arm_case_repeat_and_rotates():
    plan = replay_bench.interleave(['c1', 'c2', 'c3'], ['baseline', 'on', 'off'], 2)
    assert len(plan) == 18
    assert set(plan) == {
        (arm, case, repeat) for arm in ('baseline', 'on', 'off') for case in ('c1', 'c2', 'c3') for repeat in (0, 1)
    }
    # Within one case block the arm order rotates per case index and repeat.
    assert [key[0] for key in plan[:3]] == ['baseline', 'on', 'off']
    assert [key[0] for key in plan[3:6]] == ['on', 'off', 'baseline']
    assert [key[0] for key in plan[6:9]] == ['off', 'baseline', 'on']
    assert [key[0] for key in plan[9:12]] == ['on', 'off', 'baseline']  # repeat 1 shifts again


def test_completed_keys_drive_resume(tmp_path):
    results = tmp_path / 'runs.jsonl'
    done = {'arm': 'on', 'id': 'c1', 'repeat': 0}
    results.write_text(json.dumps(done) + '\n')
    plan = replay_bench.interleave(['c1', 'c2'], ['baseline', 'on'], 1)
    pending = replay_bench.pending_keys(plan, results)
    assert ('on', 'c1', 0) not in pending
    assert pending == [key for key in plan if key != ('on', 'c1', 0)]


def test_pending_keys_empty_results_runs_everything(tmp_path):
    plan = replay_bench.interleave(['c1'], ['baseline', 'on'], 2)
    assert replay_bench.pending_keys(plan, tmp_path / 'absent.jsonl') == plan


def test_drive_exit_maps_states_to_documented_codes():
    assert replay_bench.drive_exit('complete') == replay_bench.EXIT_OK
    assert replay_bench.drive_exit('stopped') == replay_bench.EXIT_SPEND
    assert replay_bench.drive_exit('failed') == replay_bench.EXIT_ERROR


def test_append_row_creates_owner_only_results_file(tmp_path):
    results = tmp_path / 'runs.jsonl'
    replay_bench.append_row(results, {'arm': 'on', 'id': 'c1', 'repeat': 0})
    assert results.stat().st_mode & 0o077 == 0  # rows carry conversation ids


def test_append_row_tightens_a_permissive_existing_file(tmp_path):
    results = tmp_path / 'runs.jsonl'
    results.write_text('')
    results.chmod(0o644)  # e.g. created before the owner-only rule
    replay_bench.append_row(results, {'arm': 'on', 'id': 'c1', 'repeat': 0})
    assert results.stat().st_mode & 0o077 == 0


def test_vendor_harness_carries_no_product_packages():
    vendor = replay_bench.vendor_harness()
    assert {entry.name for entry in vendor.iterdir()} == {'testing'}
    # No utils/models/database in the vendor: product imports can only resolve
    # from the arm's pinned tree, so every arm measures its own code.
    assert not (vendor / 'utils').exists()
    assert (vendor / 'testing' / 'owner_lab' / 'replay_bench.py').exists()


def test_worker_env_preserves_parent_values_and_strips_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv('OWNER_LAB_UID', 'uid-from-parent')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/secrets.json')
    monkeypatch.setenv('NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S', 'digest')
    arm = replay_bench.Arm(name='on', adapter='m:a', tree=str(tmp_path), ref='r', env={'FLAG_X': 'true'})
    env = replay_bench.worker_env(arm)
    assert env['OWNER_LAB_UID'] == 'uid-from-parent'
    assert 'GOOGLE_APPLICATION_CREDENTIALS' not in env
    assert 'NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S' not in env
    assert env['FLAG_X'] == 'true'


def test_drive_retries_transport_and_stops_after_three_consecutive():
    codes = [
        replay_bench.EXIT_TRANSPORT,
        replay_bench.EXIT_OK,  # key 1: one retry clears
        replay_bench.EXIT_TRANSPORT,
        replay_bench.EXIT_TRANSPORT,
        replay_bench.EXIT_TRANSPORT,  # key 2: three consecutive failures stop
    ]
    sleeps: list[float] = []
    state = {'i': 0}

    def spawn(key):
        code = codes[state['i']]
        state['i'] += 1
        return code

    plan = [('on', 'c1', 0), ('on', 'c2', 0)]
    state_out, detail = replay_bench.drive(plan, spawn, retry_wait_seconds=0, sleep=sleeps.append)
    assert state_out == 'failed'
    assert 'consecutive failures 3' in detail
    assert len(sleeps) == 3  # one retry on key 1, two before key 2's third consecutive failure


def test_drive_stops_immediately_on_spend_or_error():
    for code, expected in ((replay_bench.EXIT_SPEND, 'stopped'), (replay_bench.EXIT_ERROR, 'failed')):
        state, _ = replay_bench.drive([('on', 'c1', 0)], lambda key: code, sleep=lambda _: None)
        assert state == expected


# ---- runner: spend ledger and transport ----


def test_ledger_reserves_in_flight_and_stops_at_soft_cap(tmp_path):
    ledger = replay_bench.SpendLedger(path=tmp_path / 'spend.json', soft_stop_usd=1.0, hard_stop_usd=1.2)
    ledger.reserve(0.6)
    view = ledger.load()
    assert view['uncertain_usd'] == pytest.approx(0.6)
    assert view['estimated_usd'] == 0.0
    with pytest.raises(replay_bench.ControlledStop) as stop:
        ledger.reserve(0.5)  # 0.6 committed + 0.5 exceeds the soft stop
    assert stop.value.kind == 'spend'
    ledger.settle(0.6, 0.4)
    view = ledger.load()
    assert view['estimated_usd'] == pytest.approx(0.4)
    assert view['uncertain_usd'] == pytest.approx(0.0)
    with pytest.raises(replay_bench.ControlledStop):
        ledger.settle(0.0, 0.8)  # 1.2 committed hits the hard stop


class _Response:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Opener:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.requests = payload, error, []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if self.error:
            raise self.error
        return _Response(self.payload)


def _transport(tmp_path, opener, **kw):
    token = tmp_path / 'token'
    token.write_text('x' * 64)
    token.chmod(0o600)
    ledger = replay_bench.SpendLedger(path=tmp_path / 'spend.json', soft_stop_usd=2.8, hard_stop_usd=3.0)
    return replay_bench.GatewayTransport(
        url='http://127.0.0.1:19083', token_file=token, ledger=ledger, opener=opener, **kw
    )


def test_transport_token_file_must_be_private(tmp_path):
    token = tmp_path / 'token'
    token.write_text('x' * 64)
    token.chmod(0o644)
    with pytest.raises(replay_bench.ControlledStop) as stop:
        replay_bench.GatewayTransport(
            url='http://127.0.0.1:19083',
            token_file=token,
            ledger=replay_bench.SpendLedger(path=tmp_path / 's.json', soft_stop_usd=1, hard_stop_usd=2),
        )
    assert stop.value.kind == 'credential'


def test_transport_charges_reserves_and_settles(tmp_path):
    opener = _Opener(
        payload={
            'model': 'gateway/gpt-6-luna-1',
            'choices': [{'message': {'content': 'ok'}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'prompt_tokens_details': {'cached_tokens': 50}},
        }
    )
    transport = _transport(tmp_path, opener)
    result = transport.complete({'model': 'x', 'messages': [], 'max_completion_tokens': 100})
    assert result['choices'][0]['message']['content'] == 'ok'
    ledger = transport.ledger.load()
    assert ledger['estimated_usd'] == pytest.approx(((100 - 50) * 0.10 + 50 * 0.01 + 10 * 0.60) / 1e6)
    assert ledger['uncertain_usd'] == pytest.approx(0.0)
    assert ledger['requests'] == 1
    assert opener.requests[0].get_header('X-omi-service-caller') == 'backend'


def test_transport_maps_failures_to_stop_kinds(tmp_path):
    payload = {'model': 'm', 'choices': [{'message': {}}], 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}
    server_error = _Opener(error=urllib.error.HTTPError('u', 503, 'boom', None, io.BytesIO(b'x')))
    with pytest.raises(replay_bench.ControlledStop) as stop:
        _transport(tmp_path, server_error).complete({'messages': []})
    assert stop.value.kind == 'transport'
    bad_model = _Opener(payload={**payload, 'model': 'other-vendor'})
    with pytest.raises(replay_bench.ControlledStop) as stop:
        _transport(tmp_path, bad_model).complete({'messages': []})
    assert stop.value.kind == 'model'


def test_local_only_sockets_denies_other_peers():
    original = socket.socket.connect
    with replay_bench.local_only_sockets([('127.0.0.1', 19083)]):
        with pytest.raises(replay_bench.ControlledStop) as stop:
            socket.socket().connect(('10.9.8.7', 443))
        assert stop.value.kind == 'network'
    # Whatever connect was installed before (the suite may wrap it) is restored.
    assert socket.socket.connect is original


# ---- runner: parity fingerprints ----


def test_fingerprint_ignores_key_order_and_compares_parity():
    body = {'model': 'm', 'messages': [1, 2], 'prompt_cache_key': 'k'}
    same = replay_bench.fingerprint(dict(reversed(list(body.items()))))
    assert same == replay_bench.fingerprint(body)
    other = replay_bench.fingerprint({**body, 'messages': [2, 1]})
    assert other['request_sha256'] != same['request_sha256']
    rows_a = [{'id': 'c1', **same}, {'id': 'c2', **other}]
    rows_b = [{'id': 'c1', **same}, {'id': 'c2', **same}]
    assert replay_bench.compare_parity({'a': rows_a, 'b': list(rows_a)}) == []
    mismatched = replay_bench.compare_parity({'a': rows_a, 'b': rows_b})
    assert [entry['id'] for entry in mismatched] == ['c2']


# ---- report: aggregates, bootstrap, gates ----


def _row(arm, case, repeat, cost, rejections=1.0, lookups=8, turns=4, prompt=1000, cached=500, completion=100):
    return {
        'arm': arm,
        'id': case,
        'repeat': repeat,
        'forced': False,
        'reason': None,
        'lookups': lookups,
        'rejections': rejections,
        'cost': cost,
        'prompt_tokens': prompt,
        'cached_tokens': cached,
        'completion_tokens': completion,
        'turns': turns,
        'packet_bytes': 4000,
    }


def test_per_arm_counts_forced_share_and_means():
    rows = [_row('base', 'c1', 0, 0.004, rejections=2), _row('base', 'c1', 1, 0.006, rejections=1)]
    rows[0]['forced'] = True
    rows[0]['reason'] = 'lookup_cap'
    arms = report.per_arm(rows)
    assert len(arms) == 1
    assert arms[0]['runs'] == 2
    assert arms[0]['forced'] == 1
    assert arms[0]['forced_share'] == pytest.approx(0.5)
    assert arms[0]['forced_reasons'] == {'lookup_cap': 1}
    assert arms[0]['cost_per_run'] == pytest.approx(0.005)
    assert arms[0]['cache_share'] == pytest.approx(0.5)


def test_paired_ratios_reproducible_and_exact_on_a_clean_fixture():
    rows = []
    for case in ('c1', 'c2'):
        for repeat in (0, 1):
            rows.append(_row('base', case, repeat, 1.0))
            rows.append(_row('on', case, repeat, 2.0))
    first = report.paired_ratios(rows, 'base')
    second = report.paired_ratios(rows, 'base')
    assert first == second  # seeded bootstrap is reproducible
    cost = first['on']['cost']
    assert cost['ratio'] == pytest.approx(2.0)
    assert cost['ci_low'] == pytest.approx(2.0)
    assert cost['ci_high'] == pytest.approx(2.0)  # every resample doubles too
    assert cost['pairs'] == 4


def test_noise_floor_uses_baseline_repeat_one_vs_zero():
    rows = []
    for case in ('c1', 'c2'):
        rows.append(_row('base', case, 0, 1.0))
        rows.append(_row('base', case, 1, 1.0))
    ratios = report.paired_ratios(rows, 'base')
    assert ratios['noise_floor']['cost']['ratio'] == pytest.approx(1.0)


def test_cost_split_separates_volume_from_cache_share():
    rows = [
        _row('base', 'c1', 0, 0.0, prompt=1000, cached=500),
        _row('off', 'c1', 0, 0.0, prompt=1000, cached=0),
    ]
    split = {entry['arm']: entry for entry in report.cost_split(rows, 'base')}
    assert split['base']['cached_share'] == pytest.approx(0.5)
    assert split['base']['cost_per_run'] == pytest.approx((500 * 0.10 + 500 * 0.01 + 100 * 0.60) / 1e6)
    # At the baseline cache share the off arm's cost gap collapses to the output tokens.
    assert split['off']['cost_at_baseline_cache_share'] == pytest.approx(split['base']['cost_per_run'])
    assert split['off']['cost_per_run'] > split['off']['cost_at_baseline_cache_share']


def test_cost_split_accepts_custom_prices():
    rows = [_row('base', 'c1', 0, 0.0)]
    default = report.cost_split(rows, 'base')[0]['cost_per_run']
    doubled = report.cost_split(rows, 'base', (0.20, 0.02, 1.20))[0]['cost_per_run']
    assert doubled == pytest.approx(2 * default)


def test_custom_prices_reprice_every_section_including_gates(tmp_path, capsys):
    results = tmp_path / 'runs.jsonl'
    rows = [
        _row('base', 'c1', 0, 999.0, prompt=1000, cached=0, completion=0),
        _row('on', 'c1', 0, 999.0, prompt=1000, cached=0, completion=0),
    ]
    results.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    code = report.main(
        [str(results), '--baseline', 'base', '--prices', '0.20,0.02,1.20', '--max-cost-per-run', '0.0001']
    )
    out = capsys.readouterr().out
    assert code == 1
    # 1000 uncached prompt tokens at $0.20/M reprice to $0.0002, over the $0.0001 ceiling.
    assert '$0.00020' in out
    assert 'FAIL: max-cost-per-run base' in out
    assert '999.0' not in out  # the stale stored cost never leaks into the report


def test_gates_fail_when_cost_or_ratio_is_significantly_worse():
    rows = []
    for case in ('c1', 'c2'):
        for repeat in (0, 1):
            rows.append(_row('base', case, repeat, 0.002))
            rows.append(_row('on', case, repeat, 0.007))
    ratios = report.paired_ratios(rows, 'base')
    arms = report.per_arm(rows)
    gates = report.evaluate_gates(arms, ratios, max_cost_per_run=0.006, no_worse=('cost', 'rejections'))
    verdicts = {gate['gate']: gate['verdict'] for gate in gates}
    assert verdicts['no-worse cost on vs baseline'] == 'FAIL'  # CI [3.5, 3.5] sits entirely above 1
    assert verdicts['no-worse rejections on vs baseline'] == 'PASS'
    assert verdicts['max-cost-per-run base'] == 'PASS'
    assert verdicts['max-cost-per-run on'] == 'FAIL'


def test_report_main_exits_nonzero_on_gate_failure(tmp_path, capsys):
    results = tmp_path / 'runs.jsonl'
    rows = []
    for case in ('c1', 'c2'):
        for repeat in (0, 1):
            rows.append(_row('base', case, repeat, 0.002))
            rows.append(_row('on', case, repeat, 0.007))
    results.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    code = report.main([str(results), '--baseline', 'base', '--no-worse', 'cost'])
    assert code == 1
    assert 'FAIL: no-worse cost on vs baseline' in capsys.readouterr().out


# ---- invariants ----


def _notes(title='Planning', participants=None, sections=None):
    return {
        'title': title,
        'participants': participants or [],
        'sections': sections or [{'heading': 'Topic', 'body_markdown': '- point\n  - detail'}],
    }


def test_label_free_invariants_nesting_length_and_action_section():
    good = _notes()
    assert invariants.label_free_invariants(good, transcript_words=2000, est_cost_usd=0.004, cost_cap_usd=0.02) == []
    short_ok = _notes(sections=[{'heading': 'Topic', 'body_markdown': '- point'}])
    assert invariants.label_free_invariants(short_ok, transcript_words=900, est_cost_usd=0.001, cost_cap_usd=0.02) == []
    flat = _notes(sections=[{'heading': 'Topic', 'body_markdown': '- point'}])
    assert invariants.label_free_invariants(flat, transcript_words=2000, est_cost_usd=0.001, cost_cap_usd=0.02) == [
        'no nested bullets for a long transcript'
    ]
    action = _notes(sections=[{'heading': 'Action items', 'body_markdown': '- do it'}])
    failures = invariants.label_free_invariants(action, transcript_words=100, est_cost_usd=0.001, cost_cap_usd=0.02)
    assert failures == ['action-item section present']
    expensive = invariants.label_free_invariants(_notes(), transcript_words=100, est_cost_usd=0.03, cost_cap_usd=0.02)
    assert expensive == ['cost $0.0300 over the $0.0200 cap']
    assert invariants.label_free_invariants(None, stop='deadline', cost_cap_usd=0.02) == ['no notes (stop=deadline)']


def _identity():
    return NotesIdentity(
        speaker_names=(('spk_0', 'Alice Smith'),),
        meeting_names=('Bench Person',),
        owner_names=('Alice Smith',),
    )


def test_identity_invariants_fail_on_unsupported_names():
    identity = _identity()
    good = _notes(participants=[{'name': 'Alice Smith', 'speaker': 'spk_0'}])
    assert invariants.identity_invariants(good, identity) == []
    unsupported_participant = _notes(participants=[{'name': 'Bench Person', 'speaker': 'spk_1'}])
    assert invariants.identity_invariants(unsupported_participant, identity) == ['participant 0 lacks identity support']
    unsupported_title = _notes(title='Sync with Bench Person')
    assert invariants.identity_invariants(unsupported_title, identity) == [
        'title names a person without identity support'
    ]
    owner_title = _notes(title='Alice Smith weekly')
    assert invariants.identity_invariants(owner_title, identity) == []


def test_score_case_stale_unsupported_and_forbidden():
    identity = _identity()
    notes = _notes(title='Alice Smith weekly', participants=[{'name': 'Alice Smith', 'speaker': 'spk_0'}])
    stale = LabelledCase(id='c1', contract_version=1, expect=['Alice Smith'])
    assert invariants.score_case(stale, notes, identity)['status'] == 'STALE'
    unsupported = LabelledCase(id='c1', contract_version=invariants.CONTRACT_VERSION, expect=['Bench Person'])
    result = invariants.score_case(unsupported, notes, identity)
    assert result['status'] == 'PASS'  # the contract forbids naming an unbound speaker
    assert result['unscored_expected_names'] == 1
    supported = LabelledCase(id='c1', contract_version=invariants.CONTRACT_VERSION, expect=['Alice Smith'])
    assert invariants.score_case(supported, notes, identity)['status'] == 'PASS'
    missing = invariants.score_case(supported, _notes(), identity)  # participant absent
    assert missing['status'] == 'FAIL'
    assert any('not in participants' in reason for reason in missing['reasons'])
    forbidden = LabelledCase(id='c1', contract_version=invariants.CONTRACT_VERSION, forbid=['Bench Person'])
    forbidden_notes = _notes(title='Sync with Bench Person')
    hit = invariants.score_case(forbidden, forbidden_notes, identity)
    assert hit['status'] == 'FAIL'
    assert any('forbidden name' in reason for reason in hit['reasons'])


def test_load_cases_reads_external_jsonl_and_comments(tmp_path):
    path = tmp_path / 'cases.jsonl'
    path.write_text(
        '# external file, never in the repo\n'
        + json.dumps({'id': 'c1', 'contract_version': 2, 'expect': ['A B'], 'forbid': ['C D']})
        + '\n'
        + json.dumps({'id': 'c2', 'expect': []})
        + '\n'
    )
    cases = invariants.load_cases(path)
    assert set(cases) == {'c1', 'c2'}
    assert cases['c1'].forbid == ['C D']
    assert cases['c2'].contract_version == invariants.CONTRACT_VERSION
    assert invariants.load_cases(tmp_path / 'missing.jsonl') == {}

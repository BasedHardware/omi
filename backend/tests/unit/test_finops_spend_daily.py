"""Offline spend-ledger contracts. Only reduced aggregate fixtures; no cloud IO."""

import datetime as dt
import importlib.util
import json
import pathlib
import re
import shutil
from types import SimpleNamespace

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'finops'
FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'finops' / 'spend_2026_11_04'
DAY = '2026-11-04'


def load(name):
    spec = importlib.util.spec_from_file_location('test_spend_' + name, FINOPS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    monkeypatch.delenv('FINOPS_AUTH', raising=False)
    return SimpleNamespace(
        assemble=load('assemble_spend_daily'), loader=load('load_bigquery'), parity=load('verify_spend_parity')
    )


def replay(modules, tmp_path):
    return modules.assemble.assemble(FIXTURE, tmp_path, DAY, DAY, DAY)


def write(path, value):
    path.write_text(json.dumps(value))


def test_projection_flags_cover_entire_taxonomy_and_match_embedded_classes(modules):
    basis = json.loads(modules.assemble.BASIS.read_text())
    generator = load('sync_spend_basis')
    assert basis['version']
    assert set(basis['lines']) == set(generator.TAXONOMY)
    for rule in basis['lines'].values():
        assert type(rule['in_all_in']) is bool
        assert type(rule['in_margin_basis']) is bool
        assert rule['basis_class'] in {'fixed', 'variable', 'excluded'}
        if rule['class_rule']:
            assert rule['basis_class'] == basis['line_classes'][rule['class_rule']]['class']
    source = dict(
        version=basis['version'],
        adjustments=basis['adjustments'],
        exclusions=basis['exclusions'],
        split=dict(line_classes=basis['line_classes'], stripe_and_pinecone={}),
    )
    assert generator.project(source) == basis  # no KB dependency
    assert generator.project(json.loads(json.dumps(source))) == basis


def test_parity_fixture_replays_explicit_components_and_absent_modulate(modules, tmp_path):
    artifact = replay(modules, tmp_path)
    figures = modules.parity.verify(artifact['rows'])
    assert figures['all_in'] == pytest.approx(3549.2077)
    assert figures['stt_modulate_modelled_rows'] == 0
    rows = {r['line']: r for r in artifact['rows'] if r['date'] == DAY}
    assert rows['gcp_vertex_provisioned_throughput']['in_all_in'] is True
    assert rows['gcp_vertex_provisioned_throughput']['in_margin_basis'] is False
    assert rows['gcp_dev']['in_all_in'] is False
    assert rows['gcp_dev']['in_margin_basis'] is False
    assert rows['stt_modulate_cash']['in_all_in'] is True
    assert rows['stt_modulate_cash']['in_margin_basis'] is True
    assert rows['llm_anthropic_api']['usd'] == 0
    assert rows['llm_anthropic_api']['status'] == 'measured'
    assert rows['pinecone']['usd'] == 25
    assert rows['stripe_fees_subscription']['usd'] == pytest.approx(281.84 / 6794.82 * 79768.28 / 30.44)
    assert rows['stripe_fees_subscription']['in_all_in'] is False
    assert rows['stripe_fees_subscription']['in_margin_basis'] is True
    detail = json.loads((tmp_path / 'spend_daily_gcp_sku.json').read_text())
    assert sum(r['usd_net'] for r in detail) == pytest.approx(2009.84)
    assert all(r['basis_version'] == '2026-11-06.1' and r['inputs_settled'] for r in artifact['rows'])


def test_missing_inputs_never_become_zero_and_unsettled_dates_never_publish(modules, tmp_path):
    raw = tmp_path / 'raw'
    raw.mkdir()
    artifact = modules.assemble.assemble(raw, tmp_path / 'out', DAY, '2026-11-05', DAY)
    assert {r['line'] for r in artifact['rows']} == {'pinecone'}
    assert {r['date'] for r in artifact['rows']} == {DAY}
    write(raw / 'anthropic_cost_daily.json', {'data': []})
    artifact = modules.assemble.assemble(raw, tmp_path / 'out', DAY, DAY, DAY)
    assert next(r['usd'] for r in artifact['rows'] if r['line'] == 'llm_anthropic_api') == 0
    write(raw / 'anthropic_cost_daily.json', {'status': 'skipped'})
    artifact = modules.assemble.assemble(raw, tmp_path / 'out', DAY, DAY, DAY)
    assert not any(r['line'] == 'llm_anthropic_api' for r in artifact['rows'])


def test_bucket_mapping_and_modelled_cash_preference_and_tooling_cap(modules, tmp_path):
    raw = tmp_path / 'raw'
    shutil.copytree(FIXTURE, raw)
    modulate = load('pull_modulate_modelled')
    ts = int(dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc).timestamp())
    seconds = modulate.modulate_seconds(
        {
            'daily': {
                'd_live_stt_audio_seconds': {
                    'result': {
                        'status': 'success',
                        'data': {'result': [{'metric': {'provider': 'modulate'}, 'values': [[ts, '36000']]}]},
                    }
                }
            }
        },
        DAY,
        DAY,
    )
    price = {'price_usd_per_hour': '0.06'}
    write(
        raw / 'stt_modulate_modelled_daily.json',
        dict(status='ready', rows=modulate.modelled_rows(seconds, price, {}, modulate.rest_prices())),
    )
    cash = json.loads((raw / 'mercury_vendor_spend_daily.json').read_text())
    cash['rows'].append(dict(date=DAY, vendor='anthropic', category='saas', amount_usd='7000', transaction_count=1))
    write(raw / 'mercury_vendor_spend_daily.json', cash)
    artifact = modules.assemble.assemble(raw, tmp_path / 'out', DAY, DAY, DAY)
    rows = {r['line']: r for r in artifact['rows'] if r['date'] == DAY}
    assert rows['stt_modulate_modelled']['usd'] == pytest.approx(0.6)
    assert rows['stt_modulate_modelled']['in_all_in'] is True
    assert rows['stt_modulate_modelled']['in_margin_basis'] is False
    assert rows['stt_modulate_cash']['in_all_in'] is False
    assert rows['agent_tooling_claude_code']['usd'] == 80
    assert rows['agent_tooling_claude_code']['in_margin_basis'] is False
    assert rows['llm_openai']['usd'] == 295.68  # OpenAI end minus one day
    assert rows['llm_anthropic_api']['date'] == DAY  # Anthropic start
    with pytest.raises(ValueError, match='must be absent'):
        modules.parity.verify(artifact['rows'])


@pytest.mark.parametrize('vendor', ['anthropic', 'replicate', 'xai', 'openrouter'])
def test_split_cash_never_enters_saas_or_all_in_with_retained_history(modules, tmp_path, vendor):
    baseline = replay(modules, tmp_path / 'baseline')
    raw = tmp_path / 'raw'
    shutil.copytree(FIXTURE, raw)
    cash_path = raw / 'mercury_vendor_spend_daily.json'
    cash = json.loads(cash_path.read_text())
    config = modules.assemble.load_map()
    charge = dict(
        date=DAY, vendor=vendor, category=config['vendors'][vendor]['category'], amount_usd='7000', transaction_count=1
    )
    cash['rows'].append(charge)
    write(cash_path, cash)
    out = tmp_path / 'out'

    def totals(artifact):
        rows = [r for r in artifact['rows'] if r['date'] == DAY]
        return (
            next(r['usd'] for r in rows if r['line'] == 'saas_tooling'),
            sum(r['usd'] for r in rows if r['in_all_in']),
        )

    offline = modules.assemble.assemble(raw, out, DAY, DAY, DAY)
    assert totals(offline) == pytest.approx(totals(baseline))
    line = 'saas_anthropic_seats' if vendor == 'anthropic' else vendor
    separate = next(r for r in offline['rows'] if r['date'] == DAY and r['line'] == line)
    assert separate['usd'] == 7000 and separate['in_all_in'] is False

    # Exercise the real loader path too: a prior annual charge must be filtered
    # before the retained-history rates are written and used for reassembly.
    history = [dict(charge, date='2025-11-04')]
    loaded = {}
    modules.assemble.load_mercury.load(
        raw,
        'run',
        't',
        lambda _: None,
        lambda name, rows, dates: loaded.update({name: rows}) or len(rows),
        lambda *a, **kw: json.dumps(history),
        derived=out,
    )
    rates = json.loads((out / 'mercury_run_rates.json').read_text())
    assert next(r['amount_usd'] for r in rates['saas'] if r['date'] == DAY) == '750.500000000'
    modules.loader.load_spend_daily(raw, out, 'run', 't', lambda _: None, lambda *a, **kw: 0)
    assert totals(json.loads((out / 'spend_daily.json').read_text())) == pytest.approx(totals(baseline))
    if vendor in {'anthropic', 'replicate'}:
        assert float(next(r['amount_usd'] for r in loaded['mercury_saas_daily'] if r['date'] == DAY)) > 750.5


@pytest.mark.parametrize('kind,line', [('saas', 'saas_tooling'), ('infra', 'infra_non_gcp')])
def test_incomplete_mercury_rate_with_full_coverage_never_publishes(modules, tmp_path, kind, line):
    replay(modules, tmp_path)
    rates = {
        name: [
            dict(
                date=DAY, amount_usd='800', coverage_days=30, annual_history_complete=True, inputs_complete=name != kind
            )
        ]
        for name in ('saas', 'infra')
    }
    write(tmp_path / 'mercury_run_rates.json', rates)
    written = []
    modules.loader.load_spend_daily(
        FIXTURE,
        tmp_path,
        'run',
        't',
        lambda _: None,
        lambda name, rows, dates, **kw: written.extend(rows) or len(rows),
    )
    assert not any(r.get('line') == line for r in written)
    other = 'infra_non_gcp' if kind == 'saas' else 'saas_tooling'
    assert next(r['usd'] for r in written if r.get('line') == other) == 800


def test_source_scoped_replacement_is_idempotent_and_preserves_live_writer(modules, tmp_path):
    artifact = replay(modules, tmp_path)
    live = dict(date=DAY, source='meter_live', line='llm_openai', status='provisional', usd=9)
    state = [live.copy()]
    calls = []

    def replace(name, rows, dates, extra_delete='', after_insert='', related=None):
        if name != 'spend_daily':
            return len(rows)
        source = re.fullmatch(" AND source = '([a-z_]+)'", extra_delete).group(1)
        assert source != 'meter_live'
        if source == 'billing_export':
            assert related[0] == 'spend_daily_gcp_sku' and related[2] == dates
            assert len(related[1]) == 7
        else:
            assert related is None
        assert all(r['source'] == source for r in rows)
        assert "status = 'provisional' AND date < DATE('2026-11-04')" in after_insert
        assert "model.source = 'prometheus'" in after_insert
        state[:] = [r for r in state if not (r['date'] in dates and r['source'] == source)] + rows
        calls.append((source, dates))
        return len(rows)

    for _ in range(2):
        result = modules.loader.load_spend_daily(
            FIXTURE, tmp_path, 'run1', '2026-11-06T12:00:00Z', lambda _: None, replace
        )
        assert result['spend_daily'] == len(artifact['rows'])
        assert len(state) == len(artifact['rows']) + 1
        assert live in state
    assert ('mercury', artifact['scopes']['mercury']) in calls
    assert len(artifact['scopes']['mercury']) == 30
    # Successful missing model series still deletes an older stale model row.
    assert ('prometheus', [DAY]) in calls
    artifact['scopes']['meter_live'] = [DAY]
    write(tmp_path / 'spend_daily.json', artifact)
    with pytest.raises(ValueError, match='own spend sources'):
        modules.loader.load_spend_daily(FIXTURE, tmp_path, 'run', 't', lambda _: None, replace)


def test_load_replace_sql_scopes_deletion_and_cleans_provisionals_inside_transaction(modules, monkeypatch):
    queries = []
    monkeypatch.setattr(modules.loader, 'bq', lambda args, stdin=None: queries.append((args, stdin)) or '')
    monkeypatch.setattr(modules.loader.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    for rows in ([dict(date=DAY, line='llm_openai', source='openai_admin_api', status='measured', usd=2)], []):
        modules.loader.load_replace(
            'spend_daily',
            rows,
            [DAY],
            extra_delete=" AND source = 'openai_admin_api'",
            after_insert="DELETE FROM `based-hardware.omi_finops.spend_daily` WHERE status='provisional' AND date < DATE('2026-11-04');",
        )
        sql = queries[-1][1]
        assert sql.startswith('BEGIN TRANSACTION;') and sql.endswith('COMMIT TRANSACTION;')
        assert "WHERE date IN (DATE('2026-11-04')) AND source = 'openai_admin_api'" in sql
        assert sql.index("status='provisional'") < sql.index('COMMIT')
        assert 'meter_live' not in sql


def test_loader_uses_exact_mercury_rates_with_retained_annual_history(modules, tmp_path):
    replay(modules, tmp_path)
    rates = {
        'saas': [
            dict(date=DAY, amount_usd='800', coverage_days=30, annual_history_complete=True, inputs_complete=True)
        ],
        'infra': [dict(date=DAY, amount_usd='4', coverage_days=30, annual_history_complete=True, inputs_complete=True)],
    }
    write(tmp_path / 'mercury_run_rates.json', rates)
    written = []
    modules.loader.load_spend_daily(
        FIXTURE, tmp_path, 'run', 't', lambda _: None, lambda name, rows, dates, **kw: written.extend(rows) or len(rows)
    )
    assert next(r['usd'] for r in written if r.get('line') == 'saas_tooling') == 800
    assert next(r['usd'] for r in written if r.get('line') == 'infra_non_gcp') == 4


def test_backfill_bounds_and_warnings(modules, monkeypatch, capsys):
    entry = load('cloudrun_entry')
    today = dt.date(2026, 11, 8)
    dates = entry.dates_for_run(today, None, '', '2026-10-01')
    assert dates == [(dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat() for i in range(37)]
    with pytest.raises(SystemExit, match='mutually exclusive'):
        entry.dates_for_run(today, None, DAY, '2026-10-01')
    with pytest.raises(SystemExit, match='exceeds'):
        entry.dates_for_run(today, None, '', '2026-09-01')
    with pytest.raises(SystemExit, match='not settled'):
        entry.dates_for_run(today, None, '', '2026-11-07')
    import subprocess

    monkeypatch.setattr(
        subprocess,
        'run',
        lambda *a, **k: SimpleNamespace(
            returncode=0,
            stdout='ok',
            stderr='WARNING: Modulate skipped\nWARNING: Stripe skipped\nWARNING: deepgram skipped\n',
        ),
    )
    assert entry.subprocess_run(DAY) == 0
    assert capsys.readouterr().err.count('WARNING:') == 3


@pytest.mark.parametrize('present', [set(), None, {'2026-09-30'}])
def test_backfill_lease_contention_is_incomplete_until_owner_finishes(modules, monkeypatch, capsys, present):
    entry = load('cloudrun_entry')
    monkeypatch.setattr(
        entry,
        'dt',
        SimpleNamespace(
            datetime=SimpleNamespace(now=lambda tz: dt.datetime(2026, 11, 8, tzinfo=tz)),
            date=dt.date,
            timedelta=dt.timedelta,
            timezone=dt.timezone,
        ),
    )
    # Outside the normal 14-day gap-fill window: a false success strands a hole.
    day = '2026-10-01'
    monkeypatch.setenv('FINOPS_BACKFILL_FROM', day)
    monkeypatch.delenv('FINOPS_DATE', raising=False)
    monkeypatch.setenv('FINOPS_AUTH', 'cloudrun')
    monkeypatch.setenv('FINOPS_RUN_ROOT', '/unused-test-root')
    monkeypatch.setattr(entry.cloudrun, 'assert_runtime_identity', lambda: 'test-writer')
    monkeypatch.setattr(entry, 'acquire_lease', lambda date: False)
    monkeypatch.setattr(entry, 'takeover_if_stale', lambda date: False)
    reads, runs, releases = [], [], []

    def discover(start, end):
        reads.append((start, end))
        return present

    monkeypatch.setattr(entry, 'load_present_days', discover)
    monkeypatch.setattr(entry, 'subprocess_run', lambda date: runs.append(date) or 0)
    monkeypatch.setattr(entry, 'release_lease', releases.append)
    assert entry.main() != 0
    assert reads == [(day, day)]
    assert not runs and not releases  # never execute or release another owner's lease
    assert 'retry required' in capsys.readouterr().err

    monkeypatch.setattr(entry, 'load_present_days', lambda start, end: {day})
    assert entry.run_one(day) == 0
    assert 'already completed' in capsys.readouterr().err
    assert not runs and not releases

    # Alternatively the owner fails/releases: the retry must really run the date.
    monkeypatch.setattr(entry, 'acquire_lease', lambda date: True)
    assert entry.run_one(day) == 0
    assert runs == [day]


def test_openai_429_retries_only_once_and_honours_retry_after(modules, monkeypatch):
    provider = load('pull_providers')
    sleeps, calls = [], []
    monkeypatch.setattr(provider.time, 'sleep', sleeps.append)

    def pull(cmd, env=None):
        calls.append(cmd)
        if len(calls) == 1:
            raise provider.ProviderPullError('rate limited', 429, '3')
        return {'data': [], 'has_more': False}

    monkeypatch.setattr(provider, 'run_json', pull)
    provider.openai_costs(DAY, '2026-11-05')
    assert len(calls) == 2 and sleeps == [3]
    assert provider.retry_delay('unparseable') == 20
    assert provider.retry_delay('NaN') == 20
    assert provider.retry_delay('Fri, 06 Nov 2026 00:00:00 GMT') >= 0
    calls.clear()

    def fail(cmd, env=None):
        calls.append(cmd)
        raise provider.ProviderPullError('rate limited', 429, None)

    monkeypatch.setattr(provider, 'run_json', fail)
    with pytest.raises(provider.ProviderPullError):
        provider.openai_costs(DAY, '2026-11-05')
    assert len(calls) == 2 and sleeps[-1] == 20
    calls.clear()
    monkeypatch.setattr(
        provider, 'run_json', lambda *a, **k: (_ for _ in ()).throw(provider.ProviderPullError('denied', 403))
    )
    with pytest.raises(provider.ProviderPullError):
        provider.openai_costs(DAY, '2026-11-05')


def test_parity_rejects_duplicate_keys_missing_lines_and_zero_modulate(modules, tmp_path):
    rows = [r for r in replay(modules, tmp_path)['rows'] if r['date'] == DAY]
    with pytest.raises(ValueError, match='duplicate'):
        modules.parity.verify(rows + [rows[0]])
    with pytest.raises(ValueError, match='llm_openai'):
        modules.parity.verify([r for r in rows if r['line'] != 'llm_openai'])
    bad = dict(rows[0], line='stt_modulate_modelled', source='prometheus', status='estimate', usd=0)
    with pytest.raises(ValueError, match='must be absent'):
        modules.parity.verify(rows + [bad])


def test_publication_order_keeps_failed_spend_visible_to_gap_fill(modules, monkeypatch, tmp_path):
    loader = modules.loader
    order = []
    monkeypatch.setattr(loader, 'assert_writer_identity', lambda: 'test-writer')
    monkeypatch.setattr(loader, 'ensure_dataset', lambda: None)
    monkeypatch.setattr(loader, 'ensure_table', lambda _: None)
    names = ('unit_cost_daily', 'unit_cost_reconciliation', 'plan_revenue_daily', 'unit_cost_user_day')
    monkeypatch.setattr(loader, 'build_rows', lambda *a: ({name: [] for name in names}, [DAY]))
    monkeypatch.setattr(loader.load_mercury, 'load', lambda *a, **kw: {})
    for name in ('load_stripe_fees', 'load_vendor_balance', 'load_modulate_modelled'):
        monkeypatch.setattr(loader, name, lambda *a, **kw: {})
    monkeypatch.setattr(loader, 'load_spend_daily', lambda *a: order.append('spend') or {})
    monkeypatch.setattr(loader, 'load_replace', lambda name, *a, **kw: order.append(name) or 0)
    import sys

    monkeypatch.setattr(
        sys, 'argv', ['load_bigquery.py', '--raw', str(tmp_path), '--derived', str(tmp_path), '--run-id', 'r']
    )
    loader.main()
    assert order[0] == 'spend' and order[-1] == 'unit_cost_daily'


def test_retry_after_survives_provider_subprocess_boundary(modules, monkeypatch):
    provider = load('pull_providers')
    sleeps = []
    results = [
        SimpleNamespace(returncode=1, stdout='', stderr=json.dumps({'status': 429, 'retry_after': '7'})),
        SimpleNamespace(returncode=0, stdout=json.dumps({'data': [], 'has_more': False}), stderr=''),
    ]
    monkeypatch.setattr(provider.subprocess, 'run', lambda *a, **kw: results.pop(0))
    monkeypatch.setattr(provider.time, 'sleep', sleeps.append)
    provider.openai_costs(DAY, '2026-11-05')
    assert sleeps == [7] and not results


def test_new_spend_table_has_partition_cluster_and_informational_key(modules, monkeypatch):
    loader = modules.loader
    queries = []
    monkeypatch.setattr(loader.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1))
    monkeypatch.setattr(loader, 'bq', lambda args, stdin=None: queries.append(stdin))
    loader.ensure_table('spend_daily')
    sql = queries[0]
    assert 'date DATE NOT NULL' in sql and 'source STRING NOT NULL' in sql
    assert 'PRIMARY KEY (date, line, source, status) NOT ENFORCED' in sql
    assert 'PARTITION BY date CLUSTER BY line, source' in sql


def test_optional_warning_survives_pull_log_layer(modules, monkeypatch, tmp_path, capsys):
    runner = load('run_unit_cost')

    def child(*a, **kw):
        kw['stdout'].write('WARNING: Modulate modelled STT line skipped: prometheus_series_missing\n')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, 'run', child)
    assert runner.sh(['synthetic_optional.py'], tmp_path / 'pull.log', 'modulate', required=False)
    assert 'WARNING: Modulate' in capsys.readouterr().err


def test_billing_and_sku_detail_commit_in_the_same_transaction(modules, monkeypatch):
    loader = modules.loader
    calls = []
    monkeypatch.setattr(loader, 'bq', lambda args, stdin=None: calls.append((args, stdin)) or '')
    monkeypatch.setattr(loader.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    ledger = [dict(date=DAY, line='gcp:compute_engine', source='billing_export', status='billed', usd=5)]
    detail = [dict(date=DAY, project_class='prod', service='Compute Engine', sku='CPU', usd_net=5)]
    loader.load_replace(
        'spend_daily',
        ledger,
        [DAY],
        extra_delete=" AND source = 'billing_export'",
        related=('spend_daily_gcp_sku', detail, [DAY]),
    )
    assert [call[0][0] for call in calls] == ['load', 'load', 'query']
    sql = calls[-1][1]
    assert sql.count('BEGIN TRANSACTION') == sql.count('COMMIT TRANSACTION') == 1
    assert 'INSERT INTO `based-hardware.omi_finops.spend_daily`' in sql
    assert 'INSERT INTO `based-hardware.omi_finops.spend_daily_gcp_sku`' in sql


@pytest.mark.parametrize('unknown', [None, 'artifact', 'row'])
def test_modulate_loader_accepts_breakdown_and_rejects_unknown_keys(modules, tmp_path, unknown):
    modulate = load('pull_modulate_modelled')
    prices = modulate.rest_prices()
    live_price = modulate.price_from_card(json.loads(modulate.RATE_CARD.read_text()))
    from decimal import Decimal

    artifact = dict(
        status='ready',
        method='modelled',
        **live_price,
        **prices,
        rows=modulate.modelled_rows({}, live_price, {DAY: {'stt': Decimal(7200), 'lid': Decimal(3600)}}, prices),
    )
    if unknown == 'artifact':
        artifact['unexpected'] = 1
    elif unknown == 'row':
        artifact['rows'][0]['unexpected'] = 1
    write(tmp_path / modulate.ARTIFACT, artifact)
    ensured, writes = [], []

    def replace(name, rows, dates):
        writes.append((name, rows, dates))
        return len(rows)

    if unknown:
        with pytest.raises(SystemExit, match='invalid Modulate modelled'):
            modules.loader.load_modulate_modelled(tmp_path, 'run', 't', ensured.append, replace)
        assert not ensured and not writes
        return
    assert modules.loader.load_modulate_modelled(tmp_path, 'run', 't', ensured.append, replace) == {
        'stt_modulate_modelled_daily': 1,
    }
    assert ensured == ['stt_modulate_modelled_daily']
    name, rows, dates = writes[0]
    assert dates == [DAY]
    assert rows[0]['live_seconds'] == '0.000000000'
    assert rows[0]['rest_stt_seconds'] == '7200.000000000'
    assert rows[0]['lid_seconds'] == '3600.000000000'
    assert rows[0]['rest_price_usd_per_hour'] == '0.030000000'
    assert rows[0]['lid_price_usd_per_hour'] == '0.010000000'
    assert rows[0]['usd'] == '0.070000000'
    schema = dict(modules.loader.SCHEMAS[name])
    assert all(schema[key] == 'FLOAT64' for key in ('live_seconds', 'rest_stt_seconds', 'lid_seconds'))
    assert all(schema[key] == 'NUMERIC' for key in ('rest_price_usd_per_hour', 'lid_price_usd_per_hour'))

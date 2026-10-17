"""Synthetic API-shape fixtures only. No bank requests, credentials or account data."""

import importlib.util
import json
import pathlib
from decimal import Decimal
import urllib.error

import pytest

FINOPS = pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'finops'
FIXTURES = pathlib.Path(__file__).parent / 'fixtures' / 'finops'


def load(name):
    spec = importlib.util.spec_from_file_location('test_' + name, FINOPS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mercury(monkeypatch):
    monkeypatch.syspath_prepend(str(FINOPS))
    for name in ('FINOPS_AUTH', 'FINOPS_MERCURY_ENABLED', 'FINOPS_MERCURY_READONLY_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    return load('pull_mercury')


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_pages_posted_utc_debits_deduplication_and_privacy(mercury, monkeypatch, tmp_path):
    calls = []
    pages = [fixture('mercury_transactions_page1.json'), fixture('mercury_transactions_page2.json')]

    def get(params, token):
        assert token == 'TEST_TOKEN_DO_NOT_PERSIST'
        calls.append(dict(params))
        return pages.pop(0)

    monkeypatch.setattr(mercury, 'get_page', get)
    config = mercury.load_map()
    rows = mercury.fetch_aggregates('2026-10-01', '2026-10-02', 'TEST_TOKEN_DO_NOT_PERSIST', config)
    by_key = {(r['date'], r['vendor']): r for r in rows}
    assert by_key['2026-10-02', 'vercel']['amount_usd'] == '100.25'
    assert by_key['2026-10-02', 'soniox']['amount_usd'] == '143'
    assert by_key['2026-10-02', 'openai']['amount_usd'] == '200'  # USD, not JPY merchant minor units
    assert by_key['2026-10-02', 'gcp']['amount_usd'] == '400'
    assert by_key['2026-10-02', 'unmapped']['amount_usd'] == '100'
    assert by_key['2026-10-02', 'unmapped']['transaction_count'] == 2
    assert by_key['2026-10-02', 'excluded']['amount_usd'] == '1000'
    assert by_key['2026-10-01', 'unmapped']['transaction_count'] == 0
    assert calls[0]['postedStart'] == '2026-10-01T00:00:00Z'
    assert calls[0]['postedEnd'] == '2026-10-03T00:00:00Z'
    assert calls[1]['start_after'] == 'txn-10'  # exclusive last actual id, not ambiguous nextPage
    text = json.dumps(rows)
    for private in ('PRIVATE', 'DO_NOT_PERSIST', 'txn-', 'SYNTHETIC', 'note', 'cardId', 'details'):
        assert private not in text
    assert sum(Decimal(r['amount_usd']) for r in rows) == Decimal('1943.25')


def test_missing_secret_and_default_off_skip_without_network(mercury, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mercury, 'get_page', lambda *a: pytest.fail('network forbidden'))
    path = tmp_path / mercury.FILENAME
    for enabled, reason in (('false', 'disabled'), ('true', 'secret_unavailable')):
        monkeypatch.setenv('FINOPS_MERCURY_ENABLED', enabled)
        monkeypatch.setenv('FINOPS_AUTH', 'cloudrun')
        monkeypatch.setenv('FINOPS_SECRETS_DIR', str(tmp_path / 'absent'))
        path.write_text('{"status":"ready","rows":["old"]}')
        mercury.pull(tmp_path, '2026-10-17')
        assert json.loads(path.read_text()) == {'status': 'skipped', 'reason': reason}
    assert 'WARNING: Mercury' in capsys.readouterr().err


def test_mount_and_90_day_window(mercury, monkeypatch, tmp_path):
    monkeypatch.setenv('FINOPS_AUTH', 'cloudrun')
    monkeypatch.setenv('FINOPS_MERCURY_ENABLED', 'true')
    monkeypatch.setenv('FINOPS_SECRETS_DIR', str(tmp_path / 'secrets'))
    secret = tmp_path / 'secrets' / 'finops-mercury-readonly' / 'finops-mercury-readonly'
    secret.parent.mkdir(parents=True)
    secret.write_text('test-only')
    assert mercury.optional_token() == 'test-only'
    calls = []

    def get(params, token):
        calls.append(dict(params))
        return {'transactions': [], 'page': {'nextPage': None}}

    monkeypatch.setattr(mercury, 'get_page', get)
    mercury.pull(tmp_path, '2026-10-17')
    snapshot = json.loads((tmp_path / mercury.FILENAME).read_text())
    assert snapshot['start'] == '2026-07-20' and snapshot['end'] == '2026-10-17'
    assert len(snapshot['rows']) == 90  # successful zero days retain explicit coverage
    assert all(r['amount_usd'] == '0' for r in snapshot['rows'])
    assert calls[0]['status'] == 'sent'


def test_permission_skip_and_transport_failure_never_reuse_old_rows(mercury, monkeypatch, tmp_path):
    monkeypatch.setenv('FINOPS_MERCURY_ENABLED', 'true')
    monkeypatch.setenv('FINOPS_MERCURY_READONLY_TOKEN', 'private-token')
    monkeypatch.setattr(mercury, 'get_page', lambda *a: (_ for _ in ()).throw(PermissionError('PRIVATE')))
    mercury.pull(tmp_path, '2026-10-17')
    assert json.loads((tmp_path / mercury.FILENAME).read_text())['reason'] == 'permission_unavailable'
    monkeypatch.setattr(
        mercury, 'get_page', lambda *a: (_ for _ in ()).throw(mercury.MercuryError('transport failure'))
    )
    with pytest.raises(mercury.MercuryError):
        mercury.pull(tmp_path, '2026-10-17')
    assert not (tmp_path / mercury.FILENAME).exists()


def test_bad_shape_cannot_echo_private_values(mercury, monkeypatch):
    monkeypatch.setattr(
        mercury,
        'get_page',
        lambda *a: {'transactions': [{'id': 'PRIVATE', 'status': 'sent', 'postedAt': 'PRIVATE_DATE'}], 'page': {}},
    )
    with pytest.raises(mercury.MercuryError) as error:
        mercury.fetch_aggregates('2026-10-01', '2026-10-02', 'test', mercury.load_map())
    assert 'PRIVATE' not in str(error.value)


def test_pagination_loop_fails_closed(mercury, monkeypatch):
    page = fixture('mercury_transactions_page1.json')
    monkeypatch.setattr(mercury, 'get_page', lambda *a: page)
    with pytest.raises(mercury.MercuryError, match='pagination'):
        mercury.fetch_aggregates('2026-10-01', '2026-10-02', 'test', mercury.load_map())


def test_http_denial_and_redirect_are_sanitized(mercury, monkeypatch):
    class Opener:
        def open(self, *a, **kw):
            raise urllib.error.HTTPError('PRIVATE_URL', 403, 'PRIVATE_BODY', {}, None)

    monkeypatch.setattr(mercury.urllib.request, 'build_opener', lambda *a: Opener())
    with pytest.raises(PermissionError) as error:
        mercury.get_page({}, 'PRIVATE_TOKEN')
    assert 'PRIVATE' not in str(error.value)
    with pytest.raises(mercury.MercuryError, match='redirect refused'):
        mercury.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://PRIVATE.invalid')


def test_exclusion_map_and_alias_boundaries(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    tx = {'kind': 'outgoingPayment', 'counterpartyName': 'OpenAI LLC'}
    assert costs.classify(tx, config) == ('openai', 'llm_vendor')
    tx['counterpartyName'] = 'OpenAInotreally'
    assert costs.classify(tx, config) == ('unmapped', 'unmapped')
    tx['counterpartyName'] = 'PRIVATE_PERSON'
    tx['mercuryCategory'] = 'Taxes'
    assert costs.classify(tx, config) == ('excluded', 'excluded')
    tx['counterpartyName'] = 'JLCPCB'
    tx.pop('mercuryCategory')
    assert costs.classify(tx, config) == ('excluded', 'excluded')
    tx['counterpartyName'] = 'Google Workspace'
    assert costs.classify(tx, config) == ('google_workspace', 'saas')
    tx['counterpartyName'] = 'Stripe Unknown Merchant'
    assert costs.classify(tx, config) == ('unmapped', 'unmapped')
    tx['counterpartyName'] = 'Stripe Inc'
    assert costs.classify(tx, config) == ('unmapped', 'unmapped')
    tx['counterpartyName'] = 'Stripe Fees'
    assert costs.classify(tx, config) == ('stripe_fees', 'infra_non_gcp')
    tx['counterpartyName'] = 'Google Cloud'
    assert costs.classify(tx, config) == ('gcp', 'gcp')


def cash(day, vendor, amount, category='saas', count=1):
    return {'date': day, 'vendor': vendor, 'category': category, 'amount_usd': str(amount), 'transaction_count': count}


def coverage(costs, start, end):
    return [cash(d, 'unmapped', 0, 'unmapped', 0) for d in costs.days(start, end)]


def test_saas_30_day_boundaries_annual_amortization_and_no_double_count(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    config['vendors']['github']['annual'] = True
    rows = coverage(costs, '2025-10-18', '2026-10-17') + [
        cash('2026-09-18', 'vercel', 304.375),
        cash('2026-09-17', 'vercel', 999),
        cash('2026-01-01', 'github', 3652.50),
        cash('2026-10-17', 'soniox', 1000, 'stt_vendor'),
        cash('2026-10-17', 'gcp', 2000, 'gcp'),
        cash('2026-10-18', 'vercel', 999),
    ]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert Decimal(result['amount_usd']) == Decimal('20')  # 304.375/30.4375 + 3652.50/12/30.4375
    assert result['annual_monthly_usd'] == '304.375000000'
    assert result['inputs_complete'] is True
    expired = costs.saas_rows(rows, ['2027-01-01'], config)[0]
    assert Decimal(expired['annual_monthly_usd']) == 0


def test_partial_history_and_unmapped_never_look_complete(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-07-20', '2026-10-17')
    assert costs.saas_rows(rows, ['2026-07-20'], config)[0]['inputs_complete'] is False
    assert costs.saas_rows(rows, ['2026-10-17'], config)[0]['inputs_complete'] is True
    config['vendors']['github']['annual'] = True
    assert costs.saas_rows(rows, ['2026-10-17'], config)[0]['annual_history_complete'] is False
    full_year = coverage(costs, '2025-10-18', '2026-10-17')
    full_year = [r for r in full_year if r['date'] != '2026-01-01'] + [
        cash('2026-01-01', 'unmapped', 1200, 'unmapped', 1)
    ]
    # An old unknown payment could be an annual bill even if the recent month is mapped.
    assert costs.saas_rows(full_year, ['2026-10-17'], config)[0]['annual_history_complete'] is False
    config['vendors']['github']['annual'] = False
    rows = [r for r in rows if r['date'] != '2026-10-17'] + [cash('2026-10-17', 'unmapped', 2, 'unmapped', 1)]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert result['unmapped_count'] == 1 and result['inputs_complete'] is False


def test_annual_leap_day_expiry(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    config['vendors']['github']['annual'] = True
    rows = [cash('2024-02-29', 'github', 1200)]
    assert Decimal(costs.saas_rows(rows, ['2025-02-27'], config)[0]['annual_monthly_usd']) == 100
    assert Decimal(costs.saas_rows(rows, ['2025-02-28'], config)[0]['annual_monthly_usd']) == 0


def test_loader_keeps_old_annuals_and_replaces_the_whole_refresh_window(mercury, tmp_path, monkeypatch):
    loader = load('load_mercury')
    costs = load('mercury_costs')
    config = costs.load_map()
    config['vendors']['github']['annual'] = True
    monkeypatch.setattr(loader, 'load_map', lambda: config)
    rows = coverage(costs, '2026-07-20', '2026-10-17') + [cash('2026-10-01', 'vercel', 30)]
    path = tmp_path / mercury.FILENAME
    path.write_text(json.dumps({'status': 'ready', 'start': '2026-07-20', 'end': '2026-10-17', 'rows': rows}))
    calls, ensured = [], []

    def bq(args, stdin):
        assert '--maximum_bytes_billed=104857600' in args
        assert "date < DATE('2026-07-20')" in stdin
        return json.dumps(coverage(costs, '2025-10-18', '2026-07-19') + [cash('2026-01-01', 'github', '3652.50')])

    def replace(name, rows, days):
        calls.append((name, rows, days))
        return len(rows)

    result = loader.load(tmp_path, 'run-2', '2026-10-18T00:00:00Z', ensured.append, replace, bq)
    assert set(result) == {'mercury_vendor_spend_daily', 'mercury_saas_daily'}
    assert all(len(c[2]) == 90 for c in calls)
    assert calls[0][1][0]['run_id'] == 'run-2'
    assert calls[1][1][-1]['inputs_complete'] is True
    assert Decimal(calls[1][1][-1]['amount_usd']) == Decimal('10.985626283')
    path.write_text('{"status":"skipped","reason":"secret_unavailable"}')
    assert loader.load(tmp_path, 'run-3', '', lambda *a: pytest.fail('no write'), replace, bq) == {}
    # Reject any raw field even if inserted into an otherwise valid aggregate artifact.
    rows[0]['note'] = 'PRIVATE'
    path.write_text(json.dumps({'status': 'ready', 'start': '2026-07-20', 'end': '2026-10-17', 'rows': rows}))
    with pytest.raises(loader.MercuryError, match='aggregates only'):
        loader.ready_snapshot(tmp_path, config)


def test_real_cli_missing_mount_exits_successfully(mercury, tmp_path):
    import os
    import subprocess
    import sys

    env = dict(
        os.environ, FINOPS_AUTH='cloudrun', FINOPS_MERCURY_ENABLED='true', FINOPS_SECRETS_DIR=str(tmp_path / 'absent')
    )
    result = subprocess.run(
        [sys.executable, str(FINOPS / 'pull_mercury.py'), '--raw', str(tmp_path), '--end', '2026-10-17'],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert 'WARNING: Mercury' in result.stderr
    assert json.loads((tmp_path / mercury.FILENAME).read_text())['reason'] == 'secret_unavailable'


def test_successful_cloudrun_job_surfaces_mercury_skip(mercury, monkeypatch, capsys):
    import subprocess
    from types import SimpleNamespace

    entry = load('cloudrun_entry')
    monkeypatch.setattr(
        subprocess,
        'run',
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout='done',
            stderr='WARNING: Mercury vendor spend unavailable; see pull.log\nPRIVATE_OTHER_LOG\n',
        ),
    )
    assert entry.subprocess_run('2026-10-15') == 0
    output = capsys.readouterr()
    assert 'WARNING: Mercury' in output.err and 'PRIVATE' not in output.err


def test_non_utf8_secret_is_unavailable(mercury, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('FINOPS_AUTH', 'cloudrun')
    monkeypatch.setenv('FINOPS_MERCURY_ENABLED', 'true')
    monkeypatch.setenv('FINOPS_SECRETS_DIR', str(tmp_path / 'secrets'))
    secret = tmp_path / 'secrets' / 'finops-mercury-readonly'
    secret.parent.mkdir()
    secret.write_bytes(bytes([255, 254]))
    monkeypatch.setattr(mercury, 'get_page', lambda *a: pytest.fail('network forbidden'))
    mercury.pull(tmp_path, '2026-10-17')
    assert json.loads((tmp_path / mercury.FILENAME).read_text())['reason'] == 'secret_unavailable'
    assert 'WARNING: Mercury' in capsys.readouterr().err

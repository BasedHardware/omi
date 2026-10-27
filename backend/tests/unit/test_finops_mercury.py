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
    for name in (
        'FINOPS_AUTH',
        'FINOPS_MERCURY_ENABLED',
        'FINOPS_MERCURY_READONLY_TOKEN',
        'FINOPS_MERCURY_BACKFILL_DAYS',
    ):
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


def test_backfill_env_window_validation_and_idempotence(mercury, monkeypatch, tmp_path):
    """FINOPS_MERCURY_BACKFILL_DAYS widens one run to N posted days (the
    one-time annual-history backfill); the same window re-derived twice yields
    byte-identical (date, vendor) aggregates — the backfill never appends."""
    monkeypatch.setenv('FINOPS_AUTH', 'cloudrun')
    monkeypatch.setenv('FINOPS_MERCURY_ENABLED', 'true')
    monkeypatch.setenv('FINOPS_SECRETS_DIR', str(tmp_path / 'secrets'))
    secret = tmp_path / 'secrets' / 'finops-mercury-readonly' / 'finops-mercury-readonly'
    secret.parent.mkdir(parents=True)
    secret.write_text('test-only')
    calls = []

    def get(params, token):
        calls.append(dict(params))
        return {'transactions': [], 'page': {'nextPage': None}}

    monkeypatch.setattr(mercury, 'get_page', get)
    monkeypatch.setenv('FINOPS_MERCURY_BACKFILL_DAYS', '400')
    mercury.pull(tmp_path, '2026-10-17')
    first = (tmp_path / mercury.FILENAME).read_text()
    snapshot = json.loads(first)
    assert snapshot['start'] == '2025-09-13'  # 400 posted days ending 2026-10-17
    assert len(snapshot['rows']) == 400
    assert calls[0]['postedStart'] == '2025-09-13T00:00:00Z'
    mercury.pull(tmp_path, '2026-10-17')
    assert (tmp_path / mercury.FILENAME).read_text() == first  # idempotent on (date, vendor)
    for bad in ('abc', '90', '401', '0', '-1'):
        monkeypatch.setenv('FINOPS_MERCURY_BACKFILL_DAYS', bad)
        with pytest.raises(mercury.MercuryError, match='BACKFILL_DAYS'):
            mercury.pull(tmp_path, '2026-10-17')


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
    tx = {'kind': 'debitCardTransaction', 'counterpartyName': 'OpenAI LLC'}
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


def test_large_one_off_vendor_aliases_and_software_costs_rule(mercury):
    """Aliases from the 2026-10-23 read-only 13-month check: the $12,000 Modal
    Group compute wire lands in infra_non_gcp (compute, never SaaS), the
    annual-scale WWW.DEEPGRAM.COM wire stays STT cash, and the once-a-year
    Software posters (vanta, mintlify) get named SaaS entries so cadence
    detection reads their own series. `Software Costs` joins `Software &
    Subscriptions` as a saas category-data rule."""
    costs = load('mercury_costs')
    config = costs.load_map()
    wire = {
        'kind': 'outgoingPayment',
        'counterpartyName': 'Modal Group, Inc.',
        'mercuryCategory': None,
        'categoryData': None,
    }
    assert costs.classify(wire, config) == ('modal', 'infra_non_gcp')
    wire['counterpartyName'] = 'WWW.DEEPGRAM.COM'
    wire['categoryData'] = {'name': 'Software Costs'}
    assert costs.classify(wire, config) == ('deepgram', 'stt_vendor')
    card = {
        'kind': 'debitCardTransaction',
        'counterpartyName': 'Vanta',
        'mercuryCategory': 'Software',
        'categoryData': None,
    }
    assert costs.classify(card, config) == ('vanta', 'saas')
    card['counterpartyName'] = 'Mintlify'
    assert costs.classify(card, config) == ('mintlify', 'saas')
    card['counterpartyName'] = 'Unlisted Software Vendor'
    assert costs.classify(card, config) == ('mercury_category', 'saas')
    unlabelled = {
        'kind': 'other',
        'counterpartyName': 'Unlisted Vendor',
        'mercuryCategory': None,
        'categoryData': {'name': 'Software Costs'},
    }
    assert costs.classify(unlabelled, config) == ('category_data', 'saas')


def test_category_rules_precedence_and_safe_aliases(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()

    tx = {
        'kind': 'outgoingPayment',
        'counterpartyName': 'Shopify Payments',
        'mercuryCategory': 'Shipping',
        'categoryData': {'name': 'Software & Subscriptions'},
    }
    assert costs.classify(tx, config) == ('shopify', 'saas')  # aliases take precedence over both rules

    tx['counterpartyName'] = 'Google Ads'
    tx['mercuryCategory'] = 'Advertising'
    assert costs.classify(tx, config) == ('mercury_category', 'marketing')  # Google ads stay marketing

    tx['mercuryCategory'] = None
    assert costs.classify(tx, config) == ('category_data', 'saas')

    tx['counterpartyName'] = 'Google Payment Corp'
    assert costs.classify(tx, config) == ('gcp', 'gcp')  # avoid counting the GCP invoice as SaaS

    tx['counterpartyName'] = 'Facebook Ads Card'
    tx['mercuryCategory'] = 'Software'
    assert costs.classify(tx, config) == ('facebook', 'marketing')
    tx['counterpartyName'] = 'X Ads'
    assert costs.classify(tx, config) == ('x_ads', 'marketing')
    tx['counterpartyName'] = 'Twitter'
    tx['mercuryCategory'] = None
    tx['categoryData'] = None
    tx['kind'] = 'debitCardTransaction'
    assert costs.classify(tx, config) == ('unmapped', 'unmapped')  # x ads does not claim another alias
    tx['kind'] = 'outgoingPayment'

    tx['counterpartyName'] = 'Unlisted Manufacturer'
    tx['mercuryCategory'] = None
    tx['categoryData'] = {'name': 'Manufacturing'}
    assert costs.classify(tx, config) == ('category_data', 'hardware_cogs')
    tx['mercuryCategory'] = 'Airlines'
    tx['categoryData'] = {'name': 'Software & Subscriptions'}
    assert costs.classify(tx, config) == ('mercury_category', 'travel_meals')
    tx['mercuryCategory'] = None
    tx['categoryData'] = {'name': 'Transfer'}
    assert costs.classify(tx, config) == ('excluded', 'excluded')


def test_unlabelled_transfers_are_other_opex_but_unlabelled_cards_stay_uncategorized(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    wire = {
        'kind': 'outgoingPayment',
        'counterpartyName': 'Unlisted Supplier',
        'mercuryCategory': None,
        'categoryData': None,
    }
    assert costs.classify(wire, config) == ('uncategorized_payment', 'other_opex')
    card = dict(wire, kind='debitCardTransaction')
    assert costs.classify(card, config) == ('unmapped', 'unmapped')
    named = dict(wire, counterpartyName='Upstash')  # a SaaS paid by ACH is caught by its alias first
    assert costs.classify(named, config) == ('upstash', 'saas')
    labelled = dict(wire, categoryData={'name': 'Software & Subscriptions'})
    assert costs.classify(labelled, config) == ('category_data', 'saas')


def test_v1_map_compatibility_and_unknown_category_rejected(mercury, tmp_path):
    costs = load('mercury_costs')
    config = costs.load_map()
    config['schema_version'] = 1
    config.pop('mercury_category_rules')
    config.pop('category_data_rules')
    config.pop('max_uncategorized_usd')
    config.pop('uncategorized_kind_rules')
    path = tmp_path / 'legacy-map.json'
    path.write_text(json.dumps(config))
    legacy = costs.load_map(path)
    assert legacy['mercury_category_rules'] == {}
    assert legacy['category_data_rules'] == {}
    assert legacy['uncategorized_kind_rules'] == {}
    assert costs.classify(
        {
            'kind': 'outgoingPayment',
            'counterpartyName': 'Unlisted',
            'categoryData': {'name': 'Software & Subscriptions'},
        },
        legacy,
    ) == ('unmapped', 'unmapped')

    config['schema_version'] = 2
    config['mercury_category_rules'] = {'unlisted': 'not_a_category'}
    config['category_data_rules'] = {}
    path.write_text(json.dumps(config))
    with pytest.raises(costs.MercuryError, match='category rule'):
        costs.load_map(path)


def cash(day, vendor, amount, category='saas', count=1):
    return {'date': day, 'vendor': vendor, 'category': category, 'amount_usd': str(amount), 'transaction_count': count}


def coverage(costs, start, end):
    return [cash(d, 'unmapped', 0, 'unmapped', 0) for d in costs.days(start, end)]


def test_saas_30_day_boundaries_annual_amortization_and_no_double_count(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    config['vendors']['github']['annual'] = True  # manual override forces the annual treatment
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
    assert Decimal(result['annual_estimated_usd']) == 0  # an override is not an estimate
    assert result['inputs_complete'] is True
    assert result['annual_history_complete'] is True  # a full covered year, override aside
    expired = costs.saas_rows(rows, ['2027-01-01'], config)[0]
    assert Decimal(expired['annual_monthly_usd']) == 0


def test_partial_history_and_uncategorized_threshold(mercury):
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
    # Small unknown spend is tolerated; an annual unknown above the configured threshold blocks history.
    assert costs.saas_rows(full_year, ['2026-10-17'], config)[0]['annual_history_complete'] is True
    full_year = [r for r in full_year if r['date'] != '2026-01-01'] + [
        cash('2026-01-01', 'unmapped', '2500.01', 'unmapped', 1)
    ]
    blocked = costs.saas_rows(full_year, ['2026-10-17'], config)[0]
    assert blocked['annual_history_complete'] is False
    assert blocked['annual_history_reason'] == 'uncategorized_above_threshold'
    config['vendors']['github']['annual'] = False
    rows = [r for r in rows if r['date'] != '2026-10-17'] + [cash('2026-10-17', 'unmapped', 2, 'unmapped', 1)]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert result['unmapped_count'] == 1 and result['inputs_complete'] is True


def test_uncategorized_threshold_boundary_and_large_wire_window(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-09-18', '2026-10-17') + [cash('2026-10-17', 'unmapped', '2500', 'unmapped', 1)]
    at_limit = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert at_limit['unmapped_usd'] == '2500'
    assert at_limit['unmapped_count'] == 1
    assert at_limit['inputs_complete'] is True

    rows[-1] = cash('2026-10-17', 'unmapped', '2500.01', 'unmapped', 1)
    above_limit = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert above_limit['inputs_complete'] is False

    # A large one-off remains blocking while it is in the rolling 30-day window.
    rows = coverage(costs, '2026-09-18', '2026-10-18') + [cash('2026-09-18', 'unmapped', 50000, 'unmapped', 1)]
    assert costs.saas_rows(rows, ['2026-10-17'], config)[0]['inputs_complete'] is False
    assert costs.saas_rows(rows, ['2026-10-18'], config)[0]['inputs_complete'] is True


def test_reconciliation_categories_do_not_enter_the_saas_line(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-09-18', '2026-10-17') + [
        cash('2026-10-17', 'category_data', 304.375, 'saas'),
        cash('2026-10-17', 'category_data', 50000, 'travel_meals'),
        cash('2026-10-17', 'category_data', 50000, 'fulfillment'),
        cash('2026-10-17', 'category_data', 50000, 'hardware_cogs'),
        cash('2026-10-17', 'category_data', 50000, 'professional_services'),
        cash('2026-10-17', 'category_data', 50000, 'other_opex'),
    ]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    # The synthetic vendor's single blended charge is an ambiguous one-off: it
    # amortizes /12 (estimated) instead of spiking the 30-day cash window.
    assert Decimal(result['amount_usd']) == Decimal('0.833333333')  # 304.375/12/30.4375
    assert result['annual_estimated_usd'] == '25.364583333'
    assert result['inputs_complete'] is True


def test_annual_leap_day_expiry(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    config['vendors']['github']['annual'] = True
    rows = [cash('2024-02-29', 'github', 1200)]
    assert Decimal(costs.saas_rows(rows, ['2025-02-27'], config)[0]['annual_monthly_usd']) == 100
    assert Decimal(costs.saas_rows(rows, ['2025-02-28'], config)[0]['annual_monthly_usd']) == 0


def test_committed_cadence_map_is_ledger_evidence_based(mercury):
    """Cadence is detected from ledger history; the map only corrects it.

    No `annual: true` override is committed: forcing a vendor annual requires a
    ~12-month repeat in the ledger or a billing confirmation. Ledger evidence
    (omi_finops.mercury_vendor_spend_daily, 2026-07-04..2026-10-20, re-checked
    read-only 2026-10-23): shopify bills monthly on the 3rd, posthog monthly on
    the ~7th, nevercode monthly on the 1st-2nd, pinecone monthly on the 2nd. The
    2026-10-22 wall audit suspected those four of being single annual payments;
    they are monthly bills, and detection must classify that same-day-of-month
    pattern as monthly cash, never an annual bill. The 2026-10-23 read-only
    13-month check found the real once-a-year postings outside that window
    (Modal Group $12,000 on 2026-01-08 and once-each software bills); those
    drive the completeness gate, not a forced cadence.
    Anthropic is SaaS: its Mercury cash is Claude team seats (David 2026-10-22).
    """
    costs = load('mercury_costs')
    config = costs.load_map()
    assert {vendor for vendor, entry in config['vendors'].items() if entry['annual']} == set()
    rows = coverage(costs, '2026-07-04', '2026-10-17') + [
        cash('2026-08-03', 'shopify', 2969),
        cash('2026-09-03', 'shopify', 3011),
        cash('2026-10-03', 'shopify', 4013),
    ]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert Decimal(result['annual_monthly_usd']) == 0
    assert Decimal(result['amount_usd']) == (Decimal('4013') / costs.DAYS_PER_MONTH).quantize(Decimal('0.000000001'))
    # Modal's once-a-year compute wire is infra_non_gcp cash: it never enters SaaS.
    assert config['vendors']['modal']['category'] == 'infra_non_gcp'
    modal_rows = rows + [cash('2026-01-08', 'modal', 12000, 'infra_non_gcp')]
    assert costs.saas_rows(modal_rows, ['2026-10-17'], config)[0]['amount_usd'] == result['amount_usd']
    assert config['vendors']['anthropic']['category'] == 'saas'
    assert config['vendors']['anthropic']['annual'] is False
    # Modulate cash is STT vendor spend, never SaaS, and never a GCP line.
    assert config['vendors']['modulate']['category'] == 'stt_vendor'


def test_cadence_detection_yearly_repeat_vendor(mercury):
    """A vendor billing about once per 12 months: both neighbour bills amortize
    /12 across their service year instead of vanishing after the cash window."""
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2025-10-18', '2026-10-17') + [
        cash('2025-10-20', 'github', 1200),
        cash('2026-10-15', 'github', 1260),  # 360 days after the previous bill
    ]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert result['annual_monthly_usd'] == '205.000000000'  # 1200/12 + 1260/12
    assert Decimal(result['annual_estimated_usd']) == 0
    assert Decimal(result['amount_usd']) == (Decimal('205') / costs.DAYS_PER_MONTH).quantize(Decimal('0.000000001'))
    assert result['inputs_complete'] is True


def test_cadence_detection_monthly_vendor_stays_cash(mercury):
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-08-18', '2026-10-17') + [
        cash('2026-08-20', 'vercel', 100),
        cash('2026-09-18', 'vercel', 100),
        cash('2026-10-16', 'vercel', 100),
    ]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert Decimal(result['annual_monthly_usd']) == 0
    assert Decimal(result['annual_estimated_usd']) == 0
    # Only the in-window monthly bills count as cash; the August bill ages out.
    assert Decimal(result['amount_usd']) == (Decimal('200') / costs.DAYS_PER_MONTH).quantize(Decimal('0.000000001'))


def test_cadence_detection_one_off_amortizes_and_labels_estimated(mercury):
    """A vendor seen exactly once is ambiguous: amortized /12 for run-rate
    purposes and broken out as estimated, never silently monthly cash."""
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-01-15', '2026-10-17') + [
        cash('2026-02-01', 'sentry', 1200),
    ]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert result['annual_monthly_usd'] == '100.000000000'
    assert result['annual_estimated_usd'] == '100.000000000'
    assert Decimal(result['amount_usd']) == (Decimal('100') / costs.DAYS_PER_MONTH).quantize(Decimal('0.000000001'))
    expired = costs.saas_rows(rows, ['2027-02-02'], config)[0]
    assert Decimal(expired['annual_monthly_usd']) == 0  # the service year ended


def test_cadence_detection_outlier_annual_next_to_monthly_bills(mercury):
    """A charge far larger than the vendor's monthly median is an annual bill
    even without a yearly repeat; the ordinary monthly bills stay cash."""
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-05-18', '2026-10-17') + [
        cash('2026-05-20', 'shopify', 100),
        cash('2026-06-18', 'shopify', 100),
        cash('2026-07-18', 'shopify', 100),
        cash('2026-08-18', 'shopify', 100),
        cash('2026-09-18', 'shopify', 1300),  # 13x the other-charge median
        cash('2026-10-16', 'shopify', 100),
    ]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert result['annual_monthly_usd'] == '108.333333333'  # 1300/12
    assert Decimal(result['annual_estimated_usd']) == 0  # six charges: not ambiguous
    assert Decimal(result['amount_usd']) == ((Decimal('100') + Decimal('1300') / 12) / costs.DAYS_PER_MONTH).quantize(
        Decimal('0.000000001')
    )


def test_cadence_detection_covers_other_software_categories_for_callers(mercury):
    """The detector runs on any software category a caller selects; the SaaS
    run-rate line itself amortizes only `saas` rows so STT/LLM cash never
    double-counts against its own lines."""
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = [
        cash('2026-09-01', 'soniox', 24000, 'stt_vendor'),
        cash('2025-09-05', 'soniox', 24000, 'stt_vendor'),
        cash('2026-09-01', 'deepgram', 500, 'stt_vendor'),
    ]
    annual = costs.detect_annual_charges(rows, config, categories=costs.CADENCE_CATEGORIES)
    assert annual == {
        ('soniox', '2026-09-01'): 'repeat',
        ('soniox', '2025-09-05'): 'repeat',
        ('deepgram', '2026-09-01'): 'one_off',
    }
    assert costs.detect_annual_charges(rows, config) == {}  # default: the saas run-rate view


def test_run_rate_complete_only_with_365_days_of_history(mercury):
    """Luna r3 finding 4: an empty annual override map must not imply complete
    annual history. The run rate may be called complete only when the ledger
    itself covers a full year; otherwise it is partial (history under 12
    months) — the 2026-07-04 ledger start is ~109 days and cannot rule out the
    yearly bills the 13-month read-only check found outside the window."""
    costs = load('mercury_costs')
    config = costs.load_map()
    short = costs.saas_rows(coverage(costs, '2026-07-20', '2026-10-17'), ['2026-10-17'], config)[0]
    assert short['annual_history_complete'] is False
    assert short['annual_history_reason'] == 'history_under_12_months'
    # A hole inside an otherwise year-long history is still not coverage.
    gapped = [r for r in coverage(costs, '2025-10-18', '2026-10-17') if r['date'] != '2026-04-01']
    assert costs.saas_rows(gapped, ['2026-10-17'], config)[0]['annual_history_complete'] is False
    full = costs.saas_rows(coverage(costs, '2025-10-18', '2026-10-17'), ['2026-10-17'], config)[0]
    assert full['annual_history_complete'] is True
    assert full['annual_history_reason'] is None


def test_annual_history_gap_keeps_cash_window_complete_and_flags_seeding(mercury):
    """An unseeded annual history must not drop the measured line to a constant.

    `inputs_complete` describes the 30-posted-day cash window only; the annual
    seeding gap is `annual_history_complete=False` (with its reason) while every
    in-window annual bill still amortizes (bill/12) into the daily value.
    """
    costs = load('mercury_costs')
    config = costs.load_map()
    config['vendors']['github']['annual'] = True
    rows = coverage(costs, '2026-07-20', '2026-10-17') + [cash('2026-10-01', 'github', 1217.50)]
    result = costs.saas_rows(rows, ['2026-10-17'], config)[0]
    assert result['inputs_complete'] is True
    assert result['annual_history_complete'] is False
    assert result['annual_history_reason'] == 'history_under_12_months'
    assert Decimal(result['annual_monthly_usd']) == Decimal('101.458333333')  # 1217.50/12
    assert Decimal(result['annual_estimated_usd']) == 0  # an override is not an estimate
    assert Decimal(result['amount_usd']) == (Decimal('101.458333333') / costs.DAYS_PER_MONTH).quantize(
        Decimal('0.000000001')
    )


def test_infra_run_rate_amortizes_one_offs_and_keeps_monthly_cash(mercury):
    """The Infra (non-GCP) TV line gets the SaaS cadence treatment exactly:
    Modal's once-a-year compute wire amortizes /12 (ambiguous one-off, reported
    as estimated), monthly cloud cash stays run-rate cash, and the amortization
    expires after its 12-month service year."""
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-01-01', '2026-10-17') + [
        cash('2026-01-08', 'modal', 12000, 'infra_non_gcp'),  # the ledger's real once-a-year wire
        cash('2026-09-18', 'aws', 300, 'infra_non_gcp'),
        cash('2026-10-16', 'aws', 300, 'infra_non_gcp'),
        cash('2026-09-20', 'runpod', 60, 'infra_non_gcp'),
        cash('2026-10-16', 'runpod', 60, 'infra_non_gcp'),
    ]
    result = costs.infra_rows(rows, ['2026-10-17'], config)[0]
    assert result['category'] == 'infra_non_gcp'
    assert Decimal(result['amount_usd']) == (
        (Decimal('300') + Decimal('300') + Decimal('60') + Decimal('60') + Decimal('12000') / 12) / costs.DAYS_PER_MONTH
    ).quantize(Decimal('0.000000001'))
    assert result['annual_monthly_usd'] == '1000.000000000'
    assert result['annual_estimated_usd'] == '1000.000000000'  # the one-off ambiguity is labelled estimated
    assert result['inputs_complete'] is True
    # The ledger history here starts 2026-01-01, short of the 365-day gate.
    assert result['annual_history_complete'] is False
    assert result['annual_history_reason'] == 'history_under_12_months'
    expired = costs.infra_rows(rows, ['2027-01-09'], config)[0]
    assert Decimal(expired['annual_monthly_usd']) == 0  # the service year ended


def test_infra_line_never_double_counts_other_wall_lines(mercury):
    """STT compute vendors (Deepgram, Soniox, Modulate), GCP and SaaS cash map
    to their own categories and can never enter the infra run rate; the one
    in-category overlap — Mercury stripe-fee cash, measured on the fee line —
    is kept out of `amount_usd` by name yet rides along in `stripe_fees_usd`,
    so the fees are never counted on both lines and never dropped from both."""
    costs = load('mercury_costs')
    config = costs.load_map()
    for vendor in ('soniox', 'deepgram', 'modulate'):
        assert config['vendors'][vendor]['category'] == 'stt_vendor'
    assert config['vendors']['gcp']['category'] == 'gcp'
    assert config['vendors']['openai']['category'] == 'llm_vendor'
    assert config['vendors']['anthropic']['category'] == 'saas'
    assert config['vendors']['stripe_fees']['category'] == 'infra_non_gcp'
    assert 'stripe_fees' in costs.INFRA_EXCLUDED_VENDORS
    rows = coverage(costs, '2026-09-18', '2026-10-17') + [
        cash('2026-09-18', 'stripe_fees', 500, 'infra_non_gcp'),
        cash('2026-10-17', 'stripe_fees', 500, 'infra_non_gcp'),
        cash('2026-09-18', 'aws', 300, 'infra_non_gcp'),
        cash('2026-10-16', 'aws', 300, 'infra_non_gcp'),
        cash('2026-10-17', 'soniox', 1000, 'stt_vendor'),
        cash('2026-10-17', 'deepgram', 40758.67, 'stt_vendor'),
        cash('2026-10-17', 'openai', 200, 'llm_vendor'),
        cash('2026-10-17', 'gcp', 2000, 'gcp'),
        cash('2026-10-17', 'vercel', 999, 'saas'),
    ]
    result = costs.infra_rows(rows, ['2026-10-17'], config)[0]
    # Only the two aws bills: the fee cash is excluded, every other category
    # never entered the infra series.
    assert Decimal(result['amount_usd']) == (Decimal('600') / costs.DAYS_PER_MONTH).quantize(Decimal('0.000000001'))
    assert Decimal(result['annual_monthly_usd']) == 0
    assert Decimal(result['annual_estimated_usd']) == 0
    # The monthly fee pair keeps its own run rate in the fee column (P2 round 2:
    # the wall counts it there on days the measured Stripe fee line is dark).
    assert Decimal(result['stripe_fees_usd']) == (Decimal('1000') / costs.DAYS_PER_MONTH).quantize(
        Decimal('0.000000001')
    )
    # Counting both columns is exactly the combined run rate (to the two
    # columns' own 1e-9 rounding): no dollar twice, no dollar lost between lines.
    combined = costs.run_rate_rows(
        [row for row in rows if row['category'] == 'infra_non_gcp' or row['vendor'] == 'unmapped'],
        ['2026-10-17'],
        config,
        'infra_non_gcp',
    )[0]
    assert abs(
        Decimal(result['amount_usd']) + Decimal(result['stripe_fees_usd']) - Decimal(combined['amount_usd'])
    ) <= Decimal('0.000000002')


def test_run_rate_tables_are_created_with_every_produced_field(mercury):
    """P1 round 2 (schema): `ensure_table` creates each Mercury run-rate table
    whole from the registered SCHEMAS and `load_replace` projects rows through
    the same list, so every field a producer emits must have a column — an
    insert that names a column a live table lacks fails the whole load (the
    #23289 `mercury_saas_daily` incident; live-table reconciliation for older
    tables is #23354 and stays out of this lane)."""
    loader = load('load_mercury')
    costs = load('mercury_costs')
    config = costs.load_map()
    window = costs.days('2026-09-18', '2026-10-17')
    covered = coverage(costs, '2026-09-18', '2026-10-17')
    for table, produced in (
        ('mercury_saas_daily', costs.saas_rows(covered, window, config)),
        ('mercury_infra_non_gcp_daily', costs.infra_rows(covered, window, config)),
    ):
        assert set(produced[0]) | {'run_id', 'computed_at'} == {name for name, _ in loader.SCHEMAS[table]}
    # The same schemas are what load_bigquery registers for ensure_table.
    registered = load('load_bigquery').SCHEMAS
    assert registered['mercury_saas_daily'] == loader.SCHEMAS['mercury_saas_daily']
    assert registered['mercury_infra_non_gcp_daily'] == loader.SCHEMAS['mercury_infra_non_gcp_daily']


def test_infra_seeding_gap_labels_partial_but_keeps_the_measured_run_rate(mercury):
    """Same contract as SaaS: an unseeded annual history keeps the amortized
    value (measured, best run rate) and names the blocking gate, so the wall
    labels the line partial instead of falling back to a constant."""
    costs = load('mercury_costs')
    config = costs.load_map()
    rows = coverage(costs, '2026-07-20', '2026-10-17') + [
        cash('2026-10-01', 'modal', 12000, 'infra_non_gcp'),
        cash('2026-10-17', 'aws', 304.375, 'infra_non_gcp'),
    ]
    result = costs.infra_rows(rows, ['2026-10-17'], config)[0]
    assert result['inputs_complete'] is True
    assert result['annual_history_complete'] is False
    assert result['annual_history_reason'] == 'history_under_12_months'
    # Both vendors are seen exactly once, so both amortize /12 as estimated.
    assert Decimal(result['annual_monthly_usd']) == Decimal('1025.364583333')
    assert Decimal(result['annual_estimated_usd']) == Decimal('1025.364583333')


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
    assert set(result) == {
        'mercury_vendor_spend_daily',
        'mercury_saas_daily',
        'mercury_infra_non_gcp_daily',
    }
    # Every table is ensured (created whole from SCHEMAS when absent) before
    # its load; the infra table included.
    assert ensured == ['mercury_vendor_spend_daily', 'mercury_saas_daily', 'mercury_infra_non_gcp_daily']
    assert all(len(c[2]) == 90 for c in calls)
    assert calls[0][1][0]['run_id'] == 'run-2'
    saas_tail = calls[1][1][-1]
    assert saas_tail['inputs_complete'] is True
    infra_tail = calls[2][1][-1]
    assert infra_tail['category'] == 'infra_non_gcp'
    assert Decimal(infra_tail['amount_usd']) == 0  # no infra cash in this fixture
    assert Decimal(infra_tail['stripe_fees_usd']) == 0  # and no excluded fee cash either
    # github's year-old bill amortizes by override; vercel is seen exactly once,
    # so its $30 is an ambiguous one-off: /12, labelled estimated (2026-10-23).
    assert Decimal(saas_tail['amount_usd']) == Decimal('10.082135524')
    assert saas_tail['annual_monthly_usd'] == '306.875000000'
    assert saas_tail['annual_estimated_usd'] == '2.500000000'
    assert saas_tail['annual_history_complete'] is True  # full covered year from history + refresh
    assert saas_tail['annual_history_reason'] is None
    path.write_text('{"status":"skipped","reason":"secret_unavailable"}')
    assert loader.load(tmp_path, 'run-3', '', lambda *a: pytest.fail('no write'), replace, bq) == {}
    # Reject any raw field even if inserted into an otherwise valid aggregate artifact.
    rows[0]['note'] = 'PRIVATE'
    path.write_text(json.dumps({'status': 'ready', 'start': '2026-07-20', 'end': '2026-10-17', 'rows': rows}))
    with pytest.raises(loader.MercuryError, match='aggregates only'):
        loader.ready_snapshot(tmp_path, config)


def test_rule_classified_aggregates_survive_the_loader(mercury, tmp_path):
    # Classifier output must round-trip through the BigQuery loader's key validation.
    loader = load('load_mercury')
    costs = load('mercury_costs')
    config = costs.load_map()
    base = {'status': 'sent', 'postedAt': '2026-10-17T12:00:00Z', 'counterpartyName': 'Unlisted'}
    transactions = [
        dict(base, id='a', kind='debitCardTransaction', amount='-12.50', mercuryCategory='Software'),
        dict(base, id='b', kind='outgoingPayment', amount='-900', categoryData={'name': 'Manufacturing'}),
        dict(base, id='c', kind='outgoingPayment', amount='-5000'),
        dict(base, id='d', kind='debitCardTransaction', amount='-7'),
        dict(base, id='e', kind='debitCardTransaction', amount='-20', counterpartyName='Vercel'),
    ]
    totals = {}
    costs.aggregate_page(transactions, config, '2026-10-17', '2026-10-17', totals, set())
    rows = costs.aggregate_rows(totals, '2026-10-17', '2026-10-17')
    assert {(r['vendor'], r['category']) for r in rows} == {
        ('mercury_category', 'saas'),
        ('category_data', 'hardware_cogs'),
        ('uncategorized_payment', 'other_opex'),
        ('unmapped', 'unmapped'),
        ('vercel', 'saas'),
    }
    (tmp_path / mercury.FILENAME).write_text(
        json.dumps({'status': 'ready', 'start': '2026-10-17', 'end': '2026-10-17', 'rows': rows})
    )
    assert loader.ready_snapshot(tmp_path, config)['rows'] == rows
    rows[0]['vendor'] = 'Some Raw Name'
    (tmp_path / mercury.FILENAME).write_text(
        json.dumps({'status': 'ready', 'start': '2026-10-17', 'end': '2026-10-17', 'rows': rows})
    )
    with pytest.raises(loader.MercuryError, match='unknown Mercury aggregate key'):
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

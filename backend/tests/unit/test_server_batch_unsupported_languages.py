"""Declared unsupported admission is bounded and never widens auto/GPU proof."""

from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from config import server_batch
from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES
from tests.unit.test_desktop_batch_only import capture, host
from tests.unit.test_server_batch_auto_language import mobile
from utils import metrics
from utils.batch_pipeline import record_language, vendor_route_contracts
from utils.batch_pipeline.provider_stt_admission import resolve_route
from utils.stt.language_policy import LiveLanguageProfile

STARTER = 'ca,gl,eu,cy,af,sq,bs,sw'


@pytest.fixture(autouse=True)
def admission_env(monkeypatch):
    monkeypatch.setenv('HOSTED_PUSHER_API_URL', 'http://pusher.invalid')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.setenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', '100')
    monkeypatch.setenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', STARTER)
    monkeypatch.delenv('SERVER_BATCH_ONLY_ENABLED', raising=False)
    monkeypatch.delenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', raising=False)


def declared(language):
    row = capture()
    row['language'] = language
    h = host(row)
    h.request.language = h.language = language
    h.language_profile = LiveLanguageProfile.create(language, multi=True, uid='owner')
    return h, row


@pytest.mark.parametrize('language', STARTER.split(','))
def test_allowlisted_declaration_admitted_with_real_profile_and_custody(language):
    h, row = declared(language)
    assert server_batch.request_reason(h) is None
    assert server_batch.eligible(row, 'owner')
    assert server_batch.suppress_live(h)
    assert language in MODULATE_SUPPORTED_LANGUAGES
    route = resolve_route(language)
    assert (route.stt_route, route.provider_service) == ('provider', 'modulate')
    assert not vendor_route_contracts.route_capable('gpu', language)
    assert [
        option.route
        for option in vendor_route_contracts.capable_options(vendor_route_contracts.BUILTIN_TABLE, language)
    ] == ['modulate']


def test_env_normalization_filters_supported_unknown_and_japanese(monkeypatch):
    monkeypatch.setenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', ' CA-es, cy_GB, en, mt, xx, ja-JP, multi, auto, ,ca ')
    assert server_batch.unsupported_languages() == {'ca', 'cy'}
    h, row = declared('ca-ES')
    assert server_batch.request_reason(h) is None
    assert server_batch.eligible(row, 'owner')


@pytest.mark.parametrize('language', ['ja', 'ja-JP', 'zh', 'xx'])
def test_unsupported_or_japanese_stays_live_even_when_japanese_listed(monkeypatch, language):
    monkeypatch.setenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', STARTER + ',ja,ja-JP,xx')
    h, row = declared(language)
    assert server_batch.request_reason(h) == 'language_unsupported'
    assert not server_batch.eligible(row, 'owner')
    assert not server_batch.suppress_live(h)


@pytest.mark.parametrize('raw', [None, '', ' , '])
def test_empty_or_unset_keeps_previous_admission(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES')
    else:
        monkeypatch.setenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', raw)
    h, row = declared('ca')
    assert server_batch.request_reason(h) == 'language_unsupported'
    assert not server_batch.eligible(row, 'owner')
    h, row = declared('en')
    assert server_batch.request_reason(h) is None
    assert server_batch.eligible(row, 'owner')


def test_supported_profile_gate_does_not_expand():
    h, _ = declared('en')
    assert server_batch.request_reason(h) is None
    h.language_profile = SimpleNamespace(primary='en', expected=('en', 'ca'))
    assert server_batch.request_reason(h) == 'profile_mismatch'


@pytest.mark.parametrize('expected', [('ca',), ('ca', 'en'), ('ca', 'cy')])
def test_allowlisted_expected_codes_do_not_cause_false_profile_mismatch(expected):
    h, _ = declared('ca')
    h.language_profile = SimpleNamespace(primary='ca', expected=expected)
    assert server_batch.request_reason(h) is None


@pytest.mark.parametrize('profile', [None, ('cy', ('ca',)), ('ca', ()), ('ca', ('ca', 'ja')), ('ca', ('ca', 'zh'))])
def test_mismatch_missing_or_unadmitted_profile_stays_live(profile):
    h, _ = declared('ca')
    h.language_profile = SimpleNamespace(primary=profile[0], expected=profile[1]) if profile else None
    assert server_batch.request_reason(h) == 'profile_mismatch'


def test_resolved_language_must_still_match_declaration():
    h, _ = declared('ca')
    h.language = 'cy'
    assert server_batch.request_reason(h) == 'profile_mismatch'


@pytest.mark.parametrize('language', ['auto', 'multi', '', None])
def test_auto_multi_are_unchanged(monkeypatch, language):
    h, row = mobile(language)
    h.batch_record_capture = {}
    assert server_batch.request_reason(h) == 'language_auto'
    assert not server_batch.eligible(row, 'owner', batch_admitted=True)
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    assert server_batch.request_reason(h) is None
    h.language_profile = SimpleNamespace(primary='', expected=('ca',), source='learned')
    assert server_batch.request_reason(h) == 'profile_mismatch'


def test_metric_vocabulary_is_fixed_despite_arbitrary_operator_or_request_input(monkeypatch):
    counter = Mock()
    monkeypatch.setattr(metrics, 'OMI_LISTEN_SERVER_BATCH_SUPPRESSION_TOTAL', counter)
    vocabulary = (MODULATE_SUPPORTED_LANGUAGES - server_batch.SUPPORTED - server_batch.AUTO_LANGUAGES) | {'other'}
    assert len(vocabulary) == 37
    assert 'ja' in vocabulary
    for code in [*MODULATE_SUPPORTED_LANGUAGES, 'unknown', 'uid-123', 'zz', 'ca-ES', 'ja_JP', None]:
        h, _ = declared(code)
        server_batch.suppress_live(h)
        assert counter.labels.call_args.kwargs['language'] in vocabulary
    for code, decision in [('ca', 'suppressed'), ('ja', 'live'), ('zh', 'live')]:
        h, _ = declared(code)
        assert server_batch.suppress_live(h) is (decision == 'suppressed')
        assert counter.labels.call_args.kwargs['language'] == code
        assert counter.labels.call_args.kwargs['decision'] == decision
    monkeypatch.setenv('SERVER_BATCH_UNSUPPORTED_LANGUAGES', ','.join(f'unknown{i}' for i in range(100)))
    assert server_batch.bounded_language('unknown42') == 'other'
    assert metrics.OMI_LISTEN_SERVER_BATCH_SUPPRESSION_TOTAL is counter


@pytest.mark.parametrize('language', STARTER.split(','))
async def test_declared_manifest_keeps_evidence_and_needs_no_auto_probes(language):
    manifest = {'context': {'stt_language': language, 'stt_language_evidence': 'declared'}}
    artifacts = Mock()
    assert await record_language.prove_manifest(None, artifacts, None, manifest) is manifest
    artifacts.authorize.assert_not_called()


@pytest.mark.parametrize('language', ['en', 'multi', 'auto', '', None, 'und', 'xx'])
def test_existing_supported_and_unknown_native_routes_do_not_enter_provider_outbox(monkeypatch, language):
    from utils.batch_pipeline import record_provider

    admit = Mock(return_value={'outcome': 'batch'})
    outbox = Mock(side_effect=AssertionError('unexpected provider route'))
    monkeypatch.setattr(record_provider, 'admit', admit)
    binding, items = SimpleNamespace(language=language), [object()]
    assert record_provider.admit_record_units(
        None, items, binding, 1, policy='recorded', provider_outbox_factory=outbox
    ) == {'outcome': 'batch'}
    admit.assert_called_once_with(None, items, binding, 1, policy='recorded')
    outbox.assert_not_called()


@lru_cache(maxsize=None)
def _yaml(relative: str):
    # The C loader keeps the 4k-line runtime manifest inside the fast-unit CPU budget.
    text = (Path(__file__).resolve().parents[2] / relative).read_text(encoding='utf-8')
    return yaml.load(text, Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))


def _listen_values(environment: str, name: str) -> tuple[str, str, str]:
    chart = _yaml(f'charts/backend-listen/{environment}_omi_backend_listen_values.yaml')
    manifest = _yaml('deploy/runtime_env.yaml')
    return (
        next(entry['value'] for entry in chart['env'] if entry['name'] == name),
        _yaml('deploy/runtime_env/_base.yaml')['environment_shared']['gke']['backend-listen']['env'][name]['value'],
        manifest['environments'][environment]['gke']['backend-listen']['env'][name]['value'],
    )


def test_dev_listen_rollout_stays_empty():
    chart, base, manifest = _listen_values('dev', 'SERVER_BATCH_UNSUPPORTED_LANGUAGES')
    assert chart == base == manifest == ''


def test_prod_listen_allowlist_is_enabled_only_for_admitted_codes_never_japanese():
    # Enabled 2026-11-03 after backend-sync-backfill served the native-record drainer (2172cd4).
    chart, base, manifest = _listen_values('prod', 'SERVER_BATCH_UNSUPPORTED_LANGUAGES')
    assert base == ''
    assert chart == manifest
    codes = set(chart.split(','))
    assert codes and codes <= set(server_batch.UNSUPPORTED) and 'ja' not in codes

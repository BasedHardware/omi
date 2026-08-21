"""Tests for the LLM-gateway route-coverage ratchet (ADR-0067).

The guard exists because an OMISSION in our override file is not "unconfigured": the gateway synthesises a
lane for every configured feature, and a feature with no override keeps its CLOUD provider from the QoS
table. Measured on this tree before the file was completed, 8 of 45 features were uncovered — six to
gemini, one to perplexity, one to openrouter, `translation` among them — and the only thing stopping those
lanes was the absence of those vendors' credentials.

It also checks the provider of every covered entry, which is the half that is easy to forget: a "covered"
count is meaningless if an entry can name gemini.

Driven through the pure functions over strings, so these tests are hermetic.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_oss_llm_gateway_route_coverage.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_oss_llm_gateway_route_coverage', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


TABLE = '''
_TWO_TIER_MODEL_PROFILE: Dict[str, Tuple[str, str]] = {
    'chat_agent': ('claude-sonnet-4-6', 'anthropic'),
    'translation': ('gemini-2.5-flash-lite', 'gemini'),
    'web_search': ('sonar-pro', 'perplexity'),
}

MODEL_QOS_PROFILES = {name: dict(_TWO_TIER_MODEL_PROFILE) for name in ('premium', 'max', 'byok')}

_PINNED_FEATURES: Dict[str, Tuple[str, str]] = {
    'fair_use': (os.getenv('FAIR_USE_CLASSIFIER_MODEL', 'gpt-5.6-luna').strip() or 'gpt-5.6-luna', 'openai'),
}
'''

HELM_VALUES = '''
chat:
  enabled: false
  llmGateway:
    enabled: false
    model: "qwen2.5:14b"
    features:
      - chat_agent
      - translation
      - fair_use
    requestTimeoutMsByFeature:
      translation: 900000
    resources: {}
  qdrant:
    # a sibling block with its own list-shaped key: must not contribute
    features:
      - not_a_lane
'''

OVERRIDES = '''
# a comment naming a feature: feature: not_real — must not be read as an entry
generated_route_overrides:
  - feature: chat_agent
    primary: {provider: openai, model: qwen2.5:14b}
  - feature: translation
    primary: {provider: openai, model: qwen2.5:14b}
  - feature: fair_use
    primary: {provider: openai, model: qwen2.5:14b}
'''


# --- reading the two sides ----------------------------------------------------------------------


def test_configured_features_is_the_union_of_the_profile_and_the_pins():
    assert _MODULE.configured_features(TABLE) == {'chat_agent', 'translation', 'web_search', 'fair_use'}


def test_a_renamed_table_is_an_error_not_an_empty_set():
    """The failure mode that matters: a guard that measures nothing and passes. An upstream rename is
    exactly how that happens, so it must be loud."""
    with pytest.raises(_MODULE.GuardError) as raised:
        _MODULE.configured_features(TABLE.replace('_TWO_TIER_MODEL_PROFILE', '_RENAMED_PROFILE'))
    assert '_TWO_TIER_MODEL_PROFILE' in str(raised.value)


def test_a_table_that_stops_being_a_dict_literal_is_an_error():
    """Valid Python, unreadable table: `dict(...)` instead of a literal. The keys are no longer visible
    to the AST, so the honest answer is an error, not a smaller set."""
    assert _MODULE.configured_features(TABLE)  # precondition
    rewritten = TABLE.replace(
        "_PINNED_FEATURES: Dict[str, Tuple[str, str]] = {\n    'fair_use': (os.getenv('FAIR_USE_CLASSIFIER_MODEL', 'gpt-5.6-luna').strip() or 'gpt-5.6-luna', 'openai'),\n}",
        "_PINNED_FEATURES = dict(fair_use=('gpt-5.6-luna', 'openai'))",
    )
    assert '_PINNED_FEATURES = dict(' in rewritten, 'the mutation must actually apply'
    with pytest.raises(_MODULE.GuardError):
        _MODULE.configured_features(rewritten)


def test_a_source_that_does_not_parse_names_the_file():
    with pytest.raises(_MODULE.GuardError) as raised:
        _MODULE.configured_features('_TWO_TIER_MODEL_PROFILE = {')
    assert 'model_config.py' in str(raised.value)


def test_overrides_are_read_with_their_provider_and_comments_are_not_entries():
    assert _MODULE.overridden_features(OVERRIDES) == {
        'chat_agent': 'openai',
        'translation': 'openai',
        'fair_use': 'openai',
    }


def test_an_entry_with_no_readable_provider_reports_empty_not_ours():
    """It must fail rule 2 rather than pass by defaulting to our provider."""
    text = OVERRIDES.replace(
        '  - feature: translation\n    primary: {provider: openai, model: qwen2.5:14b}', '  - feature: translation'
    )
    assert _MODULE.overridden_features(text)['translation'] == ''


# --- the second declaration: the chart ------------------------------------------------------------


def test_helm_features_are_read_only_from_the_gateway_block():
    """`features:` is a generic key; a sibling component could grow one. The walk is scoped."""
    features, timeouts = _MODULE.helm_declared(HELM_VALUES)
    assert features == {'chat_agent', 'translation', 'fair_use'}
    assert 'not_a_lane' not in features
    assert timeouts == {'translation': 900000}


def test_no_helm_values_means_no_drift_verdict():
    """Passing an empty string must not report 44 phantom drifts — the check has to be skippable."""
    result = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, '')
    assert result['helm_drift'] == []
    assert result['helm_timeout_drift'] == []


def test_a_lane_pinned_in_one_target_only_fails():
    """The measured failure: this pair had drifted from 44 to 4, and 41 of 45 lanes did not serve on the
    live k0s release while compose was fine."""
    helm = HELM_VALUES.replace('      - translation\n', '')
    result = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, helm)
    assert result['helm_drift'] == ['translation (compose only)']


def test_a_lane_the_chart_pins_and_compose_does_not_also_fails():
    """Drift has two directions and neither is acceptable."""
    helm = HELM_VALUES.replace('      - fair_use\n', '      - fair_use\n      - web_search\n')
    result = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, helm)
    assert result['helm_drift'] == ['web_search (helm only)']


def test_a_timeout_set_on_one_target_only_fails():
    """A missing request_timeout_ms caps a long extraction at 30s, so the lane fails on a local model."""
    compose = OVERRIDES.replace(
        '  - feature: translation\n    primary: {provider: openai, model: qwen2.5:14b}',
        '  - feature: translation\n    primary: {provider: openai, model: qwen2.5:14b}\n    request_timeout_ms: 900000',
    )
    assert _MODULE.compose_timeouts(compose) == {'translation': 900000}

    helm = HELM_VALUES.replace('      translation: 900000\n', '')
    result = _MODULE.check(TABLE, compose, {'web_search': 'note'}, helm)
    assert result['helm_timeout_drift'] == ['translation: compose=900000 helm=-']


def test_matching_targets_report_no_drift():
    compose = OVERRIDES.replace(
        '  - feature: translation\n    primary: {provider: openai, model: qwen2.5:14b}',
        '  - feature: translation\n    primary: {provider: openai, model: qwen2.5:14b}\n    request_timeout_ms: 900000',
    )
    result = _MODULE.check(TABLE, compose, {'web_search': 'note'}, HELM_VALUES)
    assert result['helm_drift'] == []
    assert result['helm_timeout_drift'] == []


# --- the ratchet --------------------------------------------------------------------------------


def test_an_uncovered_feature_with_a_note_passes():
    result = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'perplexity-only search product'})
    assert result['uncovered'] == []
    assert result['vendor_pinned'] == []
    assert result['stale_baseline'] == []
    assert result['unreviewed'] == []


def test_an_uncovered_feature_without_a_note_fails():
    assert _MODULE.check(TABLE, OVERRIDES, {})['uncovered'] == ['web_search']


def test_the_default_marker_counts_as_debt_but_still_passes():
    """`unreviewed` is the honest default and the count is the size of the debt — it is reported, not
    failed, exactly like the env-parity guard."""
    result = _MODULE.check(TABLE, OVERRIDES, {'web_search': _MODULE.UNREVIEWED})
    assert result['uncovered'] == []
    assert result['unreviewed'] == ['web_search']


def test_a_covered_feature_pinned_to_a_vendor_fails():
    """The half that a coverage count alone would miss: on paper covered, in fact routed to gemini."""
    text = OVERRIDES.replace(
        '  - feature: translation\n    primary: {provider: openai, model: qwen2.5:14b}',
        '  - feature: translation\n    primary: {provider: gemini, model: gemini-2.5-flash-lite}',
    )
    result = _MODULE.check(TABLE, text, {'web_search': 'note'})
    assert result['uncovered'] == []
    assert result['vendor_pinned'] == ['translation -> gemini']


def test_an_override_for_an_unknown_feature_fails():
    """The gateway itself raises ConfigValidationError on this and refuses to load, so the stack would
    not start. Catching it here is the same verdict, sooner."""
    text = OVERRIDES + '  - feature: not_a_feature\n    primary: {provider: openai, model: qwen2.5:14b}\n'
    assert _MODULE.check(TABLE, text, {'web_search': 'note'})['unknown_feature'] == ['not_a_feature']


def test_a_note_for_a_feature_we_now_cover_fails():
    text = OVERRIDES + '  - feature: web_search\n    primary: {provider: openai, model: qwen2.5:14b}\n'
    assert _MODULE.check(TABLE, text, {'web_search': 'note'})['stale_baseline'] == ['web_search']


def test_a_note_for_a_feature_that_no_longer_exists_fails():
    assert _MODULE.check(TABLE, OVERRIDES, {'retired_feature': 'note'})['stale_baseline'] == ['retired_feature']


# --- the baseline file --------------------------------------------------------------------------


def test_a_baseline_of_blank_notes_is_rejected(tmp_path):
    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps({'web_search': '   '}), encoding='utf-8')
    with pytest.raises(ValueError):
        _MODULE.load_baseline(path)


def test_an_empty_baseline_file_says_what_happened(tmp_path):
    """Almost always `--print-baseline > <the baseline>`: the shell truncates before the read."""
    path = tmp_path / 'baseline.json'
    path.write_text('', encoding='utf-8')
    with pytest.raises(ValueError) as raised:
        _MODULE.load_baseline(path)
    assert 'empty' in str(raised.value)


# --- the real tree ------------------------------------------------------------------------------


def test_the_repository_is_at_or_below_its_baseline():
    """The ratchet on the real tree — the check CI runs."""
    root = Path(__file__).resolve().parents[3]
    table_source, overrides_text, helm_values_text = _MODULE._read(root)
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    result = _MODULE.check(table_source, overrides_text, baseline, helm_values_text)
    assert result['uncovered'] == []
    assert result['vendor_pinned'] == []
    assert result['unknown_feature'] == []
    assert result['stale_baseline'] == []
    assert result['helm_drift'] == []
    assert result['helm_timeout_drift'] == []


def test_web_search_is_the_only_written_off_lane_and_it_carries_a_real_note():
    """If a second lane ever gets written off, that is a decision someone must have made on purpose —
    and this test is where they have to come and say so."""
    root = Path(__file__).resolve().parents[3]
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    assert set(baseline) == {'web_search'}
    assert baseline['web_search'].strip() != _MODULE.UNREVIEWED

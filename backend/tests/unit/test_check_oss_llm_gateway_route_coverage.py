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

# The chart AFTER unification (ADR-0081): the lane list is gone from the values and the template reads
# the shared file. The tests below re-introduce each half of the old shape to prove the guard catches it.
HELM_VALUES = '''
chat:
  enabled: false
  llmGateway:
    enabled: false
    model: "qwen2.5:14b"
    resources: {}
  qdrant:
    # a sibling block with its own list-shaped key: must not contribute
    features:
      - not_a_lane
'''

HELM_TEMPLATE = '''
data:
  generated_route_overrides.yaml: |
    generated_route_overrides:
    {{- $file := .Files.Get "files/generated_route_overrides.yaml" | fromYaml }}
    {{- range $file.generated_route_overrides }}
      - feature: {{ .feature }}
    {{- end }}
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


# --- the second declaration must not come back ----------------------------------------------------


def test_the_unified_chart_reports_nothing():
    result = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, HELM_VALUES, HELM_TEMPLATE)
    assert result['second_declaration'] == []


def test_no_chart_text_means_no_verdict():
    """Passing empty strings must not report a phantom problem — the check has to be skippable."""
    assert _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, '', '')['second_declaration'] == []


def test_a_features_list_growing_back_in_the_values_fails():
    """The exact regression this replaces: a hand-kept copy next to a comment asking someone to remember
    to update it. It drifted from 44 lanes to 4, and 41 of 45 lanes did not serve on the live release."""
    values = HELM_VALUES.replace(
        '    model: "qwen2.5:14b"\n', '    model: "qwen2.5:14b"\n    features:\n      - chat_agent\n'
    )
    problems = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, values, HELM_TEMPLATE)['second_declaration']
    assert len(problems) == 1
    assert 'chat.llmGateway.features' in problems[0]


def test_a_timeout_map_growing_back_in_the_values_fails():
    """The timeouts travel with the lanes; splitting them is the same defect one field smaller."""
    values = HELM_VALUES.replace(
        '    model: "qwen2.5:14b"\n',
        '    model: "qwen2.5:14b"\n    requestTimeoutMsByFeature:\n      translation: 900000\n',
    )
    problems = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, values, HELM_TEMPLATE)['second_declaration']
    assert len(problems) == 1
    assert 'requestTimeoutMsByFeature' in problems[0]


def test_a_sibling_block_with_its_own_features_key_does_not_count():
    """`features:` is generic; the walk is scoped to the llmGateway block. HELM_VALUES already carries a
    qdrant sibling with one, and it must stay silent."""
    assert 'not_a_lane' in HELM_VALUES
    assert (
        _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, HELM_VALUES, HELM_TEMPLATE)['second_declaration'] == []
    )


def test_a_template_that_stopped_reading_the_file_fails():
    """The subtler half: the values are clean, so nothing looks duplicated, but the ConfigMap renders
    EMPTY and every feature silently keeps its cloud model."""
    template = HELM_TEMPLATE.replace('.Files.Get "files/generated_route_overrides.yaml"', 'dict')
    problems = _MODULE.check(TABLE, OVERRIDES, {'web_search': 'note'}, HELM_VALUES, template)['second_declaration']
    assert len(problems) == 1
    assert 'CLOUD model' in problems[0]


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
    table_source, overrides_text, helm_values_text, helm_template_text = _MODULE._read(root)
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    result = _MODULE.check(table_source, overrides_text, baseline, helm_values_text, helm_template_text)
    assert result['uncovered'] == []
    assert result['vendor_pinned'] == []
    assert result['unknown_feature'] == []
    assert result['stale_baseline'] == []
    assert result['second_declaration'] == []


def test_web_search_is_the_only_written_off_lane_and_it_carries_a_real_note():
    """If a second lane ever gets written off, that is a decision someone must have made on purpose —
    and this test is where they have to come and say so."""
    root = Path(__file__).resolve().parents[3]
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    assert set(baseline) == {'web_search'}
    assert baseline['web_search'].strip() != _MODULE.UNREVIEWED

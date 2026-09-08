from __future__ import annotations

import ast
import os
import re
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
import pytest

from llm_gateway.gateway.config_loader import feature_lane_id, load_gateway_config, load_generated_route_overrides
from llm_gateway.gateway.schemas import Surface
from utils.llm.model_config import get_all_configured_features, get_route_options, get_model, get_provider

BACKEND_DIR = Path(__file__).resolve().parents[2]
INVENTORY_PATH = BACKEND_DIR / 'docs' / 'llm' / 'model_endpoint_inventory.yaml'

DIRECT_CONSTRUCTOR_NAMES = {
    'openai.OpenAI',
    'openai.AsyncOpenAI',
    'anthropic.Anthropic',
    'anthropic.AsyncAnthropic',
    'langchain_openai.ChatOpenAI',
    'langchain_openai.OpenAIEmbeddings',
    'langchain_anthropic.ChatAnthropic',
    'langchain_google_genai.ChatGoogleGenerativeAI',
    'google.genai.Client',
    'genai.Client',
}
DIRECT_PROVIDER_CALL_PREFIXES = {
    'openai.beta',
    'openai.chat.completions',
    'openai.files',
    'anthropic_client.messages',
}
DIRECT_PROVIDER_ENV_VARS = {
    'OPENAI_API_KEY',
    'OPENROUTER_API_KEY',
    'ANTHROPIC_API_KEY',
    'PERPLEXITY_API_KEY',
    'GEMINI_API_KEY',
}


@dataclass(frozen=True)
class DirectUse:
    rel_path: str
    symbol: str


DIRECT_PROVIDER_ALLOWLIST = {
    DirectUse('llm_gateway/routers/openai_compatible.py', 'OPENAI_API_KEY'),
    DirectUse('llm_gateway/routers/anthropic_messages.py', 'ANTHROPIC_API_KEY'),
    DirectUse('llm_gateway/routers/health.py', 'ANTHROPIC_API_KEY'),
    DirectUse('llm_gateway/routers/health.py', 'OPENAI_API_KEY'),
    DirectUse('llm_gateway/routers/health.py', 'PERPLEXITY_API_KEY'),
    DirectUse('routers/desktop_proxy.py', 'GEMINI_API_KEY'),
    DirectUse('routers/desktop_realtime.py', 'GEMINI_API_KEY'),
    DirectUse('routers/desktop_realtime.py', 'OPENAI_API_KEY'),
    DirectUse('routers/desktop_tts_updates.py', 'OPENAI_API_KEY'),
    DirectUse('utils/llm/providers.py', 'ChatGoogleGenerativeAI'),
    DirectUse('utils/llm/providers.py', 'ChatOpenAI'),
    DirectUse('utils/llm/providers.py', 'GEMINI_API_KEY'),
    DirectUse('utils/llm/clients.py', 'AsyncAnthropic'),
    DirectUse('utils/llm/gateway_anthropic.py', 'AsyncAnthropic'),
    DirectUse('utils/llm/clients.py', 'ChatAnthropic'),
    DirectUse('utils/llm/clients.py', 'ChatOpenAI'),
    DirectUse('utils/llm/clients.py', 'GEMINI_API_KEY'),
    DirectUse('utils/llm/clients.py', 'OpenAIEmbeddings'),
    DirectUse('utils/memory_ingestion/export_runner.py', 'OPENAI_API_KEY'),
    DirectUse('utils/other/chat_file.py', 'AsyncOpenAI'),
    DirectUse('utils/other/chat_file.py', 'openai.chat.completions'),
    DirectUse('utils/other/chat_file.py', 'openai.files'),
    # gateway_client.py constructs SDK clients pointed at the gateway itself
    # (OpenAI-compatible surface); these never reach a provider directly.
    DirectUse('utils/llm/gateway_client.py', 'AsyncOpenAI'),
    DirectUse('utils/llm/gateway_client.py', 'OpenAI'),
    DirectUse('utils/retrieval/agentic.py', 'anthropic_client.messages'),
    DirectUse('routers/omni_relay.py', 'GEMINI_API_KEY'),
    DirectUse('routers/omni_relay.py', 'OPENAI_API_KEY'),
}
INVENTORIED_DIRECT_EXCEPTION_FILES = {
    'routers/desktop_proactivity.py',
    'routers/omni_relay.py',
}

_RESOLVER_CALL_NAMES = frozenset(
    {'get_llm', 'get_model', 'get_provider', 'get_route_ref', '_get_model_config', 'get_model_config'}
)
_RESOLVER_NAME_RE = re.compile(r'\b(?:' + '|'.join(sorted(_RESOLVER_CALL_NAMES, key=len, reverse=True)) + r')\b')
_RESOLVER_DEFINITION_FILE = 'utils/llm/model_config.py'
# Reviewed non-literal (path, callee, arg). A new triple fails until reviewed.
# persona.py: ternary persona_chat / persona_chat_premium.
# config_loader.py and clients.get_qos_info: iterate get_all_configured_features().
# clients.get_llm: pass-through of the caller's feature into _get_model_config.
# clients._so_gemini: iterates the active profile.
# judge.py: model_feature defaults to the pinned screen_frame_judge key.
# managed_compute.py: pass-through of authorize_managed_compute's feature into get_provider.
KNOWN_DYNAMIC_FEATURE_SITES = frozenset(
    {
        ('utils/llm/persona.py', 'get_llm', 'feature'),
        ('llm_gateway/gateway/config_loader.py', 'get_model', 'feature'),
        ('llm_gateway/gateway/config_loader.py', 'get_provider', 'feature'),
        ('utils/llm/clients.py', '_get_model_config', 'feature'),
        ('utils/memory/belief_backfill.py', 'get_llm', 'BELIEF_BACKFILL_LLM_FEATURE'),
        ('utils/llm/clients.py', '_get_model_config', 'f'),
        ('utils/screen_frames/judge.py', 'get_llm', 'model_feature'),
        ('utils/managed_compute.py', 'get_provider', 'feature'),
    }
)
_FEATURE_SCAN_SKIP_DIRS = {'.venv', 'venv', '.openapi-venv', '__pycache__', 'tests'}
_SNIPPET_CONFIGURED = {'chat_agent', 'memory_l1', 'conv_structure', 'what_matters_now'}


def _frozenset_literals_from_assign(tree: ast.Module, name: str) -> frozenset[str]:
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        if target != name or value is None:
            continue
        call = value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'frozenset':
            arg = call.args[0] if call.args else None
            if isinstance(arg, (ast.Set, ast.List, ast.Tuple)):
                return frozenset(
                    elt.value for elt in arg.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                )
        if isinstance(call, (ast.Tuple, ast.List)):
            return frozenset(
                elt.value for elt in call.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )
    raise AssertionError(f'could not read {name} from managed_compute.py')


def _str_constant_from_assign(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if (
                node.targets[0].id == name
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                return node.value.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise AssertionError(f'could not read {name} from managed_compute.py')


# Reuse S1's vocabulary without importing managed_compute (that module pulls
# database.users and hangs this file's existing import graph).
_MANAGED_COMPUTE_TREE = ast.parse(
    (Path(__file__).resolve().parents[2] / 'utils' / 'managed_compute.py').read_text(encoding='utf-8')
)
DECISION_REASONS = _frozenset_literals_from_assign(_MANAGED_COMPUTE_TREE, 'DECISION_REASONS')
FREE_ALLOWLIST_FEATURES = _frozenset_literals_from_assign(_MANAGED_COMPUTE_TREE, 'FREE_ALLOWLIST_FEATURES')
FREE_ALLOWLIST_PREFIX = _str_constant_from_assign(_MANAGED_COMPUTE_TREE, 'FREE_ALLOWLIST_PREFIX')
FUNDING_OWNERS = _frozenset_literals_from_assign(_MANAGED_COMPUTE_TREE, 'FUNDING_OWNERS')

# S7: plan-gating is S1's reason vocabulary plus the realtime quota label.
PLAN_GATING_VALUES = DECISION_REASONS | {'unified_chat_quota'}
FALLBACK_ON_DENY_VALUES = frozenset(
    {
        'deterministic_minimum',
        'http_402',
        'quota_refuse',
        'none_unwired',
        'gateway_fail_closed',
        'n/a_allowed',
    }
)
# Sol claim 9 missed list + realtime usage/relay companions. A rename fails CI.
REQUIRED_USER_SURFACES = frozenset(
    {
        'desktop_realtime_token_mint',
        'desktop_realtime_usage',
        'omni_realtime_relay',
        'wrapped_generation',
        'listen_onboarding',
        'session_titles',
        'what_matters_now',
        'app_integration',
        'app_generation',
        'conversation_test_prompt',
        'phone_call_processing',
        'external_integrations',
        'sync_limitless',
        'conversation_merge',
        'conversation_reprocess',
    }
)
LLM_REST_HOSTS = (
    'api.openai.com',
    'generativelanguage.googleapis.com',
    'api.anthropic.com',
    'openrouter.ai',
    'api.perplexity.ai',
    'aiplatform.googleapis.com',
)


def test_every_model_config_feature_has_inventory_and_gateway_lane():
    inventory = _load_inventory()
    configured_features = get_all_configured_features()
    listed_features = set()
    for values in inventory['model_config_features']['request_shapes'].values():
        listed_features.update(values)

    assert configured_features <= listed_features

    config = load_gateway_config(prod_mode=True)
    missing_lanes = [feature for feature in configured_features if feature_lane_id(feature) not in config.lanes]
    assert missing_lanes == []


def test_generated_gateway_lanes_apply_only_declared_gateway_route_overrides():
    config = load_gateway_config(prod_mode=True)
    overrides = load_generated_route_overrides()

    for feature in get_all_configured_features():
        override = overrides.get(feature)
        model = override.primary.model if override is not None else get_model(feature)
        provider = override.primary.provider if override is not None else get_provider(feature)
        route = config.route_artifacts[f'route.{feature}.model_config.001']

        expected_options = get_route_options(feature, model, provider)
        if override is not None:
            expected_options.update(override.provider_options)
        expected_provider_model = (
            f'google/{model}' if provider == 'openrouter' and model.startswith('gemini') else model
        )
        assert route.primary.model == expected_provider_model
        assert route.primary.provider == provider
        assert route.provider_options == expected_options


def test_persona_auth_tiers_resolve_to_fixed_gateway_models():
    overrides = load_generated_route_overrides()

    assert overrides['persona_chat'].primary.model == 'gpt-5-nano'
    assert overrides['persona_chat_premium'].primary.model == 'gpt-5.6-luna'


def test_every_gpt5_generated_lane_pins_an_explicit_reasoning_effort():
    """A GPT-5 lane without a pinned effort rides the provider default.

    File chat ran unpinned with a 2048-token output cap, and the provider
    default can spend a capped completion budget on hidden reasoning before
    any answer text — the truncation failure desktop proactivity hit on its
    direct path. Every OpenAI GPT-5 lane must name its effort explicitly.
    """
    overrides = load_generated_route_overrides()

    for feature in get_all_configured_features():
        override = overrides.get(feature)
        model = override.primary.model if override is not None else get_model(feature)
        provider = override.primary.provider if override is not None else get_provider(feature)
        if provider != 'openai' or not model.startswith('gpt-5'):
            continue
        options = get_route_options(feature, model, provider)
        if override is not None:
            options.update(override.provider_options)
        assert 'reasoning_effort' in options, feature


def test_only_background_flex_routes_allow_the_documented_flex_timeout():
    config = load_gateway_config(prod_mode=True)

    assert config.route_artifacts['route.memory_conflict.model_config.001'].timeouts.request_ms == 120_000
    assert config.route_artifacts['route.memory_conflict_flex.model_config.001'].timeouts.request_ms == 900_000
    assert config.route_artifacts['route.memory_l2_flex.model_config.001'].timeouts.request_ms == 900_000
    assert config.route_artifacts['route.x_memory_extraction_flex.model_config.001'].timeouts.request_ms == 900_000


def test_anthropic_generated_lanes_do_not_advertise_streaming_without_adapter_support():
    config = load_gateway_config(prod_mode=True)

    for feature in get_all_configured_features():
        if get_provider(feature) == 'anthropic' and feature != 'chat_agent':
            lane = config.lanes[feature_lane_id(feature)]
            assert lane.surface == Surface.OPENAI_CHAT_COMPLETIONS
            assert lane.capabilities.streaming is False

    chat_agent = config.lanes[feature_lane_id('chat_agent')]
    assert chat_agent.surface == Surface.OPENAI_CHAT_COMPLETIONS
    assert chat_agent.capabilities.streaming is True
    assert chat_agent.capabilities.tools is True


def test_inventory_surfaces_have_status_guardrails_and_resolvable_code_paths():
    inventory = _load_inventory()

    assert inventory['schema_version'] == 'llm_model_endpoint_inventory.v1'
    assert isinstance(inventory['out_of_scope_surfaces'], list)
    names: list[str] = []
    for surface in inventory['surfaces']:
        assert surface['surface']
        names.append(surface['surface'])
        assert surface['code_path']
        assert surface['entrypoint']
        assert surface['feature']
        assert surface['plan_gating'] in PLAN_GATING_VALUES, surface['surface']
        assert surface['funding_owner'] in FUNDING_OWNERS, surface['surface']
        assert surface['fallback_on_deny'] in FALLBACK_ON_DENY_VALUES, surface['surface']
        assert isinstance(surface.get('call_sites'), list), surface['surface']
        assert surface['current_provider_model']
        assert surface['request_shape']
        assert surface['gateway_lane_capability_needed']
        assert surface['migration_status']
        assert surface['test_guardrail_coverage']
        assert _inventory_file_exists(surface['code_path']), surface['code_path']
        _assert_plan_gating_matches_allowlist(surface)
    assert len(names) == len(set(names))
    assert REQUIRED_USER_SURFACES <= set(names)


def _assert_plan_gating_matches_allowlist(surface: dict) -> None:
    feature = surface['feature']
    gating = surface['plan_gating']
    if gating == 'unified_chat_quota' or feature in {
        '*',
        'desktop_vertex',
        'desktop_tts',
        'omni_relay',
        'desktop_chat_realtime',
        'public_shared_conversation_chat',
        'openai_embeddings',
        'gemini_embeddings',
        'file_chat_vision',
        'file_chat_documents',
    }:
        return
    on_allowlist = feature in FREE_ALLOWLIST_FEATURES or feature.startswith(FREE_ALLOWLIST_PREFIX)
    if gating == 'free_allowlist':
        assert on_allowlist, surface['surface']
    if gating == 'basic_not_entitled':
        assert not on_allowlist, surface['surface']


def test_required_user_surfaces_are_named():
    """Sol claim 9's missed list must keep a named row. A rename is a CI failure."""
    names = {surface['surface'] for surface in _load_inventory()['surfaces']}
    assert REQUIRED_USER_SURFACES <= names


_ACCESSOR_PROBE_SOURCE = textwrap.dedent("""
    import openai
    from openai import AsyncOpenAI

    _async_openai = None


    def _get_async_openai() -> AsyncOpenAI:
        global _async_openai
        if _async_openai is None:
            _async_openai = AsyncOpenAI(timeout=120.0)
        return _async_openai


    def _get_sync_openai():
        return openai


    async def ask():
        await _get_async_openai().chat.completions.create(model='m', messages=[])
        _get_sync_openai().files.create(file=None, purpose='assistants')
    """)


def test_direct_provider_scan_sees_through_a_provider_accessor():
    """A helper that hands back a provider client is not a boundary.

    ``_dotted_name`` drops the receiver when it is a call, so
    ``_get_async_openai().chat.completions.create(...)`` read as the unowned
    ``chat.completions.create`` and the scan saw nothing. That is how a real
    direct-OpenAI fallback in ``utils/other/chat_file.py`` became invisible
    while its allowlist entry stayed behind as a stale one, which is what
    this whole test module reports.

    The accessor resolves by return annotation, by returning an imported
    provider module, or by returning a name bound to a constructor call —
    all three appear in the probe below.

    red-proof: drop the accessor re-read in ``_direct_provider_uses`` and both
    assertions fail; the plain dotted-name walk yields no provider symbol.
    """
    uses = {use.symbol for use in _direct_provider_uses('probe.py', ast.parse(_ACCESSOR_PROBE_SOURCE))}

    assert 'openai.chat.completions' in uses, 'a lazily constructed client reached through an accessor'
    assert 'openai.files' in uses, 'the provider module itself returned by an accessor'


def test_direct_provider_scan_reports_the_file_chat_direct_fallback():
    """The live site the accessor blind spot hid.

    ``chat_file.py`` falls back to direct OpenAI when the gateway lane is
    missing or returns a model-not-found. That call is real, it is
    allowlisted, and the scan must keep seeing it: an inventory that silently
    stops detecting a direct provider call is worse than one that never had
    the entry.
    """
    rel = 'utils/other/chat_file.py'
    tree = ast.parse((BACKEND_DIR / rel).read_text(encoding='utf-8'))

    uses = {use.symbol for use in _direct_provider_uses(rel, tree)}

    assert 'openai.chat.completions' in uses


_REST_HOST_PROBE_SOURCE = textwrap.dedent("""
    import httpx

    _OPENAI_CLIENT_SECRETS_URL = 'https://api.openai.com/v1/realtime/client_secrets'
    _GEMINI_AUTH_TOKENS_URL = 'https://generativelanguage.googleapis.com/v1alpha/auth_tokens'


    async def mint():
        await httpx.AsyncClient().post(_OPENAI_CLIENT_SECRETS_URL, json={})
        await httpx.AsyncClient().post(_GEMINI_AUTH_TOKENS_URL, params={'key': 'k'})
    """)


def test_managed_site_scan_sees_rest_hosts_not_just_sdk_names():
    """Omi calls some vendors over raw REST with httpx; a missing SDK is not a missing surface.

    red-proof: drop the host walk in ``_managed_sites_in_tree`` and both assertions fail.
    """
    sites = {key for _path, key in _managed_sites_in_tree('probe.py', ast.parse(_REST_HOST_PROBE_SOURCE))}
    assert 'host:api.openai.com' in sites
    assert 'host:generativelanguage.googleapis.com' in sites


_HOST_CONTEXT_PROBE_SOURCE = textwrap.dedent("""
    import httpx

    _DOCS_URL = 'https://api.openai.com/docs'


    def _raise_quota_error():
        raise RuntimeError('api.openai.com is quota-capped')


    async def call_default_base_url():
        # vendor-reachable: bound as the client's default base_url
        async with httpx.AsyncClient(base_url='https://api.anthropic.com/v1') as client:
            await client.post('/messages', json={})
    """)


def test_managed_host_scan_ignores_non_call_host_mentions():
    """A host string only counts where it can plausibly reach a vendor.

    The scan flags call arguments, assignments, parameter defaults, and
    returned URL builders. A docstring, an error message, or an unused
    constant that merely mentions a host must not become a required
    inventory ``host:`` call_site.

    red-proof: revert ``_vendor_host_sites`` to the bare ``ast.Constant``
    walk and the ``not in`` assertions fail (the mentions get flagged).
    """
    sites = _managed_sites_in_tree('probe.py', ast.parse(_HOST_CONTEXT_PROBE_SOURCE))
    assert ('probe.py', 'host:api.openai.com') not in sites  # unused constant + error message
    assert ('probe.py', 'host:api.anthropic.com') in sites  # client base_url default arg


def test_managed_site_scan_sees_get_llm_literals():
    source = "from utils.llm.clients import get_llm\nget_llm('wrapped_analysis')\n"
    sites = _managed_sites_in_tree('utils/wrapped/probe.py', ast.parse(source))
    assert sites == {('utils/wrapped/probe.py', 'feature:wrapped_analysis')}


@pytest.mark.slow
def test_managed_call_sites_absent_from_the_inventory_fail_ci():
    """A managed get_llm or LLM REST host not listed on a surface row fails CI.

    This is the S7 automatic-or-dead check. Exact-set pin: new sites fail until
    inventoried; stale inventory rows fail until removed. Coordinator-only
    surfaces (sync/merge/reprocess/phone) have empty call_sites on purpose —
    they spend through process_conversation, which is pinned on langchain /
    conversation_processing files.

    Slow-marked per tests/README.md: it is a full-backend codebase scan, and
    codebase greps leave the PR unit-test lane via ``@pytest.mark.slow`` rather
    than the fast-unit duration allowlist.

    red-proof: delete a known call_site from model_endpoint_inventory.yaml
    (the real file) and this assertion goes red.
    """
    discovered = _scan_managed_call_sites()
    inventoried = _inventory_call_sites()
    missing = sorted(discovered - inventoried)
    stale = sorted(inventoried - discovered)
    assert missing == [], 'managed call sites absent from the inventory: ' + '; '.join(
        f'{path}::{key}' for path, key in missing
    )
    assert stale == [], 'inventory call_sites with no matching production site: ' + '; '.join(
        f'{path}::{key}' for path, key in stale
    )
    duplicates = _duplicate_inventory_call_sites()
    assert duplicates == [], 'call_site claimed by more than one surface: ' + '; '.join(duplicates)


@pytest.mark.slow
def test_direct_provider_usage_stays_inside_approved_boundaries():
    detected = set()
    for path in BACKEND_DIR.rglob('*.py'):
        rel = path.relative_to(BACKEND_DIR).as_posix()
        if _is_skipped_path(rel):
            continue
        source = path.read_text(encoding='utf-8')
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        detected.update(_direct_provider_uses(rel, tree))

    violations = sorted(detected - DIRECT_PROVIDER_ALLOWLIST, key=lambda item: (item.rel_path, item.symbol))
    stale_allowlist = sorted(DIRECT_PROVIDER_ALLOWLIST - detected, key=lambda item: (item.rel_path, item.symbol))

    assert violations == []
    assert stale_allowlist == []


def test_direct_exception_files_follow_their_declared_gateway_policy():
    inventory = _load_inventory()
    inventory_paths = {_code_path_file(surface['code_path']) for surface in inventory['surfaces']}

    assert INVENTORIED_DIRECT_EXCEPTION_FILES <= inventory_paths
    policies_by_file: dict[str, set[str]] = {path: set() for path in INVENTORIED_DIRECT_EXCEPTION_FILES}
    for surface in inventory['surfaces']:
        rel_path = _code_path_file(surface['code_path'])
        if rel_path in policies_by_file:
            policies_by_file[rel_path].add(_direct_exception_policy(surface['migration_status']))

    assert all(len(policies) == 1 for policies in policies_by_file.values())
    policy_by_file = {rel_path: next(iter(policies)) for rel_path, policies in policies_by_file.items()}
    assert policy_by_file['routers/desktop_proactivity.py'] == 'acknowledged'
    assert policy_by_file['routers/omni_relay.py'] == 'blocked'

    for rel_path, policy in policy_by_file.items():
        source = (BACKEND_DIR / rel_path).read_text(encoding='utf-8')
        if policy == 'acknowledged':
            assert 'record_direct_exception_surface' in source
            assert 'raise_if_gateway_feature_mode_blocks_direct_model_surface' not in source
        elif policy == 'blocked':
            assert 'raise_if_gateway_feature_mode_blocks_direct_model_surface' in source
            assert 'record_direct_exception_surface' not in source
        else:
            raise AssertionError(f'unknown direct gateway policy {policy!r} for {rel_path}')


def scan_resolver_feature_calls(
    rel_path: str, source: str, configured: set[str]
) -> tuple[list[str], set[tuple[str, str, str]]]:
    """Return (unknown_literals, dynamic_sites) for one module's source.

    Prefilter matches resolver names as bare words, not ``name(``, so
    ``from utils.llm.clients import get_llm as resolve; resolve(x)`` is parsed.
    """
    if _RESOLVER_NAME_RE.search(source) is None:
        return [], set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], set()

    import_aliases: dict[str, str] = {}
    name_assigns: list[tuple[str, ast.AST]] = []
    dict_nodes: list[ast.Dict] = []
    partial_calls: list[ast.Call] = []
    attr_assigns: list[tuple[ast.Attribute, ast.AST]] = []
    calls: list[ast.Call] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_aliases[alias.asname or alias.name.split('.')[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                import_aliases[alias.asname or alias.name] = f'{node.module}.{alias.name}'
        elif isinstance(node, ast.Dict):
            dict_nodes.append(node)
        elif isinstance(node, ast.Call):
            if _is_partial_call(node):
                partial_calls.append(node)
            elif not _is_cast_call(node):
                calls.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name_assigns.append((target.id, node.value))
                elif isinstance(target, ast.Attribute):
                    attr_assigns.append((target, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                name_assigns.append((node.target.id, node.value))
            elif isinstance(node.target, ast.Attribute):
                attr_assigns.append((node.target, node.value))

    local_aliases = _aliases_from_assignments(name_assigns, import_aliases)
    unknown_literals: list[str] = []
    dynamic_sites: set[tuple[str, str, str]] = set()

    for dict_node in dict_nodes:
        for value in dict_node.values:
            basename = _resolver_basename_from_value(value, import_aliases, local_aliases)
            if basename is not None:
                dynamic_sites.add((rel_path, basename, ast.unparse(dict_node)))
    for partial in partial_calls:
        for value in list(partial.args) + [keyword.value for keyword in partial.keywords]:
            basename = _resolver_basename_from_value(value, import_aliases, local_aliases)
            if basename is not None:
                dynamic_sites.add((rel_path, basename, ast.unparse(partial)))
                break
    for target, value in attr_assigns:
        basename = _resolver_basename_from_value(value, import_aliases, local_aliases)
        if basename is not None:
            dynamic_sites.add((rel_path, basename, ast.unparse(target)))

    for node in calls:
        callee = _resolver_call_name(node.func, import_aliases, local_aliases)
        if callee is None:
            continue
        arg = _feature_call_arg(node)
        if arg is None:
            continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value not in configured:
                unknown_literals.append(f'{rel_path}:{node.lineno} {callee}({arg.value!r})')
            continue
        dynamic_sites.add((rel_path, callee, ast.unparse(arg)))

    return unknown_literals, dynamic_sites


def test_resolver_scan_imported_alias():
    source = "from utils.llm.clients import get_llm as resolve\nresolve('chat_agent')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == []
    assert dynamic == set()


def test_resolver_scan_imported_alias_unknown_literal():
    source = "from utils.llm.clients import get_llm as resolve\nresolve('made_up_feature')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == ["snippet.py:2 get_llm('made_up_feature')"]
    assert dynamic == set()


def test_resolver_scan_module_qualified_call():
    source = "import utils.llm.clients\nutils.llm.clients.get_llm('chat_agent')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == []
    assert dynamic == set()


def test_resolver_scan_feature_keyword():
    source = "get_llm(feature='chat_agent')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == []
    assert dynamic == set()


def test_resolver_scan_cast_alias():
    source = "from typing import Any, cast\nllm_factory = cast(Any, get_llm)\nllm_factory('memory_l1')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == []
    assert dynamic == set()
    source = "from typing import Any, cast\nllm_factory = cast(Any, get_llm)\nllm_factory('made_up_feature')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == ["snippet.py:3 get_llm('made_up_feature')"]
    assert dynamic == set()


def test_resolver_scan_one_step_name_alias():
    source = "resolve = get_llm\nresolve('chat_agent')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == []
    assert dynamic == set()
    unknown, dynamic = scan_resolver_feature_calls(
        'snippet.py', "resolve = get_llm\nresolve('made_up_feature')\n", set()
    )
    assert unknown == ["snippet.py:2 get_llm('made_up_feature')"]
    assert dynamic == set()


def test_resolver_scan_get_model_config_literal():
    source = "get_model_config('conv_structure')\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == []
    assert dynamic == set()
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', "get_model_config('made_up_feature')\n", set())
    assert unknown == ["snippet.py:1 get_model_config('made_up_feature')"]
    assert dynamic == set()


def test_resolver_scan_unfollowable_alias_is_dynamic():
    source = "ROUTES = {'x': get_llm}\n"
    unknown, dynamic = scan_resolver_feature_calls('snippet.py', source, _SNIPPET_CONFIGURED)
    assert unknown == []
    assert dynamic == {('snippet.py', 'get_llm', "{'x': get_llm}")}


def test_resolver_feature_literals_are_configured_and_dynamic_sites_are_reviewed():
    """Every literal feature must be mapped; new dynamic sites need review.

    Fail closed: never a silent fall-through to luna for an unmapped feature.
    """
    configured = get_all_configured_features()
    unknown_literals: list[str] = []
    dynamic_sites: set[tuple[str, str, str]] = set()
    started = time.perf_counter()
    for path in _iter_backend_py_files():
        rel = path.relative_to(BACKEND_DIR).as_posix()
        if rel == _RESOLVER_DEFINITION_FILE:
            continue
        source = path.read_text(encoding='utf-8')
        file_unknown, file_dynamic = scan_resolver_feature_calls(rel, source, configured)
        unknown_literals.extend(file_unknown)
        dynamic_sites.update(file_dynamic)
    elapsed = time.perf_counter() - started
    # Isolated walk is ~0.2s; do not hard-fail on noisy combined-run wall time.
    print(f'tree_scan_elapsed_s={elapsed:.3f}')
    assert unknown_literals == [], 'literal features missing from get_all_configured_features(): ' + '; '.join(
        unknown_literals
    )
    assert dynamic_sites == KNOWN_DYNAMIC_FEATURE_SITES


def test_file_chat_completions_hop_the_gateway_in_feature_mode():
    """File chat's model call is gateway-routed; only the kill-switch path stays direct.

    Static tripwire for the file-chat gateway lanes: under
    OMI_LLM_GATEWAY_FEATURE_MODE=gateway the completions call must go through
    the gateway client, never a raw direct SDK call, and the surface must not
    swing back to the fail-closed blocking gate. Behavioral coverage lives in
    test_chat_file_gateway_surface.py.
    """
    source = (BACKEND_DIR / 'utils/other/chat_file.py').read_text(encoding='utf-8')

    assert 'get_file_chat_gateway_async_client' in source
    assert 'file_chat_auto_lane_id' in source
    assert 'raise_if_gateway_feature_mode_blocks_direct_model_surface' not in source


def _load_inventory() -> dict:
    with INVENTORY_PATH.open('r', encoding='utf-8') as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


def _parse_call_site(item: str) -> tuple[str, str]:
    path, sep, key = item.partition('::')
    assert sep, f'call_site must be path::key, got {item!r}'
    assert path and key, item
    return path, key


def _inventory_call_sites() -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    for surface in _load_inventory()['surfaces']:
        for item in surface.get('call_sites') or []:
            sites.add(_parse_call_site(item))
    return sites


def _duplicate_inventory_call_sites() -> list[str]:
    seen: dict[tuple[str, str], str] = {}
    duplicates: list[str] = []
    for surface in _load_inventory()['surfaces']:
        name = surface['surface']
        for item in surface.get('call_sites') or []:
            parsed = _parse_call_site(item)
            if parsed in seen:
                duplicates.append(f'{item} ({seen[parsed]} and {name})')
            else:
                seen[parsed] = name
    return duplicates


def _scan_managed_call_sites() -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    extra_skip = {'charts', 'deploy', 'parakeet', 'diarizer', 'nllb_translation', 'modal'}
    for path in _iter_backend_py_files():
        rel = path.relative_to(BACKEND_DIR).as_posix()
        if _is_skipped_path(rel) or rel.split('/', 1)[0] in extra_skip:
            continue
        source = path.read_text(encoding='utf-8')
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        sites.update(_managed_sites_in_tree(rel, tree))
    return sites


def _managed_sites_in_tree(rel: str, tree: ast.AST) -> set[tuple[str, str]]:
    """get_llm literals (incl. aliases/cast) and LLM REST host string constants."""
    sites: set[tuple[str, str]] = set()
    import_aliases: dict[str, str] = {}
    name_assigns: list[tuple[str, ast.AST]] = []
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_aliases[alias.asname or alias.name.split('.')[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                import_aliases[alias.asname or alias.name] = f'{node.module}.{alias.name}'
        elif isinstance(node, ast.Call) and not _is_cast_call(node) and not _is_partial_call(node):
            calls.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name_assigns.append((target.id, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None and isinstance(node.target, ast.Name):
            name_assigns.append((node.target.id, node.value))
    local_aliases = _aliases_from_assignments(name_assigns, import_aliases)
    for node in calls:
        callee = _resolver_call_name(node.func, import_aliases, local_aliases)
        if callee != 'get_llm':
            continue
        arg = _feature_call_arg(node)
        if arg is None:
            continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            sites.add((rel, f'feature:{arg.value}'))
        else:
            sites.add((rel, 'feature:<dynamic>'))
    sites.update(_vendor_host_sites(rel, tree, import_aliases, local_aliases))
    return sites


def _vendor_host_sites(
    rel: str, tree: ast.AST, import_aliases: dict[str, str], local_aliases: dict[str, str]
) -> set[tuple[str, str]]:
    """REST host constants only where the string can plausibly reach a vendor.

    A bare ``ast.Constant`` walk flags every mention of a host anywhere in a
    file — docstrings, error messages, unrelated config URLs — which is not a
    call-site signal. A host counts when it is:

    - an argument of a call (a URL handed to httpx/requests/SDK/any function),
    - the right-hand side of an assignment (the file's named URL / base-URL
      constants that those calls read),
    - a concatenation/join of such constants (f-strings and ``+``/``%`` over
      host-bearing strings),
    - a function parameter default (``def __init__(base_url='https://…')``
      binds the host into the client), or
    - a returned value (URL builders like ``return f'https://host/{path}'``).

    A host assembled purely at runtime from non-constant parts still escapes
    this scan; that residual is accepted — same as SDK-less vendors that never
    name a host — because the cost of closing it (flagging every string) is
    false pins on non-call strings.
    """
    sites: set[tuple[str, str]] = set()
    read_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}

    def _hosts_in(node: ast.AST) -> set[str]:
        found: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                for host in LLM_REST_HOSTS:
                    if host in sub.value:
                        found.add(host)
        return found

    def _record(node: ast.AST) -> None:
        for host in _hosts_in(node):
            sites.add((rel, f'host:{host}'))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in [*node.args.defaults, *node.args.kw_defaults]:
                if default is not None:
                    _record(default)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if node.value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            name_targets = [target for target in targets if isinstance(target, ast.Name)]
            if not name_targets:
                continue
            if not any(target.id in read_names for target in name_targets):
                # A named constant that nothing in the file reads cannot reach
                # a vendor; it is a mention (docs/config), not a call site.
                continue
            _record(node.value)
        elif isinstance(node, ast.Call):
            callee_name = _dotted_name(node.func) or ''
            if callee_name.rsplit('.', 1)[-1].endswith(('Error', 'Exception', 'Warning')):
                # An exception message that mentions a host is documentation,
                # not a vendor call.
                continue
            for arg in [*node.args, *node.keywords]:
                value = arg.value if isinstance(arg, ast.keyword) else arg
                _record(value)
        elif isinstance(node, ast.Return) and node.value is not None:
            _record(node.value)
    return sites


def _is_skipped_path(rel: str) -> bool:
    return rel.startswith(
        (
            'tests/',
            'scripts/',
            'migrations/',
            'testing/',
            'pusher/',
            '.venv/',
            'venv/',
            '.openapi-venv/',
        )
    )


def _direct_provider_uses(rel: str, tree: ast.AST) -> set[DirectUse]:
    aliases = _import_aliases(tree)
    accessors = _provider_accessors(tree, aliases)
    uses: set[DirectUse] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _expanded_name(_dotted_name(node.func), aliases)
            matched = _direct_symbol(call_name)
            if matched is None:
                # ``_dotted_name`` drops the receiver when it is a call, so
                # ``_get_async_openai().chat.completions.create`` reads as the
                # unowned ``chat.completions.create``. Re-read it with the
                # accessor resolved to its provider root.
                through = _expanded_name(_dotted_name_through_accessors(node.func, accessors), aliases)
                matched = _direct_symbol(through)
            if matched is not None:
                uses.add(DirectUse(rel, matched))
            env_var = _provider_env_var_from_call(node)
            if env_var is not None:
                uses.add(DirectUse(rel, env_var))
    return uses


# Provider roots reachable through an accessor, derived from the constructor
# names above so the two cannot drift apart.
DIRECT_PROVIDER_ROOTS = {name.rsplit('.', 1)[0] for name in DIRECT_CONSTRUCTOR_NAMES}


def _provider_root(expanded: str | None) -> str | None:
    """The provider root a resolved name belongs to, if any."""
    if not expanded:
        return None
    if expanded in DIRECT_PROVIDER_ROOTS:
        return expanded
    for constructor in DIRECT_CONSTRUCTOR_NAMES:
        if expanded == constructor:
            return constructor.rsplit('.', 1)[0]
    return None


def _module_level_constructor_bindings(tree: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Module-level names bound to a direct-provider constructor call.

    ``_async_openai = AsyncOpenAI(...)`` anywhere in the module binds that name
    to the ``openai`` root, including the lazy-singleton form where the
    assignment lives inside the accessor under ``global``.
    """
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        root = _provider_root(_expanded_name(_dotted_name(value.func), aliases))
        if root is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                bound[target.id] = root
    return bound


def _provider_accessors(tree: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Module-level functions that hand back a provider module or SDK client.

    ``_get_sync_openai().chat.completions.create(...)`` is a direct provider
    call, but the receiver is a ``Call`` node, so a dotted-name walk bottoms
    out at ``None`` and the scanner sees nothing. Resolving the accessor to
    its provider root is what makes the indirection visible: a helper is not
    a boundary.

    An accessor resolves by its return annotation, or by returning an
    imported provider module, or by returning a name bound to a direct
    constructor call.
    """
    accessors: dict[str, str] = {}
    bound = _module_level_constructor_bindings(tree, aliases)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        root = _provider_root(_expanded_name(_dotted_name(node.returns), aliases)) if node.returns else None
        if root is None:
            for child in ast.walk(node):
                if not isinstance(child, ast.Return) or child.value is None:
                    continue
                returned = child.value
                if isinstance(returned, ast.Name) and returned.id in bound:
                    root = bound[returned.id]
                    break
                candidate = _expanded_name(_dotted_name(returned), aliases)
                root = _provider_root(candidate)
                if root is None and isinstance(returned, ast.Call):
                    root = _provider_root(_expanded_name(_dotted_name(returned.func), aliases))
                if root is not None:
                    break
        if root is not None:
            accessors[node.name] = root
    return accessors


def _dotted_name_through_accessors(node: ast.AST, accessors: dict[str, str]) -> str | None:
    """``_dotted_name`` that resolves a provider accessor call as its root."""
    if isinstance(node, ast.Call):
        callee = _dotted_name(node.func)
        if callee is not None:
            return accessors.get(callee.rsplit('.', 1)[-1])
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name_through_accessors(node.value, accessors)
        return f'{parent}.{node.attr}' if parent else None
    return None


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split('.')[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f'{node.module}.{alias.name}'
    return aliases


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f'{parent}.{node.attr}' if parent else node.attr
    return None


def _expanded_name(name: str | None, aliases: dict[str, str]) -> str | None:
    if name is None:
        return None
    head, _, tail = name.partition('.')
    expanded_head = aliases.get(head, head)
    return f'{expanded_head}.{tail}' if tail else expanded_head


def _direct_symbol(call_name: str | None) -> str | None:
    if call_name is None:
        return None
    for constructor in DIRECT_CONSTRUCTOR_NAMES:
        if call_name == constructor:
            return constructor.split('.')[-1]
    for prefix in DIRECT_PROVIDER_CALL_PREFIXES:
        if (
            call_name == prefix
            or call_name.startswith(f'{prefix}.')
            or call_name.endswith(f'.{prefix}')
            or f'.{prefix}.' in call_name
        ):
            return prefix
    return None


def _provider_env_var_from_call(node: ast.Call) -> str | None:
    call_name = _dotted_name(node.func)
    if call_name not in {'os.getenv', 'os.environ.get'}:
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    value = node.args[0].value
    return value if isinstance(value, str) and value in DIRECT_PROVIDER_ENV_VARS else None


def _inventory_file_exists(code_path: str) -> bool:
    rel = _code_path_file(code_path)
    return bool(rel) and (BACKEND_DIR / rel).exists()


def _code_path_file(code_path: str) -> str:
    normalized = code_path.removeprefix('backend/')
    return normalized.split(':', 1)[0]


def _direct_exception_policy(migration_status: str) -> str:
    if migration_status.startswith('acknowledged_direct_'):
        return 'acknowledged'
    if 'blocked during OMI_LLM_GATEWAY_FEATURE_MODE=gateway' in migration_status:
        return 'blocked'
    raise AssertionError(f'direct exception surface has no declared gateway policy: {migration_status!r}')


def _iter_backend_py_files():
    for dirpath, dirnames, filenames in os.walk(BACKEND_DIR):
        dirnames[:] = [d for d in dirnames if d not in _FEATURE_SCAN_SKIP_DIRS]
        for name in filenames:
            if name.endswith('.py'):
                yield Path(dirpath) / name


def _unwrap_cast(node: ast.AST) -> ast.AST:
    current = node
    for _ in range(4):
        if not isinstance(current, ast.Call) or not _is_cast_call(current) or len(current.args) < 2:
            return current
        current = current.args[1]
    return current


def _call_basename(func: ast.AST) -> str | None:
    dotted = _dotted_name(func)
    if dotted is None:
        return None
    return dotted.rsplit('.', 1)[-1]


def _is_cast_call(node: ast.Call) -> bool:
    return _call_basename(node.func) == 'cast'


def _is_partial_call(node: ast.Call) -> bool:
    return _call_basename(node.func) == 'partial'


def _resolver_basename_from_value(
    node: ast.AST, import_aliases: dict[str, str], local_aliases: dict[str, str]
) -> str | None:
    node = _unwrap_cast(node)
    dotted = _dotted_name(node)
    if dotted is None:
        return None
    if dotted in local_aliases:
        return local_aliases[dotted]
    head, _, tail = dotted.partition('.')
    if not tail and head in local_aliases:
        return local_aliases[head]
    expanded = _expanded_name(dotted, import_aliases)
    if expanded is None:
        return None
    basename = expanded.rsplit('.', 1)[-1]
    return basename if basename in _RESOLVER_CALL_NAMES else None


def _aliases_from_assignments(
    name_assigns: list[tuple[str, ast.AST]], import_aliases: dict[str, str]
) -> dict[str, str]:
    local: dict[str, str] = {}
    for _ in range(4):
        grew = False
        for target, value in name_assigns:
            if target in local:
                continue
            basename = _resolver_basename_from_value(value, import_aliases, local)
            if basename is not None:
                local[target] = basename
                grew = True
        if not grew:
            break
    return local


def _resolver_call_name(func: ast.AST, import_aliases: dict[str, str], local_aliases: dict[str, str]) -> str | None:
    return _resolver_basename_from_value(func, import_aliases, local_aliases)


def _feature_call_arg(node: ast.Call) -> ast.AST | None:
    if node.args:
        return node.args[0]
    for keyword in node.keywords:
        if keyword.arg == 'feature':
            return keyword.value
    return None

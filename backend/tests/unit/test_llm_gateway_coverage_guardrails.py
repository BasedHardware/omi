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
        ('utils/llm/clients.py', '_get_model_config', 'f'),
        ('utils/screen_frames/judge.py', 'get_llm', 'model_feature'),
        ('utils/managed_compute.py', 'get_provider', 'feature'),
    }
)
_FEATURE_SCAN_SKIP_DIRS = {'.venv', 'venv', '.openapi-venv', '__pycache__', 'tests'}
_SNIPPET_CONFIGURED = {'chat_agent', 'memory_l1', 'conv_structure', 'what_matters_now'}


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
    for surface in inventory['surfaces']:
        assert surface['surface']
        assert surface['code_path']
        assert surface['current_provider_model']
        assert surface['request_shape']
        assert surface['gateway_lane_capability_needed']
        assert surface['migration_status']
        assert surface['test_guardrail_coverage']
        assert _inventory_file_exists(surface['code_path']), surface['code_path']


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

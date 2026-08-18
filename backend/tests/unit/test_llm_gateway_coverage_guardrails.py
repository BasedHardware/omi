from __future__ import annotations

import ast
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
    DirectUse('routers/desktop_proxy.py', 'GEMINI_API_KEY'),
    DirectUse('routers/desktop_realtime.py', 'GEMINI_API_KEY'),
    DirectUse('routers/desktop_realtime.py', 'OPENAI_API_KEY'),
    DirectUse('routers/desktop_tts_updates.py', 'OPENAI_API_KEY'),
    DirectUse('utils/llm/providers.py', 'ChatGoogleGenerativeAI'),
    DirectUse('utils/llm/providers.py', 'ChatOpenAI'),
    DirectUse('utils/llm/providers.py', 'GEMINI_API_KEY'),
    DirectUse('utils/llm/clients.py', 'AsyncAnthropic'),
    DirectUse('utils/llm/gateway_anthropic.py', 'AsyncAnthropic'),
    DirectUse('utils/llm/clients.py', 'ChatOpenAI'),
    DirectUse('utils/llm/clients.py', 'GEMINI_API_KEY'),
    DirectUse('utils/llm/clients.py', 'OpenAIEmbeddings'),
    DirectUse('utils/memory_ingestion/export_runner.py', 'OPENAI_API_KEY'),
    DirectUse('utils/other/chat_file.py', 'AsyncOpenAI'),
    DirectUse('utils/other/chat_file.py', 'openai.beta'),
    DirectUse('utils/other/chat_file.py', 'openai.files'),
    DirectUse('utils/retrieval/agentic.py', 'anthropic_client.messages'),
    DirectUse('routers/omni_relay.py', 'GEMINI_API_KEY'),
    DirectUse('routers/omni_relay.py', 'OPENAI_API_KEY'),
}
INVENTORIED_DIRECT_EXCEPTION_FILES = {
    'routers/desktop_proactivity.py',
    'utils/other/chat_file.py',
    'routers/omni_relay.py',
}


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
    assert inventory['out_of_scope_surfaces']
    for surface in inventory['surfaces']:
        assert surface['surface']
        assert surface['code_path']
        assert surface['current_provider_model']
        assert surface['request_shape']
        assert surface['gateway_lane_capability_needed']
        assert surface['migration_status']
        assert surface['test_guardrail_coverage']
        assert _inventory_file_exists(surface['code_path']), surface['code_path']


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
    assert policy_by_file['utils/other/chat_file.py'] == 'acknowledged'
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


def test_acknowledged_file_chat_surface_is_observed_without_a_gateway_block():
    """Static regression guard for PR #11419's acknowledged file-chat direct surface.

    Behavioral upload coverage lives in test_chat_file_gateway_surface.py; this tripwire
    keeps the acknowledged implementation from regressing to the fail-closed gate.
    """
    source = (BACKEND_DIR / 'utils/other/chat_file.py').read_text(encoding='utf-8')

    assert 'record_direct_exception_surface(surface=\'file_chat.openai_files_assistants_vision\')' in source
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
    uses: set[DirectUse] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _expanded_name(_dotted_name(node.func), aliases)
            matched = _direct_symbol(call_name)
            if matched is not None:
                uses.add(DirectUse(rel, matched))
            env_var = _provider_env_var_from_call(node)
            if env_var is not None:
                uses.add(DirectUse(rel, env_var))
    return uses


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

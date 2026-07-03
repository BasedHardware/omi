from __future__ import annotations

import ast
from pathlib import Path

import yaml

from llm_gateway.gateway.config_loader import feature_lane_id, load_gateway_config
from utils.llm.model_config import get_all_configured_features

BACKEND_DIR = Path(__file__).resolve().parents[2]
INVENTORY_PATH = BACKEND_DIR / 'docs' / 'llm' / 'model_endpoint_inventory.yaml'

DIRECT_PROVIDER_PATTERNS = {
    ('openai', 'OpenAI'),
    ('openai', 'AsyncOpenAI'),
    ('anthropic', 'AsyncAnthropic'),
    ('langchain_openai', 'ChatOpenAI'),
    ('langchain_google_genai', 'ChatGoogleGenerativeAI'),
}

DIRECT_CALL_ALLOWLIST = {
    # Gateway/client construction boundary.
    'llm_gateway/gateway/providers.py',
    'utils/llm/providers.py',
    'utils/llm/clients.py',
    # Explicitly out-of-scope embeddings and memory-ingestion tests patch this seam.
    'utils/memory_ingestion/adapters/production_like_model.py',
    # Inventoried direct provider lifecycle surfaces that cannot be silently missed.
    'utils/other/chat_file.py',
    'routers/omni_relay.py',
    'utils/retrieval/agentic.py',
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


def test_inventory_surfaces_have_status_and_guardrails():
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


def test_direct_provider_construction_stays_inside_approved_boundaries():
    violations: list[str] = []
    for path in BACKEND_DIR.rglob('*.py'):
        rel = path.relative_to(BACKEND_DIR).as_posix()
        if _is_skipped_path(rel):
            continue
        if rel in DIRECT_CALL_ALLOWLIST:
            continue
        source = path.read_text(encoding='utf-8')
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        imported_names = _direct_provider_imports(tree)
        if not imported_names:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in imported_names:
                violations.append(f'{rel}:{node.lineno} constructs {node.func.id}')

    assert violations == []


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
        )
    )


def _direct_provider_imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        for module_name, class_name in DIRECT_PROVIDER_PATTERNS:
            if node.module == module_name:
                for alias in node.names:
                    if alias.name == class_name:
                        names.add(alias.asname or alias.name)
    return names

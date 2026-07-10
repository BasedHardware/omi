"""Load and validate checked-in task-intelligence contract artifacts."""

import ast
import json
import re
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from utils.task_intelligence.fixture_runner import TEST_ADAPTERS

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent
CONTRACT_MANIFEST_PATH = BACKEND_ROOT / 'config' / 'task_intelligence_contract_v1.json'
SOURCE_MANIFEST_PATH = BACKEND_ROOT / 'config' / 'task_intelligence_sources_v1.json'
FIXTURE_ROOT = BACKEND_ROOT / 'tests' / 'unit' / 'fixtures' / 'task_intelligence'

REQUIRED_CONTRACT_DOMAINS = {
    'task',
    'candidate',
    'goal',
    'workstream',
    'workstream_event',
    'evidence_ref',
    'feedback',
    'recommendation',
    'decision_record',
    'kernel_workstream_bridge',
    'attribution_event',
}
REQUIRED_SOURCE_IDS = {
    'mobile_manual',
    'desktop_manual',
    'chat_voice_tools',
    'mcp_tools',
    'developer_api',
    'backend_conversation_extraction',
    'desktop_screen_extraction',
    'sharing_imports',
    'recurrence',
    'integrations',
    'goal_manual_api',
    'goal_ai_progress',
    'legacy_staged_promotion',
}
ALLOWED_POLICY_CLASSES = {'direct_command', 'shared_capture_policy', 'compatibility_migration'}
BACKEND_WRITER_METHODS = {
    'action_items_db': {
        'create_action_item',
        'create_action_items_batch',
        'delete_action_item',
        'delete_action_items_batch',
        'delete_action_items_for_conversation',
        'mark_action_item_completed',
        'update_action_item',
    },
    'goals_db': {'create_goal', 'delete_goal', 'update_goal', 'update_goal_progress'},
}
CLIENT_WRITER_METHODS = {
    'createActionItem',
    'updateActionItem',
    'deleteActionItem',
    'markActionItemCompleted',
    'createTask',
    'updateTask',
    'deleteTask',
    'createGoal',
    'updateGoal',
    'deleteGoal',
    'updateGoalProgress',
}
CLIENT_CALL_PATTERN = re.compile(r'\.\s*(' + '|'.join(sorted(CLIENT_WRITER_METHODS)) + r')\s*\(')


def _read_json(path: Path) -> object:
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def load_contract_manifest(path: Path = CONTRACT_MANIFEST_PATH) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError('contract manifest must be an object')
    return cast(dict[str, Any], payload)


def load_source_manifest(path: Path = SOURCE_MANIFEST_PATH) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError('source manifest must be an object')
    return cast(dict[str, Any], payload)


def load_fixture(name: str) -> dict[str, Any]:
    if not name or '/' in name or '\\' in name:
        raise ValueError('fixture name must be a simple filename')
    payload = _read_json(FIXTURE_ROOT / name)
    if not isinstance(payload, dict):
        raise ValueError('fixture must be an object')
    return cast(dict[str, Any], payload)


def validate_contract_manifest(payload: dict[str, Any]) -> None:
    if payload.get('schema_version') != 1:
        raise ValueError('unsupported task-intelligence contract schema')
    definitions = payload.get('$defs')
    owners = payload.get('domain_owners')
    examples = payload.get('examples')
    if not isinstance(definitions, dict) or not isinstance(owners, dict) or not isinstance(examples, dict):
        raise ValueError('contract definitions, owners, and examples must be objects')
    missing = REQUIRED_CONTRACT_DOMAINS - set(definitions)
    if missing:
        raise ValueError(f'missing contract domains: {sorted(missing)}')
    if set(owners) != REQUIRED_CONTRACT_DOMAINS or set(examples) != REQUIRED_CONTRACT_DOMAINS:
        raise ValueError('contract owners and examples must exactly match required domains')
    if not isinstance(payload.get('compatibility_policy'), dict):
        raise ValueError('contract compatibility policy is required')

    root_schema = {'$schema': payload.get('$schema'), '$defs': definitions}
    Draft202012Validator.check_schema(root_schema)
    format_checker = FormatChecker()
    for name in sorted(REQUIRED_CONTRACT_DOMAINS):
        if not isinstance(owners[name], str) or not owners[name]:
            raise ValueError(f'invalid contract owner: {name}')
        domain_examples = examples[name]
        if not isinstance(domain_examples, list) or not domain_examples:
            raise ValueError(f'contract domain requires examples: {name}')
        validator = Draft202012Validator(
            {'$schema': payload.get('$schema'), '$defs': definitions, '$ref': f'#/$defs/{name}'},
            format_checker=format_checker,
        )
        for example in domain_examples:
            errors = sorted(validator.iter_errors(example), key=lambda error: list(error.path))
            if errors:
                raise ValueError(f'invalid {name} example: {errors[0].message}')


def _python_writer_anchors(path: Path, *, repository_root: Path) -> set[tuple[str, str]]:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ValueError(f'cannot inspect writer source {path}: {exc}') from exc

    module_aliases: dict[str, str] = {}
    direct_aliases: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == 'database':
                for alias in node.names:
                    canonical_module = f'{alias.name}_db'
                    if canonical_module in BACKEND_WRITER_METHODS:
                        module_aliases[alias.asname or alias.name] = canonical_module
            elif node.module in {'database.action_items', 'database.goals'}:
                module_name = f'{node.module.rsplit(".", 1)[1]}_db'
                for alias in node.names:
                    if alias.name in BACKEND_WRITER_METHODS[module_name]:
                        direct_aliases[alias.asname or alias.name] = (module_name, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {'database.action_items', 'database.goals'}:
                    module_name = f'{alias.name.rsplit(".", 1)[1]}_db'
                    module_aliases[alias.asname or module_name] = module_name

    relative_path = path.relative_to(repository_root).as_posix()
    discovered: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            module_name = module_aliases.get(node.value.id)
            if module_name and node.attr in BACKEND_WRITER_METHODS[module_name]:
                discovered.add((relative_path, f'{module_name}.{node.attr}'))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in direct_aliases:
            module_name, method = direct_aliases[node.id]
            discovered.add((relative_path, f'{module_name}.{method}'))
    return discovered


def discover_backend_writer_anchors(*, repository_root: Path = REPOSITORY_ROOT) -> set[tuple[str, str]]:
    """Discover task/goal mutation call sites across backend, Swift, and Dart."""

    discovered: set[tuple[str, str]] = set()
    backend_root = repository_root / 'backend'
    if backend_root.exists():
        for path in backend_root.rglob('*.py'):
            relative_parts = path.relative_to(backend_root).parts
            if (
                '__pycache__' in path.parts
                or 'tests' in path.parts
                or 'testing' in path.parts
                or any(part.startswith('.') for part in relative_parts)
            ):
                continue
            if path.name in {'action_items.py', 'goals.py'} and path.parent.name == 'database':
                continue
            discovered.update(_python_writer_anchors(path, repository_root=repository_root))

    for relative_root, suffix in (
        ('desktop/macos/Desktop/Sources', '*.swift'),
        ('app/lib', '*.dart'),
    ):
        root = repository_root / relative_root
        if not root.exists():
            continue
        for path in root.rglob(suffix):
            try:
                source = path.read_text(encoding='utf-8')
            except OSError as exc:
                raise ValueError(f'cannot inspect writer source {path}: {exc}') from exc
            relative_path = path.relative_to(repository_root).as_posix()
            for line in source.splitlines():
                code = line.split('//', 1)[0]
                for match in CLIENT_CALL_PATTERN.finditer(code):
                    discovered.add((relative_path, f'client.{match.group(1)}'))
    return discovered


def _registered_discoverable_anchors(sources: list[dict[str, Any]]) -> set[tuple[str, str]]:
    registered: set[tuple[str, str]] = set()
    for source in sources:
        anchors = source.get('writer_anchors', [])
        if not isinstance(anchors, list):
            raise ValueError(f'source {source.get("id")} writer_anchors must be a list')
        for anchor in anchors:
            if not isinstance(anchor, dict):
                raise ValueError(f'source {source.get("id")} has invalid writer anchor')
            if anchor.get('discover') is True:
                path = anchor.get('path')
                symbol = anchor.get('symbol')
                if not isinstance(path, str) or not isinstance(symbol, str):
                    raise ValueError(f'source {source.get("id")} has incomplete writer anchor')
                registered.add((path, symbol))
    return registered


def validate_source_manifest(
    payload: dict[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    discovered_anchors: set[tuple[str, str]] | None = None,
) -> None:
    if payload.get('schema_version') != 1:
        raise ValueError('unsupported task-intelligence source schema')
    sources = payload.get('sources')
    if not isinstance(sources, list):
        raise ValueError('sources must be a list')
    typed_sources: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('source entries must be objects')
        typed_sources.append(cast(dict[str, Any], source))
    by_id: dict[str, dict[str, Any]] = {}
    for source in typed_sources:
        if not isinstance(source.get('id'), str):
            raise ValueError('source entry requires an id')
        source_id = source['id']
        if source_id in by_id:
            raise ValueError(f'duplicate source id: {source_id}')
        if source.get('policy_class') not in ALLOWED_POLICY_CLASSES:
            raise ValueError(f'invalid policy class for {source_id}')
        owner_paths = source.get('owner_paths')
        if not isinstance(owner_paths, list) or not owner_paths:
            raise ValueError(f'source {source_id} requires owner paths')
        for owner_path in owner_paths:
            if not isinstance(owner_path, str) or not (repository_root / owner_path).exists():
                raise ValueError(f'source {source_id} has missing owner path: {owner_path}')
        test_adapter = source.get('test_adapter')
        if not isinstance(test_adapter, str) or not callable(TEST_ADAPTERS.get(test_adapter)):
            raise ValueError(f'source {source_id} requires a resolvable test adapter')
        by_id[source_id] = source
    missing = REQUIRED_SOURCE_IDS - set(by_id)
    if missing:
        raise ValueError(f'missing source registrations: {sorted(missing)}')

    discovered = (
        discover_backend_writer_anchors(repository_root=repository_root)
        if discovered_anchors is None
        else discovered_anchors
    )
    registered_owner_paths = {
        owner_path for source in typed_sources for owner_path in source['owner_paths'] if isinstance(owner_path, str)
    }
    unowned = {anchor for anchor in discovered if anchor[0] not in registered_owner_paths}
    if unowned:
        raise ValueError(f'unregistered writer anchors: {sorted(unowned)}')

    registered = _registered_discoverable_anchors(typed_sources)
    stale = registered - discovered
    if stale:
        raise ValueError(f'stale writer anchors: {sorted(stale)}')


__all__ = [
    'CONTRACT_MANIFEST_PATH',
    'FIXTURE_ROOT',
    'REPOSITORY_ROOT',
    'SOURCE_MANIFEST_PATH',
    'discover_backend_writer_anchors',
    'load_contract_manifest',
    'load_fixture',
    'load_source_manifest',
    'validate_contract_manifest',
    'validate_source_manifest',
]

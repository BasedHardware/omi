#!/usr/bin/env python3
"""Select backend unit tests for either a full run or a changed-file PR run."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple, cast

import argparse
import fnmatch
import json
from pathlib import Path
from pathlib import PurePosixPath

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
WORKFLOW_CONTRACTS_PATH = BACKEND_DIR / 'testing' / 'workflow_contracts.json'

FULL_TEST_ROOTS = (
    BACKEND_DIR / 'tests' / 'unit',
    BACKEND_DIR / 'tests' / 'services',
    BACKEND_DIR / 'tests' / 'routers',
)
FULL_TEST_GLOBS = (BACKEND_DIR / 'tests',)

# Hermetic e2e tests selected by workflow contracts / memory policy core — not part of --all.
EXTRA_DISCOVERABLE_TESTS = (BACKEND_DIR / 'testing' / 'e2e' / 'test_canonical_memory_pipeline.py',)

LEGACY_UNLISTED_TESTS = {
    'tests/test_cache_manager.py',
    'tests/unit/test_diarizer_dockerfile.py',
    'tests/unit/test_lazy_conversation_processing.py',
}

FULL_RUN_PATHS = (
    '.github/workflows/backend-unit-tests.yml',
    'backend/pylock.toml',
    'backend/pylock.macos.toml',
    'backend/pylock.macos-x86_64.toml',
    'backend/pylock.runtime.toml',
    'backend/pylock.windows.toml',
    'backend/pyproject.toml',
    'backend/requirements.txt',
    'backend/test-preflight.sh',
    'backend/test.sh',
    'backend/tests/conftest.py',
    'backend/tests/unit/conftest.py',
    'backend/scripts/select_backend_unit_tests.py',
)

FULL_RUN_PREFIXES = (
    'backend/database/',
    'backend/models/',
    'backend/testing/',
)

# Explicit cross-cutting paths only. Do not use `backend/*` or
# `backend/utils/*.py` — those force the full suite for docs/AGENTS edits and
# every flat utils module before AREA_TESTS can narrow.
FULL_RUN_GLOBS = (
    'backend/main.py',
    'backend/dependencies.py',
    'backend/scripts/update-python-lock.sh',
    'backend/scripts/sync-python-deps.sh',
    'backend/utils/executors.py',
    'backend/utils/log_sanitizer.py',
    'backend/utils/http_client.py',
    'backend/utils/async_tasks.py',
    'backend/utils/encryption.py',
)

MEMORY_POLICY_CORE_PATH_PREFIXES = ('backend/utils/memory/',)

MEMORY_POLICY_CORE_PATH_GLOBS = (
    'backend/database/memory_*.py',
    'backend/models/product_memory.py',
    'backend/models/memory_search_gateway.py',
    'backend/routers/memory_*.py',
    'backend/routers/memories.py',
)

MEMORY_POLICY_CORE_TESTS = (
    'tests/unit/test_inv_mem_1_guard.py',
    'testing/e2e/test_canonical_memory_pipeline.py',
)

AREA_TESTS = (
    (
        ('backend/llm_gateway/',),
        (),
        ('tests/unit/test_llm_gateway_*.py',),
    ),
    (
        ('backend/mcp/', 'backend/routers/mcp'),
        (),
        ('tests/unit/test_mcp_*.py', 'tests/unit/test_oauth_callback_uid_guard.py'),
    ),
    (
        (
            'backend/utils/stt/',
            'backend/config/prerecorded_stt',
            'backend/pusher/',
            'backend/routers/transcribe',
            'backend/routers/listen',
        ),
        (),
        (
            'tests/unit/test_*audio*.py',
            'tests/unit/test_*listen*.py',
            'tests/unit/test_parakeet_*.py',
            'tests/unit/test_*pusher*.py',
            'tests/unit/test_*speaker*.py',
            'tests/unit/test_*speech*.py',
            'tests/unit/test_*stt*.py',
            'tests/unit/test_*streaming*.py',
            'tests/unit/test_*sync*.py',
            'tests/unit/test_*transcribe*.py',
            'tests/unit/test_*vad*.py',
            'tests/unit/utils/test_listen_pusher_session.py',
        ),
    ),
    (
        ('backend/parakeet/',),
        (),
        ('tests/unit/test_parakeet_*.py',),
    ),
    (
        ('backend/services/users/', 'backend/routers/users'),
        (),
        (
            'tests/services/users/test_*.py',
            'tests/routers/test_users.py',
            'tests/unit/test_users_*.py',
            'tests/unit/test_delete_account_*.py',
            'tests/unit/test_claim_deletion_*.py',
        ),
    ),
    (
        ('backend/routers/conversations', 'backend/services/conversations/', 'backend/utils/conversations'),
        (),
        (
            'tests/unit/test_conversation*.py',
            'tests/unit/test_conversations*.py',
            'tests/unit/test_folder_*.py',
            'tests/unit/test_retrieval_*.py',
        ),
    ),
    (
        ('backend/routers/memories', 'backend/services/memories/', 'backend/utils/memories'),
        (),
        ('tests/unit/test_memories_*.py', 'tests/unit/test_memory_*.py'),
    ),
    (
        ('backend/routers/action_items', 'backend/services/action_items/', 'backend/utils/action_items'),
        (),
        ('tests/unit/test_action_item*.py', 'tests/unit/test_dev_api_action_items_poison.py'),
    ),
    (
        ('backend/routers/payment', 'backend/services/payment/', 'backend/utils/payments'),
        (),
        (
            'tests/unit/test_payment_*.py',
            'tests/unit/test_stripe_*.py',
            'tests/unit/test_subscription_*.py',
            'tests/unit/test_available_plans_resilience.py',
            'tests/unit/test_trial_metadata.py',
            'tests/unit/test_paywall_reconnect_gate.py',
            'tests/unit/test_chat_quota.py',
        ),
    ),
    (
        ('backend/routers/apps', 'backend/services/apps/', 'backend/utils/apps'),
        (),
        ('tests/unit/test_apps_*.py', 'tests/unit/test_app_*.py', 'tests/unit/test_create_persona_user_none.py'),
    ),
    (
        ('backend/routers/folders', 'backend/services/folders/', 'backend/utils/folders'),
        (),
        ('tests/unit/test_folder_*.py',),
    ),
    (
        ('backend/routers/developer', 'backend/services/developer/', 'backend/utils/developer'),
        (),
        ('tests/unit/test_dev_api_*.py', 'tests/unit/test_developer_*.py'),
    ),
    (
        ('backend/routers/sync', 'backend/services/sync/', 'backend/utils/sync'),
        (),
        ('tests/unit/test_sync_*.py', 'tests/unit/test_audio_merge_tasks.py'),
    ),
    (
        ('backend/routers/storage', 'backend/services/storage/', 'backend/utils/storage'),
        (),
        ('tests/unit/test_storage_*.py', 'tests/unit/test_file_upload*.py'),
    ),
    (
        ('backend/routers/notifications', 'backend/services/notifications/', 'backend/utils/notifications'),
        (),
        ('tests/unit/test_*notification*.py', 'tests/unit/test_mentor_notifications.py'),
    ),
    (
        ('backend/routers/twilio', 'backend/services/twilio/', 'backend/utils/twilio'),
        (),
        ('tests/unit/test_twilio_*.py', 'tests/unit/test_phone_*.py'),
    ),
    (
        ('backend/routers/geocoding', 'backend/services/geocoding/', 'backend/utils/geocoding'),
        (),
        ('tests/unit/test_*geocoding*.py', 'tests/unit/test_location_maps_status_guard.py'),
    ),
    (
        ('backend/routers/rate', 'backend/services/rate', 'backend/utils/rate'),
        (),
        ('tests/unit/test_rate_*.py',),
    ),
)


def discover_unit_tests() -> list[str]:
    tests: set[Path] = set()
    for root in FULL_TEST_ROOTS:
        tests.update(root.rglob('test_*.py'))
    for root in FULL_TEST_GLOBS:
        tests.update(root.glob('test_*.py'))
    return sorted(
        test_path
        for test_path in (_backend_relative(path) for path in tests if path.is_file())
        if test_path not in LEGACY_UNLISTED_TESTS
    )


def discover_all_tests() -> list[str]:
    """Unit tests plus workflow-contract extras (e2e) for PR path selection only."""
    tests = {Path(BACKEND_DIR / path) for path in discover_unit_tests()}
    for path in EXTRA_DISCOVERABLE_TESTS:
        if path.is_file():
            tests.add(path)
    return sorted(_backend_relative(path) for path in tests if path.is_file())


def _backend_relative(path: Path) -> str:
    return path.relative_to(BACKEND_DIR).as_posix()


def normalize_changed_path(path: str) -> str:
    path = path.strip()
    if not path:
        return ''
    path = path.replace('\\', '/')
    while path.startswith('./'):
        path = path[2:]
    return path


def is_full_run_path(path: str) -> bool:
    if path in FULL_RUN_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in FULL_RUN_PREFIXES):
        return True
    return any(path_matches(path, pattern) for pattern in FULL_RUN_GLOBS)


def is_selectable_backend_path(path: str) -> bool:
    """Return True for backend paths that can select or force unit tests.

    Docs, AGENTS, and chart/dashboard artifacts are ignored so editing them
    does not trip the unmapped-path full-suite fallback.
    """
    if not path.startswith('backend/'):
        return False
    if path.endswith('.md'):
        return False
    if path.startswith('backend/docs/') or path.startswith('backend/charts/'):
        return False
    return True


def path_matches(path: str, pattern: str) -> bool:
    if pattern.endswith('/**'):
        return path.startswith(pattern[:-3].rstrip('/') + '/')
    return PurePosixPath(path).match(pattern)


def is_memory_policy_core_path(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in MEMORY_POLICY_CORE_PATH_PREFIXES):
        return True
    return any(path_matches(path, pattern) for pattern in MEMORY_POLICY_CORE_PATH_GLOBS)


def load_workflow_contracts() -> List[Dict[str, Any]]:
    if not WORKFLOW_CONTRACTS_PATH.exists():
        return []
    data: object = json.loads(WORKFLOW_CONTRACTS_PATH.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        return []
    typed_data: Dict[str, Any] = cast(Dict[str, Any], data)
    workflows_raw: Any = typed_data.get('workflows', [])
    return cast(List[Dict[str, Any]], workflows_raw) if isinstance(workflows_raw, list) else []


def workflow_contract_tests_for_path(path: str, all_tests: List[str]) -> Set[str]:
    selected: Set[str] = set()
    for workflow in load_workflow_contracts():
        sources: Tuple[str, ...] = tuple(workflow.get('sources') or ())
        if not any(path_matches(path, source) for source in sources):
            continue
        tests_raw = workflow.get('tests') or ()
        selected.update(test for test in tests_raw if test in all_tests)
    return selected


def workflow_contract_matches_path(path: str) -> bool:
    for workflow in load_workflow_contracts():
        sources: Tuple[str, ...] = tuple(workflow.get('sources') or ())
        if any(path_matches(path, source) for source in sources):
            return True
    return False


def tests_for_changed_paths(changed_paths: list[str], all_tests: list[str]) -> tuple[list[str], str]:
    changed_paths = [path for path in (normalize_changed_path(path) for path in changed_paths) if path]
    if not changed_paths:
        return all_tests, 'no changed paths were provided'

    selected: set[str] = set()
    backend_paths = [path for path in changed_paths if is_selectable_backend_path(path)]
    test_paths = [path for path in backend_paths if path.startswith('backend/tests/') and path.endswith('.py')]

    for path in changed_paths:
        selected.update(workflow_contract_tests_for_path(path, all_tests))

    for path in backend_paths:
        if is_full_run_path(path):
            return all_tests, f'{path} requires the full backend unit suite'

    for path in test_paths:
        backend_relative = path.removeprefix('backend/')
        if backend_relative in all_tests:
            selected.add(backend_relative)

    removed_or_unlisted_tests = [path for path in test_paths if path.removeprefix('backend/') not in all_tests]
    if removed_or_unlisted_tests:
        return all_tests, f'{removed_or_unlisted_tests[0]} was removed or is outside backend test discovery'

    mapped_backend_sources: set[str] = set()
    for path in backend_paths:
        if path in test_paths:
            continue
        if workflow_contract_matches_path(path):
            mapped_backend_sources.add(path)
        for source_prefixes, source_globs, test_globs in AREA_TESTS:
            if any(path.startswith(prefix) for prefix in source_prefixes) or any(
                path_matches(path, pattern) for pattern in source_globs
            ):
                mapped_backend_sources.add(path)
                selected.update(match_tests(all_tests, test_globs))

    if any(is_memory_policy_core_path(path) for path in backend_paths):
        mapped_backend_sources.update(path for path in backend_paths if is_memory_policy_core_path(path))
        selected.update(test for test in MEMORY_POLICY_CORE_TESTS if test in all_tests)

    unmapped_backend_sources = [
        path for path in backend_paths if path not in test_paths and path not in mapped_backend_sources
    ]
    if unmapped_backend_sources:
        return all_tests, f'{unmapped_backend_sources[0]} did not match a backend test-selection contract'

    if not backend_paths:
        if selected:
            return sorted(selected), 'selected backend unit tests from changed paths and workflow contracts'
        return [], 'no backend files changed'
    if selected:
        return sorted(selected), 'selected backend unit tests from changed paths and workflow contracts'
    return all_tests, 'backend changes did not match a narrow area'


def match_tests(all_tests: list[str], test_globs: tuple[str, ...]) -> set[str]:
    return {test for test in all_tests if any(fnmatch.fnmatch(test, pattern) for pattern in test_globs)}


def read_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def existing_tests(paths: list[str], all_tests: list[str]) -> list[str]:
    all_test_set = set(all_tests)
    missing = [path for path in paths if path not in all_test_set]
    if missing:
        missing_list = ', '.join(missing)
        raise SystemExit(f'Selected backend unit tests do not exist: {missing_list}')
    return sorted(dict.fromkeys(paths))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--all', action='store_true', help='print every backend unit test file')
    mode.add_argument('--changed-files', type=Path, help='file containing repo-relative changed paths')
    mode.add_argument('--from-test-list', type=Path, help='file containing backend-relative test paths')
    parser.add_argument('--output', type=Path, help='write selected tests to this file instead of stdout')
    parser.add_argument('--reason-output', type=Path, help='write the selection reason to this file')
    args = parser.parse_args()

    all_tests = discover_all_tests()
    reason = 'full backend unit suite'
    if args.all:
        selected = discover_unit_tests()
    elif args.from_test_list:
        selected = existing_tests(read_lines(args.from_test_list), all_tests)
        reason = 'using provided backend unit test list'
    else:
        selected, reason = tests_for_changed_paths(read_lines(args.changed_files), all_tests)

    output = '\n'.join(selected)
    if output:
        output += '\n'
    if args.output:
        args.output.write_text(output, encoding='utf-8', newline='\n')
    else:
        print(output, end='')
    if args.reason_output:
        args.reason_output.write_text(reason + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

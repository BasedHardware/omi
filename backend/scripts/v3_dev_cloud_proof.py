"""Dev-cloud proof helpers for memory ``/v3`` readiness scripts and tests."""

# LIFECYCLE: one-time
# DELETE-AFTER: INV-MEM-3

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from config.memory_rollout import MemoryRolloutMode
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import DEFAULT_READ_ROLLOUT_SCHEMA_VERSION
from utils.memory.v3.limited_rollout_config import GLOBAL_READ_GATE_PATH, WRITE_CONVERGENCE_GATE_PATH

GATE_STATUS_BLOCKED = 'BLOCKED'
GATE_STATUS_READY_TO_EXECUTE = 'READY_TO_EXECUTE_DEV_CLOUD_PROOF'
GATE_STATUS_NOT_RUN = 'NOT_RUN'
ROUTE_SCOPE = 'get_v3_memories'
DEV_FIXTURE_SOURCE = 'v3_dev_cloud_synthetic_fixture'

REQUIRED_ARTIFACTS = (
    'candidate-manifest.json',
    'target-preflight.json',
    'deployment.json',
    'indexes-source.json',
    'indexes-status.json',
    'iam-effective.json',
    'auth-evidence.json',
    'fixtures.redacted.json',
    'proof-results.json',
    'junit.xml',
    'http-transcripts.redacted.ndjson',
    'memory-operations.ndjson',
    'audit-extract.ndjson',
    'telemetry-redaction-report.json',
    'rollback-report.json',
    'cleanup-report.json',
    'checksums.sha256',
    'review.md',
)

PROOF_MATRIX = (
    {
        'id': 'feature_variable_absent_false_or_non_exact',
        'required_result': 'memory not selected; zero memory adapter calls; existing legacy/off contract unchanged.',
    },
    {'id': 'memory_mode_not_exact_read', 'required_result': 'memory not selected; zero memory adapter calls.'},
    {'id': 'authenticated_uid_not_allowlisted', 'required_result': 'memory not selected; no memory Firestore calls.'},
    {
        'id': 'valid_allowlisted_user',
        'required_result': 'Exact synthetic memories, ordering, pagination, generation, and headers match API contract.',
    },
    {
        'id': 'client_uid_query_body_mode_header_spoof',
        'required_result': 'No effect on authenticated UID or route selection.',
    },
    {
        'id': 'user_a_references_user_b',
        'required_result': 'No B data returned through query, header, path, or cursor.',
    },
    {'id': 'global_gate_absent_or_disabled', 'required_result': 'memory selected then fail closed; legacy count zero.'},
    {'id': 'kill_switch_active', 'required_result': 'memory selected then fail closed; legacy count zero.'},
    {'id': 'grant_missing', 'required_result': 'memory selected then fail closed; legacy count zero.'},
    {
        'id': 'write_convergence_absent_or_false',
        'required_result': 'memory selected then fail closed; legacy count zero.',
    },
    {'id': 'head_missing_or_malformed', 'required_result': 'memory selected then fail closed; legacy count zero.'},
    {
        'id': 'head_projection_generation_mismatch',
        'required_result': 'memory selected then fail closed; legacy count zero.',
    },
    {
        'id': 'projection_missing_or_malformed',
        'required_result': 'memory selected then fail closed; legacy count zero.',
    },
    {
        'id': 'cursor_malformed_tampered_stale_or_cross_user',
        'required_result': 'Stable error/client result; no legacy fallback; no cross-user disclosure.',
    },
    {'id': 'runtime_firestore_read_permission_denied', 'required_result': 'Fail closed; no legacy fallback.'},
    {
        'id': 'firestore_timeout_or_unavailable',
        'required_result': 'Fail closed via dependency-injection tests; no public bypass endpoint.',
    },
    {'id': 'every_get_case_zero_memory_writes', 'required_result': 'Zero successful or attempted memory writes.'},
    {'id': 'real_projection_query', 'required_result': 'Succeeds against dev Firestore with checked-in indexes READY.'},
    {
        'id': 'telemetry_redaction',
        'required_result': 'Route/reason/trace present; memory, token, cursor payload absent.',
    },
    {
        'id': 'kill_switch_rollback',
        'required_result': 'Blocks within documented propagation interval without redeployment.',
    },
)

_REQUIRED_ENV = (
    'MEMORY_DEV_CLOUD_PROJECT_ID',
    'MEMORY_DEV_CLOUD_PROJECT_NUMBER',
    'MEMORY_DEV_CLOUD_DATABASE_ID',
    'MEMORY_DEV_CLOUD_REGION',
    'MEMORY_DEV_CLOUD_BACKEND_URL',
    'MEMORY_DEV_CLOUD_DEPLOYED_REVISION',
    'MEMORY_DEV_CLOUD_IMAGE_DIGEST',
    'MEMORY_DEV_CLOUD_RUNTIME_SERVICE_ACCOUNT',
    'MEMORY_DEV_CLOUD_FIXTURE_WRITER_PRINCIPAL',
)

_REDACTED_ENV_KEYS = (
    'MEMORY_V3_GET_ENABLED',
    'MEMORY_MODE',
    'MEMORY_ENABLED_USERS',
    'MEMORY_V3_CURSOR_SECRET_VERSION',
    'MEMORY_V3_CURSOR_TTL_SECONDS',
)


def split_csv(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip() for part in raw.split(',') if part.strip())


@dataclass(frozen=True)
class DevCloudTarget:
    expected_project_id: str
    expected_project_number: str
    actual_project_id: str
    actual_project_number: str
    database_id: str
    region: str
    backend_url: str
    deployed_revision: str
    image_digest: str
    runtime_service_account: str
    fixture_writer_principal: str
    production_project_ids: tuple[str, ...]
    production_project_numbers: tuple[str, ...]


@dataclass(frozen=True)
class DevCloudPreflight:
    status: str
    target: DevCloudTarget
    blockers: tuple[dict[str, Any], ...]

    @property
    def ready(self) -> bool:
        return self.status == GATE_STATUS_READY_TO_EXECUTE


def target_from_env(env: dict[str, str] | None = None) -> DevCloudTarget:
    effective_env = env if env is not None else dict(os.environ)
    expected_project_id = effective_env.get('MEMORY_DEV_CLOUD_PROJECT_ID', '')
    expected_project_number = effective_env.get('MEMORY_DEV_CLOUD_PROJECT_NUMBER', '')
    return DevCloudTarget(
        expected_project_id=expected_project_id,
        expected_project_number=expected_project_number,
        actual_project_id=effective_env.get('GOOGLE_CLOUD_PROJECT')
        or effective_env.get('GCLOUD_PROJECT')
        or effective_env.get('FIREBASE_PROJECT_ID')
        or '',
        actual_project_number=effective_env.get('GOOGLE_CLOUD_PROJECT_NUMBER')
        or effective_env.get('FIREBASE_PROJECT_NUMBER')
        or '',
        database_id=effective_env.get('MEMORY_DEV_CLOUD_DATABASE_ID', ''),
        region=effective_env.get('MEMORY_DEV_CLOUD_REGION', ''),
        backend_url=effective_env.get('MEMORY_DEV_CLOUD_BACKEND_URL', ''),
        deployed_revision=effective_env.get('MEMORY_DEV_CLOUD_DEPLOYED_REVISION', ''),
        image_digest=effective_env.get('MEMORY_DEV_CLOUD_IMAGE_DIGEST', ''),
        runtime_service_account=effective_env.get('MEMORY_DEV_CLOUD_RUNTIME_SERVICE_ACCOUNT', ''),
        fixture_writer_principal=effective_env.get('MEMORY_DEV_CLOUD_FIXTURE_WRITER_PRINCIPAL', ''),
        production_project_ids=split_csv(effective_env.get('MEMORY_PRODUCTION_PROJECT_IDS')),
        production_project_numbers=split_csv(effective_env.get('MEMORY_PRODUCTION_PROJECT_NUMBERS')),
    )


def evaluate_target_preflight(env: dict[str, str] | None = None) -> DevCloudPreflight:
    effective_env = env if env is not None else dict(os.environ)
    target = target_from_env(effective_env)
    blockers: list[dict[str, Any]] = []
    for key in _REQUIRED_ENV:
        if not effective_env.get(key):
            blockers.append(_blocker('missing_required_env', f'{key} is required for dev-cloud proof execution.'))
    if not target.actual_project_id:
        blockers.append(
            _blocker('missing_actual_project_id', 'GOOGLE_CLOUD_PROJECT/FIREBASE_PROJECT_ID must be explicit.')
        )
    if not target.actual_project_number:
        blockers.append(
            _blocker(
                'missing_actual_project_number', 'GOOGLE_CLOUD_PROJECT_NUMBER/FIREBASE_PROJECT_NUMBER must be explicit.'
            )
        )
    if (
        target.expected_project_id
        and target.actual_project_id
        and target.expected_project_id != target.actual_project_id
    ):
        blockers.append(_blocker('project_id_mismatch', 'Expected and actual dev project IDs differ.'))
    if (
        target.expected_project_number
        and target.actual_project_number
        and target.expected_project_number != target.actual_project_number
    ):
        blockers.append(_blocker('project_number_mismatch', 'Expected and actual dev project numbers differ.'))
    blockers.extend(_production_target_blockers(target))
    if target.runtime_service_account and target.fixture_writer_principal:
        if target.runtime_service_account == target.fixture_writer_principal:
            blockers.append(
                _blocker(
                    'runtime_identity_matches_fixture_writer', 'Runtime and fixture-writer identities must differ.'
                )
            )
    status = GATE_STATUS_READY_TO_EXECUTE if not blockers else GATE_STATUS_BLOCKED
    return DevCloudPreflight(status=status, target=target, blockers=tuple(blockers))


def build_target_preflight_report(env: dict[str, str] | None = None) -> dict[str, Any]:
    preflight = evaluate_target_preflight(env)
    target = preflight.target
    return {
        'artifact': 'target-preflight.json',
        'status': preflight.status,
        'gate': 'v3_dev_cloud',
        'mutation_allowed': False,
        'target': {
            'expected_project_id': target.expected_project_id,
            'expected_project_number': target.expected_project_number,
            'actual_project_id': target.actual_project_id,
            'actual_project_number': target.actual_project_number,
            'database_id': target.database_id,
            'region': target.region,
            'backend_url': target.backend_url,
            'deployed_revision': target.deployed_revision,
            'image_digest': target.image_digest,
            'runtime_service_account': target.runtime_service_account,
            'fixture_writer_principal': target.fixture_writer_principal,
            'production_project_ids_configured': bool(target.production_project_ids),
            'production_project_numbers_configured': bool(target.production_project_numbers),
        },
        'blockers': list(preflight.blockers),
        'non_claims': [
            'This preflight performs no cloud calls and no Firestore writes.',
            'READY_TO_EXECUTE_DEV_CLOUD_PROOF is not Gate 2 GO.',
            'A local backend with dev credentials cannot satisfy Gate 2.',
        ],
    }


def build_candidate_manifest(
    *, repo_root: str | Path, env: dict[str, str] | None = None, run_id: str = 'not-run'
) -> dict[str, Any]:
    effective_env = env if env is not None else dict(os.environ)
    repo_path = Path(repo_root)
    index_path = repo_path / 'firestore.indexes.json'
    target = target_from_env(effective_env)
    return {
        'artifact': 'candidate-manifest.json',
        'status': GATE_STATUS_NOT_RUN,
        'run_id': run_id,
        'git_sha': effective_env.get('MEMORY_DEV_CLOUD_GIT_SHA', ''),
        'clean_tree_asserted': effective_env.get('MEMORY_DEV_CLOUD_CLEAN_TREE_ASSERTED', '').lower() == 'true',
        'image_digest': target.image_digest,
        'deployed_revision': target.deployed_revision,
        'backend_url': target.backend_url,
        'dev_project_id': target.expected_project_id,
        'dev_project_number': target.expected_project_number,
        'firestore_database_id': target.database_id,
        'region': target.region,
        'runtime_service_account': target.runtime_service_account,
        'fixture_writer_principal': target.fixture_writer_principal,
        'index_file_sha256': sha256_file(index_path) if index_path.exists() else '',
        'redacted_env': redacted_env_snapshot(effective_env),
        'non_claims': ['This manifest is a preparation artifact until filled by CI/deployment.'],
    }


def redacted_env_snapshot(env: dict[str, str]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for key in _REDACTED_ENV_KEYS:
        value = env.get(key, '')
        if key == 'MEMORY_ENABLED_USERS' and value:
            snapshot[key] = '<set:redacted-user-list>'
        else:
            snapshot[key] = value
    snapshot['MEMORY_V3_CURSOR_SECRET'] = '<redacted>' if env.get('MEMORY_V3_CURSOR_SECRET') else '<unset>'
    return snapshot


def build_dev_cloud_fixture_bundle(
    *, uid_a: str, uid_b: str, run_id: str, account_generation: int = 1
) -> dict[str, Any]:
    if not uid_a or not uid_b or uid_a == uid_b:
        raise ValueError('two distinct synthetic UIDs are required')
    if account_generation < 0:
        raise ValueError('account_generation must be nonnegative')
    documents: dict[str, Any] = {}
    documents.update(_baseline_docs_for_uid(uid_a, account_generation, memory_id=f'{run_id}-a-memory'))
    documents.update(_baseline_docs_for_uid(uid_b, account_generation, memory_id=f'{run_id}-b-memory'))
    documents[GLOBAL_READ_GATE_PATH] = {
        'route_scope': ROUTE_SCOPE,
        'purpose': 'v3_dev_cloud_fixture_global_gate',
        'owner': 'memory_platform_dev_cloud_proof',
        'config_schema_version': 1,
        'memory_reads_enabled': True,
        'kill_switch_active': False,
        'fixture_source': DEV_FIXTURE_SOURCE,
        'run_id': run_id,
    }
    documents[WRITE_CONVERGENCE_GATE_PATH] = {
        'route_scope': ROUTE_SCOPE,
        'purpose': 'v3_dev_cloud_fixture_write_convergence',
        'owner': 'memory_platform_dev_cloud_proof',
        'config_schema_version': 1,
        'durable_outbox_enabled': True,
        'dual_write_projection_ready': True,
        'delete_convergence_ready': True,
        'idempotency_contract_ready': True,
        'fixture_source': DEV_FIXTURE_SOURCE,
        'run_id': run_id,
    }
    return {
        'artifact': 'fixtures.redacted.json',
        'status': GATE_STATUS_NOT_RUN,
        'fixture_source': DEV_FIXTURE_SOURCE,
        'run_id': run_id,
        'synthetic_uids': [uid_a, uid_b],
        'document_count': len(documents),
        'documents': documents,
        'setup_manifest': sorted(documents),
        'cleanup_manifest': sorted(documents),
        'non_claims': ['This fixture bundle is local JSON only; it does not write Firestore.'],
    }


def build_proof_matrix() -> dict[str, Any]:
    return {
        'artifact': 'proof-results.json',
        'status': GATE_STATUS_NOT_RUN,
        'required_case_count': len(PROOF_MATRIX),
        'cases': [dict(case) for case in PROOF_MATRIX],
        'acceptance': 'Every case must pass without skips in the deployed dev-cloud branch backend.',
    }


def build_review_template(preflight_report: dict[str, Any]) -> str:
    status = preflight_report['status']
    blockers = preflight_report['blockers']
    lines = [
        '# memory /v3 dev-cloud proof review',
        '',
        f'Preflight status: `{status}`',
        '',
        '## Decision',
        '',
        '- [ ] GO',
        '- [ ] NO_GO',
        '- [ ] BLOCKED',
        '',
        '## Blockers',
        '',
    ]
    if blockers:
        for blocker in blockers:
            lines.append(f"- `{blocker['blocker_id']}`: {blocker['message']}")
    else:
        lines.append('- No local preflight blockers; execute the deployed dev-cloud proof suite next.')
    lines.extend(
        [
            '',
            '## Non-claims',
            '',
            '- This review is not production activation approval.',
            '- READY_TO_EXECUTE_DEV_CLOUD_PROOF is not Gate 2 GO.',
            '- Gate 2 GO requires the deployed branch backend evidence bundle and independent review.',
            '',
        ]
    )
    return '\n'.join(lines)


def write_prepared_bundle(
    *,
    repo_root: str | Path,
    output_dir: str | Path,
    uid_a: str,
    uid_b: str,
    run_id: str,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    effective_env = env if env is not None else dict(os.environ)
    preflight = build_target_preflight_report(effective_env)
    artifacts: dict[str, Any] = {
        'candidate-manifest.json': build_candidate_manifest(repo_root=repo_root, env=effective_env, run_id=run_id),
        'target-preflight.json': preflight,
        'fixtures.redacted.json': build_dev_cloud_fixture_bundle(uid_a=uid_a, uid_b=uid_b, run_id=run_id),
        'proof-results.json': build_proof_matrix(),
        'review.md': build_review_template(preflight),
    }
    for name in REQUIRED_ARTIFACTS:
        path = out / name
        if name in artifacts:
            write_artifact(path, artifacts[name])
        elif name.endswith('.ndjson'):
            path.write_text('')
        elif name == 'junit.xml':
            path.write_text('<testsuites tests="0" failures="0" errors="0" skipped="0" />\n')
        elif name == 'checksums.sha256':
            continue
        elif name.endswith('.md'):
            path.write_text('# Placeholder\n\nTo be replaced by deployed dev-cloud proof execution.\n')
        else:
            write_artifact(
                path,
                {
                    'artifact': name,
                    'status': GATE_STATUS_NOT_RUN,
                    'placeholder': True,
                    'required_before_gate2_go': True,
                },
            )
    checksums = build_checksums(out, REQUIRED_ARTIFACTS)
    (out / 'checksums.sha256').write_text(checksums)
    return {
        'status': preflight['status'],
        'output_dir': str(out),
        'artifact_count': len(REQUIRED_ARTIFACTS),
        'artifacts': list(REQUIRED_ARTIFACTS),
        'blockers': preflight['blockers'],
    }


def write_artifact(path: Path, value: object) -> None:
    if isinstance(value, str):
        path.write_text(value)
    else:
        path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + '\n')


def build_checksums(directory: Path, names: Iterable[str]) -> str:
    lines: list[str] = []
    for name in names:
        if name == 'checksums.sha256':
            continue
        path = directory / name
        if path.exists():
            lines.append(f'{sha256_file(path)}  {name}')
    return '\n'.join(lines) + ('\n' if lines else '')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _baseline_docs_for_uid(uid: str, account_generation: int, memory_id: str) -> dict[str, Any]:
    paths = MemoryCollections(uid=uid)
    return {
        paths.memory_control_state: _control_state(uid, account_generation),
        paths.memory_state_head: _state_head(uid, account_generation),
        paths.v3_compatibility_projection_state: _projection_state(uid, account_generation),
        f'{paths.v3_compatibility_projection_items}/{memory_id}': _projection_item(uid, account_generation, memory_id),
    }


def _control_state(uid: str, account_generation: int) -> dict[str, Any]:
    return {
        'uid': uid,
        'schema_version': DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        'mode': MemoryRolloutMode.read.value,
        'mode_epoch': 1,
        'cutover_epoch': 1,
        'account_generation': account_generation,
        'fallback_projection_ready': True,
        'persistent_memory_writes_started': True,
        'decommission_reconciled': False,
        'writes_blocked': False,
        'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
        'grants': {'omi_chat': {'default_memory': True, 'archive': False}},
        'fixture_source': DEV_FIXTURE_SOURCE,
    }


def _state_head(uid: str, account_generation: int) -> dict[str, Any]:
    return {
        'uid': uid,
        'schema_version': 1,
        'source': 'memory_state_head',
        'account_generation': account_generation,
        'head_commit_id': f'dev-cloud-head-{uid}-{account_generation}',
        'commit_sequence': account_generation,
        'fixture_source': DEV_FIXTURE_SOURCE,
    }


def _projection_state(uid: str, account_generation: int) -> dict[str, Any]:
    return {
        'uid': uid,
        'schema_version': 1,
        'source': 'memory_items_projection',
        'ready': True,
        'account_generation': account_generation,
        'projection_generation': account_generation,
        'freshness_fence_generation': account_generation,
        'tombstone_fence_generation': account_generation,
        'vector_cleanup_fence_generation': account_generation,
        'source_commit_id': f'dev-cloud-source-{uid}-{account_generation}',
        'projection_commit_id': f'dev-cloud-projection-{uid}-{account_generation}',
        'source_evidence_fence': f'dev-cloud-evidence-{uid}-{account_generation}',
        'projection_evidence_fence': f'dev-cloud-evidence-{uid}-{account_generation}',
        'projection_version': 'v3_memorydb_compatibility',
        'source_version': 'dev-cloud-fixture-v1',
        'write_convergence_complete': True,
        'delete_convergence_complete': True,
        'tombstone_convergence_complete': True,
        'empty_projection': False,
        'fixture_source': DEV_FIXTURE_SOURCE,
    }


def _projection_item(uid: str, account_generation: int, memory_id: str) -> dict[str, Any]:
    timestamp = '2026-06-21T00:00:00Z'
    return {
        'uid': uid,
        'memory_id': memory_id,
        'schema_version': 1,
        'source': 'memory_items_projection',
        'account_generation': account_generation,
        'projection_generation': account_generation,
        'source_commit_id': f'dev-cloud-source-{uid}-{account_generation}',
        'projection_commit_id': f'dev-cloud-projection-{uid}-{account_generation}',
        'projection_evidence_fence': f'dev-cloud-evidence-{uid}-{account_generation}',
        'freshness_fence_generation': account_generation,
        'tombstone_fence_generation': account_generation,
        'write_convergence_complete': True,
        'delete_convergence_complete': True,
        'tombstone_convergence_complete': True,
        'created_at': timestamp,
        'memorydb': {
            'id': memory_id,
            'uid': uid,
            'content': f'synthetic dev-cloud memory for {uid}',
            'category': 'system',
            'visibility': 'private',
            'tags': [],
            'created_at': timestamp,
            'updated_at': timestamp,
            'reviewed': True,
            'user_review': None,
            'manually_added': False,
            'edited': False,
            'conversation_id': None,
            'data_protection_level': 'standard',
        },
        'fixture_source': DEV_FIXTURE_SOURCE,
    }


def _production_target_blockers(target: DevCloudTarget) -> tuple[dict[str, Any], ...]:
    blockers: list[dict[str, Any]] = []
    if target.expected_project_id and target.expected_project_id in target.production_project_ids:
        blockers.append(
            _blocker('expected_project_id_is_production', 'Expected dev project ID is configured as production.')
        )
    if target.actual_project_id and target.actual_project_id in target.production_project_ids:
        blockers.append(
            _blocker('actual_project_id_is_production', 'Actual cloud project ID is configured as production.')
        )
    if target.expected_project_number and target.expected_project_number in target.production_project_numbers:
        blockers.append(
            _blocker(
                'expected_project_number_is_production', 'Expected dev project number is configured as production.'
            )
        )
    if target.actual_project_number and target.actual_project_number in target.production_project_numbers:
        blockers.append(
            _blocker('actual_project_number_is_production', 'Actual cloud project number is configured as production.')
        )
    return tuple(blockers)


def _blocker(blocker_id: str, message: str) -> dict[str, Any]:
    return {'blocker_id': blocker_id, 'message': message, 'required_before_gate2_go': True}


# Neutral symbol aliases (memory names remain valid via shim)

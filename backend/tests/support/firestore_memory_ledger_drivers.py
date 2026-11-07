"""Executable profiles for the legacy memory ledger commit fence queries.

C015: the commit fence pre-screens with two transactional limit-1 probes
(any override document; any tombstoned item) before the per-memory exact
reads. Trial 0 drives the clean fast path (no override history); trial 1
seeds a tombstoned override so the probe-hit fallback records the exact
per-memory lookups too.
"""

import os
from unittest.mock import patch

from database.memory_privacy_reference_index import with_privacy_reference_tokens
from tests.support.firestore_query_drivers import DriverEntry, CoveredByEntry, SHAPE_UID

_FACT = {
    'id': 'mem-1',
    'content': 'Lives in NYC',
    'predicate': 'resides_in',
    'arguments': {'location': 'NYC'},
    'subject_entity_id': 'user',
    'qualifiers': {},
}


def _mutations(_transaction=None):
    return [{'fact': dict(_FACT)}]


def _builder(transaction):
    return {'mutations': _mutations()}


def _seed_fence_history(client, combo, trial):
    if trial % 2 == 1:
        client.documents[f'users/{SHAPE_UID}/memory_historical_overrides/mem-1'] = {'status': 'tombstoned'}


def reference_switch_environment(_client):
    return patch.dict(os.environ, {'MEMORY_PRIVACY_REFERENCE_INDEX': 'off'})


def seed_privacy_reference_history(client, combo, trial):
    os.environ['MEMORY_PRIVACY_REFERENCE_INDEX'] = 'on' if trial % 2 else 'off'


def seed_privacy_operation_history(client, combo, trial):
    seed_privacy_reference_history(client, combo, trial)
    path = f'users/{SHAPE_UID}/memory_operations/index-operation'
    client.queue_results([client.snapshot(path, with_privacy_reference_tokens(SHAPE_UID, {'nested': ['mem-1']}))])


def registry_extension():
    return (
        DriverEntry(
            'database.memory_ledger.append_commit',
            base={
                'uid': SHAPE_UID,
                'parent_commit_id': None,
                'mutations': _mutations(),
            },
            neutrals={
                'run_id': (None, 'commit identity only; no query shape'),
                'commit_time': (None, 'timestamp operand only; module clock frozen'),
                'projection_writer': (None, 'callback side-effect neutralized'),
                'use_current_head': (False, 'head selection only; state document absent in trial'),
            },
            setup=_seed_fence_history,
            trials=2,
        ),
        DriverEntry(
            'database.memory_ledger.append_commit_with_builder',
            base={
                'uid': SHAPE_UID,
                'parent_commit_id': None,
                'mutation_builder': _builder,
            },
            neutrals={
                'run_id': (None, 'commit identity only; no query shape'),
                'commit_time': (None, 'timestamp operand only; module clock frozen'),
                'use_current_head': (False, 'head selection only; state document absent in trial'),
            },
            setup=_seed_fence_history,
            trials=2,
        ),
        CoveredByEntry(
            'database.memory_ledger._append_commit_transaction',
            covered_by=('database.memory_ledger.append_commit',),
            reason='transactional body delegates every read to the fence and the probe; '
            'document writes never appear as a query caller',
            expect_observed=False,
            body_digest='a2687d1eeecd27eb6daedf30ba86755b59dada17f50a7c401ad96e51060f2619',
        ),
        CoveredByEntry(
            'database.memory_ledger._append_commit_with_builder_transaction',
            covered_by=('database.memory_ledger.append_commit_with_builder',),
            reason='transactional body delegates every read to the fence and the probe; '
            'document writes never appear as a query caller',
            expect_observed=False,
            body_digest='ae4939ae5a04333cb3aadcb8e0a38a1c608139a556c01422adb6f048a937628c',
        ),
        CoveredByEntry(
            'database.memory_ledger._assert_legacy_commit_privacy_fences',
            covered_by=(
                'database.memory_ledger.append_commit',
                'database.memory_ledger.append_commit_with_builder',
            ),
            reason='fence runs document lookups only (no query builders); its probe helper '
            '_legacy_commit_fences_need_exact_reads owns the recorded query callers',
            expect_observed=False,
            body_digest='59596ea3da66dd82e55c7a08ad949ee894ba1a4fe7714f79ced320955ed22959',
        ),
        CoveredByEntry(
            'database.memory_ledger._legacy_commit_fences_need_exact_reads',
            covered_by=(
                'database.memory_ledger.append_commit',
                'database.memory_ledger.append_commit_with_builder',
            ),
            reason='fence pre-screen observed inside both public commit drivers',
        ),
    )

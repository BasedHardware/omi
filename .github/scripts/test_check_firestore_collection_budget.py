#!/usr/bin/env python3
"""Offline fixtures for the M8 Firestore collection budget guard.

Both directions are pinned: an unbudgeted new queue/job/lease collection fails,
a budgeted one passes, and a collection that already exists at the base revision
is grandfathered. The fixtures build a real throwaway git repository so the
base-revision scan is exercised, not mocked.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_firestore_collection_budget import (
    ENABLED_ENV,
    REASON_ENV,
    kill_switch,
    load_registry,
    scan_git_tree,
    scan_tree,
    unbudgeted,
    work_state_token,
)

BASE_SOURCE = '''from google.cloud import firestore

client = firestore.Client()


def read_user(uid):
    return client.collection('users').document(uid).get()
'''

NEW_QUEUE_SOURCE = BASE_SOURCE + '''

FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'


def claim_job(job_id):
    return client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id).get()
'''

NEW_USER_DATA_SOURCE = BASE_SOURCE + '''

def read_releases():
    return client.collection('desktop_releases').stream()
'''

BUDGET = {
    'collection': 'conversation_finalization_jobs',
    'owner': 'conversations lane',
    'unit': 'job',
    'reads_per_unit_budget': 12,
    'reads_per_day_budget': 2_000_000,
    'basis': 'planning-bound',
    'source': 'fixture: one claim read plus one status read per job',
    'reviewed': '2026-11-12',
}


class GuardFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / 'backend' / 'database'
        self.database.mkdir(parents=True)
        self.registry = self.root / '.github' / 'firestore-collection-budgets.json'
        self.registry.parent.mkdir(parents=True)
        self.write_registry()
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.com')
        self.git('config', 'user.name', 'Fixture')
        self.write_source(BASE_SOURCE)
        self.git('add', '-A')
        self.git('commit', '-m', 'base')

    def git(self, *args: str) -> None:
        subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)

    def write_source(self, source: str) -> None:
        (self.database / 'queue.py').write_text(source, encoding='utf-8')

    def write_registry(self, budgets: list[dict] | None = None, exempt: list[dict] | None = None) -> None:
        self.registry.write_text(
            json.dumps({'budgets': budgets or [], 'exempt': exempt or []}),
            encoding='utf-8',
        )

    def evaluate(self) -> list[str]:
        budgets, exempt, errors = load_registry(self.registry)
        self.assertEqual(errors, [])
        return unbudgeted(scan_tree(self.root), scan_git_tree(self.root, 'HEAD'), budgets, exempt)


class UnbudgetedCollectionTests(GuardFixture):
    def test_unbudgeted_new_queue_collection_fails(self) -> None:
        self.write_source(NEW_QUEUE_SOURCE)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_finalization_jobs', errors[0])
        self.assertIn("matched 'jobs'", errors[0])
        self.assertIn('backend/database/queue.py:', errors[0])

    def test_budgeted_new_queue_collection_passes(self) -> None:
        self.write_source(NEW_QUEUE_SOURCE)
        self.write_registry(budgets=[BUDGET])
        self.assertEqual(self.evaluate(), [])

    def test_new_user_data_collection_passes(self) -> None:
        self.write_source(NEW_USER_DATA_SOURCE)
        self.assertEqual(self.evaluate(), [])

    def test_existing_collection_is_grandfathered(self) -> None:
        # ``users`` is not work state, so use a work-state name that predates the change.
        self.write_source(BASE_SOURCE + "\n\ndef jobs():\n    return client.collection('legacy_jobs').stream()\n")
        self.git('add', '-A')
        self.git('commit', '-m', 'legacy jobs')
        self.write_source(
            BASE_SOURCE
            + "\n\ndef jobs():\n    return client.collection('legacy_jobs').stream()\n"
            + "\n\ndef more_jobs():\n    return client.collection('legacy_jobs').limit(1).stream()\n"
        )
        self.assertEqual(self.evaluate(), [])

    def test_imported_constant_is_resolved(self) -> None:
        (self.database / 'constants.py').write_text("OUTBOX_COLLECTION = 'sync_reprocess_outbox'\n", encoding='utf-8')
        self.write_source(
            BASE_SOURCE
            + "\nfrom database.constants import OUTBOX_COLLECTION\n"
            + "\n\ndef outbox():\n    return client.collection(OUTBOX_COLLECTION).stream()\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('sync_reprocess_outbox', errors[0])

    def test_exempt_entry_allows_collection(self) -> None:
        self.write_source(NEW_QUEUE_SOURCE)
        self.write_registry(exempt=[{'collection': 'conversation_finalization_jobs', 'reason': 'fixture exemption'}])
        self.assertEqual(self.evaluate(), [])

    def test_work_state_token_classification(self) -> None:
        self.assertEqual(work_state_token('conversation_finalization_jobs'), 'jobs')
        self.assertEqual(work_state_token('channel_turn_leases'), 'leases')
        self.assertEqual(work_state_token('sync_reprocess_outbox'), 'outbox')
        self.assertIsNone(work_state_token('desktop_releases'))
        self.assertIsNone(work_state_token('memory_state'))


class RegistryValidationTests(GuardFixture):
    def test_incomplete_budget_entry_fails(self) -> None:
        incomplete = dict(BUDGET)
        del incomplete['reads_per_day_budget']
        self.write_registry(budgets=[incomplete])
        _budgets, _exempt, errors = load_registry(self.registry)
        self.assertTrue(any('missing reads_per_day_budget' in error for error in errors), errors)

    def test_non_positive_budget_fails(self) -> None:
        self.write_registry(budgets=[dict(BUDGET, reads_per_unit_budget=0)])
        _budgets, _exempt, errors = load_registry(self.registry)
        self.assertTrue(any('reads_per_unit_budget must be a positive integer' in error for error in errors), errors)

    def test_duplicate_budget_entry_fails(self) -> None:
        self.write_registry(budgets=[BUDGET, BUDGET])
        _budgets, _exempt, errors = load_registry(self.registry)
        self.assertTrue(any('duplicate budget' in error for error in errors), errors)

    def test_budgeted_and_exempt_is_rejected(self) -> None:
        self.write_registry(
            budgets=[BUDGET],
            exempt=[{'collection': BUDGET['collection'], 'reason': 'contradiction'}],
        )
        _budgets, _exempt, errors = load_registry(self.registry)
        self.assertTrue(any('both budgeted and exempt' in error for error in errors), errors)

    def test_missing_registry_fails_closed(self) -> None:
        self.registry.unlink()
        _budgets, _exempt, errors = load_registry(self.registry)
        self.assertTrue(any('registry is missing' in error for error in errors), errors)


class KillSwitchTests(unittest.TestCase):
    def test_default_is_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENABLED_ENV, None)
            self.assertEqual(kill_switch(), ('enabled', ''))

    def test_explicit_zero_requires_a_reason(self) -> None:
        with patch.dict(os.environ, {ENABLED_ENV: '0'}, clear=False):
            os.environ.pop(REASON_ENV, None)
            state, detail = kill_switch()
            self.assertEqual(state, 'invalid')
            self.assertIn(REASON_ENV, detail)

    def test_explicit_zero_with_reason_disables(self) -> None:
        with patch.dict(os.environ, {ENABLED_ENV: '0', REASON_ENV: 'rollback 2026-11-12'}, clear=False):
            self.assertEqual(kill_switch(), ('disabled', 'rollback 2026-11-12'))

    def test_unknown_value_fails_closed(self) -> None:
        with patch.dict(os.environ, {ENABLED_ENV: 'yes'}, clear=False):
            self.assertEqual(kill_switch()[0], 'invalid')


class RepositoryContractTests(unittest.TestCase):
    def test_repository_registry_is_valid(self) -> None:
        root = Path(__file__).resolve().parents[2]
        _budgets, _exempt, errors = load_registry(root / '.github' / 'firestore-collection-budgets.json')
        self.assertEqual(errors, [])

    def test_manifest_runs_guard_in_both_lanes(self) -> None:
        from run_checks import load_manifest, resolve_checks

        root = Path(__file__).resolve().parents[2]
        manifest = load_manifest(root / '.github' / 'checks-manifest.yaml')
        check = next(check for check in manifest.checks if check.id == 'firestore-collection-budget')
        self.assertEqual(check.command[0], 'python3')
        self.assertIn('.github/scripts/check_firestore_collection_budget.py', check.command)
        self.assertIn('{base}', check.command)
        for lane in ('local', 'ci'):
            selected = resolve_checks(manifest, ['backend/database/new_queue.py'], lane, include_pr_body_checks=False)
            self.assertIn(check, selected, lane)


if __name__ == '__main__':
    unittest.main()

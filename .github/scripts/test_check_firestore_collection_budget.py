#!/usr/bin/env python3
"""Offline fixtures for the M8 Firestore collection budget guard.

Both directions are pinned on both Firestore surfaces: an unbudgeted new
queue/job/lease collection fails, a budgeted one passes, a collection that
already exists at the base revision is grandfathered, and a computed collection
name fails until a dynamic family budget is declared. A grandfathered computed
site whose literal namespace tuple grows is compared by family, so the new
member needs its own budget. Python's ``collection_group_id`` keyword form is
pinned alongside the positional form. The fixtures build a real throwaway git
repository so the base-revision scan is exercised, not mocked.
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
    _excluded,
    ENABLED_ENV,
    REASON_ENV,
    findings,
    kill_switch,
    load_registry,
    scan_git_tree,
    scan_tree,
    work_state_token,
)

BASE_PYTHON = '''from google.cloud import firestore

client = firestore.Client()


def read_user(uid):
    return client.collection('users').document(uid).get()
'''

NEW_QUEUE_PYTHON = BASE_PYTHON + '''

FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'


def claim_job(job_id):
    return client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id).get()
'''

NEW_USER_DATA_PYTHON = BASE_PYTHON + '''

def read_releases():
    return client.collection('desktop_releases').stream()
'''

COMPUTED_PYTHON = BASE_PYTHON + '''

def claim_stage_job(stage, job_id):
    return client.collection(f'new_{stage}_jobs').document(job_id).get()
'''

STATIC_PATH_PYTHON = BASE_PYTHON + '''

def claim_user_job(uid, job_id):
    return client.collection(f'users/{uid}/jobs').document(job_id).get()
'''

# The reported gap: the computed call site is unchanged, but the namespace tuple it
# reads gains a member, so the collection family grows without a new site key.
NAMESPACE_TUPLE_PYTHON = BASE_PYTHON + '''

NAMESPACES = ('batch_pipeline_prod', 'batch_pipeline_dev')


def purge_jobs(client, namespace):
    return client.collection(f'{namespace}_jobs').stream()


def sweep(client):
    for index in range(len(NAMESPACES)):
        namespace = NAMESPACES[index]
        purge_jobs(client, namespace)
'''

EXPANDED_NAMESPACE_TUPLE_PYTHON = NAMESPACE_TUPLE_PYTHON.replace(
    "'batch_pipeline_dev')", "'batch_pipeline_dev', 'batch_pipeline_preview')"
)

# Same shape, but the namespace is only ever a parameter: the guard cannot enumerate
# the family, so a tuple edit must not invent members for it.
UNBOUND_NAMESPACE_PYTHON = BASE_PYTHON + '''

NAMESPACES = ('batch_pipeline_prod', 'batch_pipeline_dev')


def purge_jobs(client, namespace):
    return client.collection(f'{namespace}_jobs').stream()
'''

BASE_WEB = '''import { getDb } from "@/lib/firebase/admin";

export async function readUser(uid: string) {
  return getDb().collection("users").doc(uid).get();
}
'''

NEW_QUEUE_WEB = BASE_WEB + '''

export async function claimDispatch(id: string) {
  return getDb().collection("conversation_dispatch_queue").doc(id).get();
}
'''

CONST_QUEUE_WEB = BASE_WEB + '''

const NEW_JOBS_COLLECTION = "conversation_retry_jobs";

export async function claimRetry(id: string) {
  return getDb().collection(NEW_JOBS_COLLECTION).doc(id).get();
}
'''

COMPUTED_WEB = BASE_WEB + '''

export async function claimStage(stage: string, id: string) {
  return getDb().collection(`new_${stage}_jobs`).doc(id).get();
}
'''

STATIC_PATH_WEB = BASE_WEB + '''

export async function claimUserJob(uid: string, id: string) {
  return getDb().collection(`users/${uid}/jobs`).doc(id).get();
}
'''

MODULAR_WEB = BASE_WEB + '''

import { collection, doc } from "firebase/firestore";

export function userMessages(db: unknown, uid: string) {
  return collection(db, "users", uid, "messages");
}

export function persona(db: unknown, id: string) {
  return doc(db, "plugins_data", id);
}
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

DYNAMIC = {
    'site': 'backend/database/queue.py',
    'expression': "f'new_{stage}_jobs'",
    'collection_pattern': 'new_*_jobs',
    'owner': 'fixture lane',
    'unit': 'job',
    'reads_per_unit_budget': 4,
    'reads_per_day_budget': 1_000,
    'basis': 'planning-bound',
    'source': 'fixture: one claim read per job',
    'reviewed': '2026-11-13',
}

WEB_DYNAMIC = {
    'site': 'web/admin/lib/queue.ts',
    'expression': '`new_${stage}_jobs`',
    'collection_pattern': 'new_*_jobs',
    'owner': 'fixture lane',
    'unit': 'job',
    'reads_per_unit_budget': 4,
    'reads_per_day_budget': 1_000,
    'basis': 'planning-bound',
    'source': 'fixture: one claim read per job',
    'reviewed': '2026-11-13',
}


class GuardFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.python_file = self.root / 'backend' / 'database' / 'queue.py'
        self.web_file = self.root / 'web' / 'admin' / 'lib' / 'queue.ts'
        self.python_file.parent.mkdir(parents=True)
        self.web_file.parent.mkdir(parents=True)
        self.registry = self.root / '.github' / 'firestore-collection-budgets.json'
        self.registry.parent.mkdir(parents=True)
        self.write_registry()
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'fixture@example.com')
        self.git('config', 'user.name', 'Fixture')
        self.write_python(BASE_PYTHON)
        self.write_web(BASE_WEB)
        self.git('add', '-A')
        self.git('commit', '-m', 'base')

    def git(self, *args: str) -> None:
        subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)

    def write_python(self, source: str) -> None:
        self.python_file.write_text(source, encoding='utf-8')

    def write_web(self, source: str) -> None:
        self.web_file.write_text(source, encoding='utf-8')

    def write_registry(
        self,
        budgets: list[dict] | None = None,
        exempt: list[dict] | None = None,
        dynamic: list[dict] | None = None,
    ) -> None:
        self.registry.write_text(
            json.dumps({'budgets': budgets or [], 'dynamic': dynamic or [], 'exempt': exempt or []}),
            encoding='utf-8',
        )

    def evaluate(self) -> list[str]:
        budgets, exempt, dynamic, errors = load_registry(self.registry)
        self.assertEqual(errors, [])
        return findings(scan_tree(self.root), scan_git_tree(self.root, 'HEAD'), budgets, exempt, dynamic)


class VirtualenvExclusionTests(unittest.TestCase):
    """Installed packages are not product code: a worktree's own backend/.venv and
    backend/.openapi-venv must never be scanned (they held Firestore's client library
    and failed every push), while look-alike product directories still are."""

    def test_worktree_virtualenv_roots_are_excluded(self) -> None:
        for relative in (
            "backend/.venv/lib/python3.11/site-packages/google/cloud/firestore_v1/client.py",
            "backend/.openapi-venv/lib/python3.11/site-packages/fake_firestore/client.py",
        ):
            self.assertTrue(_excluded(relative), relative)

    def test_product_code_is_still_scanned(self) -> None:
        for relative in (
            "backend/database/conversations.py",
            "backend/utils/venv_helper.py",
            "backend/venv/queue.py",
            "backend/domain/site-packages/queue.py",
            "backend/domain/.venv/queue.py",
            "web/admin/venv/queue.ts",
            "web/admin/lib/queue.ts",
        ):
            self.assertFalse(_excluded(relative), relative)


class LiteralCollectionTests(GuardFixture):
    def test_generated_python_environments_do_not_hide_first_party_work_state(self) -> None:
        for environment in ('.venv', '.openapi-venv'):
            dependency = self.root / 'backend' / environment / 'lib' / 'site-packages' / 'client.py'
            dependency.parent.mkdir(parents=True)
            dependency.write_text('def read(client, collection_id):\n    return client.collection(collection_id)\n')
        self.assertEqual(self.evaluate(), [])
        self.write_python(NEW_QUEUE_PYTHON)
        self.assertTrue(self.evaluate(), 'generated dependency exclusions must not exempt first-party queues')

    def test_unbudgeted_new_queue_collection_fails(self) -> None:
        self.write_python(NEW_QUEUE_PYTHON)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_finalization_jobs', errors[0])
        self.assertIn("matched 'jobs'", errors[0])
        self.assertIn('backend/database/queue.py:', errors[0])

    def test_budgeted_new_queue_collection_passes(self) -> None:
        self.write_python(NEW_QUEUE_PYTHON)
        self.write_registry(budgets=[BUDGET])
        self.assertEqual(self.evaluate(), [])

    def test_new_user_data_collection_passes(self) -> None:
        self.write_python(NEW_USER_DATA_PYTHON)
        self.assertEqual(self.evaluate(), [])

    def test_existing_collection_is_grandfathered(self) -> None:
        self.write_python(BASE_PYTHON + "\n\ndef jobs():\n    return client.collection('legacy_jobs').stream()\n")
        self.git('add', '-A')
        self.git('commit', '-m', 'legacy jobs')
        self.write_python(
            BASE_PYTHON
            + "\n\ndef jobs():\n    return client.collection('legacy_jobs').stream()\n"
            + "\n\ndef more_jobs():\n    return client.collection('legacy_jobs').limit(1).stream()\n"
        )
        self.assertEqual(self.evaluate(), [])

    def test_imported_constant_is_resolved(self) -> None:
        (self.python_file.parent / 'constants.py').write_text(
            "OUTBOX_COLLECTION = 'sync_reprocess_outbox'\n", encoding='utf-8'
        )
        self.write_python(
            BASE_PYTHON
            + "\nfrom database.constants import OUTBOX_COLLECTION\n"
            + "\n\ndef outbox():\n    return client.collection(OUTBOX_COLLECTION).stream()\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('sync_reprocess_outbox', errors[0])

    def test_exempt_entry_allows_collection(self) -> None:
        self.write_python(NEW_QUEUE_PYTHON)
        self.write_registry(exempt=[{'collection': 'conversation_finalization_jobs', 'reason': 'fixture exemption'}])
        self.assertEqual(self.evaluate(), [])

    def test_python_keyword_collection_argument_fails(self) -> None:
        self.write_python(
            BASE_PYTHON
            + "\n\ndef claim(job_id):\n"
            + "    return client.collection(collection_id='conversation_retry_jobs').document(job_id).get()\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_retry_jobs', errors[0])
        self.assertNotIn('computed collection name', errors[0])

    def test_python_keyword_collection_argument_with_budget_passes(self) -> None:
        self.write_python(
            BASE_PYTHON
            + "\n\ndef claim(job_id):\n"
            + "    return client.collection(collection_id=JOBS).document(job_id).get()\n"
            + "\n\nJOBS = 'conversation_retry_jobs'\n"
        )
        self.write_registry(budgets=[dict(BUDGET, collection='conversation_retry_jobs')])
        self.assertEqual(self.evaluate(), [])

    def test_python_argument_less_collection_call_fails_closed(self) -> None:
        self.write_python(
            BASE_PYTHON + "\n\ndef claim(job_id):\n    return client.collection().document(job_id).get()\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection name', errors[0])

    def test_python_collection_group_keyword_argument_fails(self) -> None:
        self.write_python(
            BASE_PYTHON
            + "\n\ndef steps():\n"
            + "    return client.collection_group(collection_group_id='conversation_retry_steps').stream()\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_retry_steps', errors[0])
        self.assertNotIn('computed collection name', errors[0])

    def test_python_collection_group_positional_argument_fails(self) -> None:
        self.write_python(
            BASE_PYTHON
            + "\n\ndef steps():\n"
            + "    return client.collection_group('conversation_retry_steps').stream()\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_retry_steps', errors[0])
        self.assertNotIn('computed collection name', errors[0])

    def test_python_collection_group_with_budget_passes(self) -> None:
        self.write_python(
            BASE_PYTHON
            + "\n\ndef steps():\n"
            + "    return client.collection_group(collection_group_id='conversation_retry_steps').stream()\n"
        )
        self.write_registry(budgets=[dict(BUDGET, collection='conversation_retry_steps')])
        self.assertEqual(self.evaluate(), [])

    def test_work_state_token_classification(self) -> None:
        self.assertEqual(work_state_token('conversation_finalization_jobs'), 'jobs')
        self.assertEqual(work_state_token('channel_turn_leases'), 'leases')
        self.assertEqual(work_state_token('sync_reprocess_outbox'), 'outbox')
        self.assertEqual(work_state_token('newDispatchQueue'), 'dispatch')
        self.assertIsNone(work_state_token('desktop_releases'))
        self.assertIsNone(work_state_token('memory_state'))


class ComputedNameTests(GuardFixture):
    def test_computed_python_name_fails(self) -> None:
        self.write_python(COMPUTED_PYTHON)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection name', errors[0])
        self.assertIn("f'new_{stage}_jobs'", errors[0])
        self.assertIn('backend/database/queue.py:', errors[0])

    def test_computed_python_name_with_dynamic_entry_passes(self) -> None:
        self.write_python(COMPUTED_PYTHON)
        self.write_registry(dynamic=[DYNAMIC])
        self.assertEqual(self.evaluate(), [])

    def test_existing_computed_site_is_grandfathered(self) -> None:
        self.write_python(COMPUTED_PYTHON)
        self.git('add', '-A')
        self.git('commit', '-m', 'computed site')
        self.write_python(
            COMPUTED_PYTHON
            + "\n\ndef again(stage, job_id):\n    return client.collection(f'new_{stage}_jobs').document(job_id).get()\n"
        )
        self.assertEqual(self.evaluate(), [])

    def test_static_collection_segments_in_fstring_path_are_not_computed(self) -> None:
        self.write_python(STATIC_PATH_PYTHON)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn("jobs (matched 'jobs')", errors[0])
        self.assertNotIn('computed collection name', errors[0])

    def test_dynamic_entry_with_wrong_expression_does_not_cover(self) -> None:
        self.write_python(COMPUTED_PYTHON)
        self.write_registry(dynamic=[dict(DYNAMIC, expression="f'other_{stage}_jobs'")])
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection name', errors[0])

    def test_exempt_dynamic_site_allows_it(self) -> None:
        self.write_python(COMPUTED_PYTHON)
        self.write_registry(
            exempt=[
                {
                    'site': 'backend/database/queue.py',
                    'expression': "f'new_{stage}_jobs'",
                    'reason': 'fixture exemption',
                }
            ]
        )
        self.assertEqual(self.evaluate(), [])


class ComputedFamilyExpansionTests(GuardFixture):
    """A grandfathered computed site keeps its key when its namespace tuple grows.

    The key-level check cannot see the new collection, so the guard compares the
    enumerable family between the base revision and the working tree.
    """

    def commit_python(self, source: str) -> None:
        self.write_python(source)
        self.git('add', '-A')
        self.git('commit', '-m', 'namespace tuple')

    def test_namespace_tuple_expansion_fails(self) -> None:
        self.commit_python(NAMESPACE_TUPLE_PYTHON)
        self.write_python(EXPANDED_NAMESPACE_TUPLE_PYTHON)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection family', errors[0])
        self.assertIn('batch_pipeline_preview_jobs', errors[0])
        self.assertIn('backend/database/queue.py:', errors[0])

    def test_namespace_tuple_expansion_with_budget_passes(self) -> None:
        self.commit_python(NAMESPACE_TUPLE_PYTHON)
        self.write_python(EXPANDED_NAMESPACE_TUPLE_PYTHON)
        self.write_registry(budgets=[dict(BUDGET, collection='batch_pipeline_preview_jobs')])
        self.assertEqual(self.evaluate(), [])

    def test_namespace_tuple_expansion_with_exemption_passes(self) -> None:
        self.commit_python(NAMESPACE_TUPLE_PYTHON)
        self.write_python(EXPANDED_NAMESPACE_TUPLE_PYTHON)
        self.write_registry(exempt=[{'collection': 'batch_pipeline_preview_jobs', 'reason': 'fixture exemption'}])
        self.assertEqual(self.evaluate(), [])

    def test_unchanged_namespace_tuple_passes(self) -> None:
        self.commit_python(NAMESPACE_TUPLE_PYTHON)
        self.write_python(
            NAMESPACE_TUPLE_PYTHON
            + "\n\ndef read_user(client, uid):\n    return client.collection('users').document(uid).get()\n"
        )
        self.assertEqual(self.evaluate(), [])

    def test_new_computed_site_with_expanded_tuple_still_needs_a_dynamic_entry(self) -> None:
        self.write_python(EXPANDED_NAMESPACE_TUPLE_PYTHON)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection name', errors[0])
        self.assertNotIn('computed collection family', errors[0])

    def test_unenumerable_family_is_not_flagged(self) -> None:
        self.commit_python(UNBOUND_NAMESPACE_PYTHON)
        self.write_python(
            UNBOUND_NAMESPACE_PYTHON.replace("'batch_pipeline_dev')", "'batch_pipeline_dev', 'batch_pipeline_preview')")
        )
        self.assertEqual(self.evaluate(), [])


class WebSurfaceTests(GuardFixture):
    def test_typescript_literal_collection_fails(self) -> None:
        self.write_web(NEW_QUEUE_WEB)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_dispatch_queue', errors[0])
        self.assertIn('web/admin/lib/queue.ts:', errors[0])

    def test_typescript_const_collection_fails(self) -> None:
        self.write_web(CONST_QUEUE_WEB)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_retry_jobs', errors[0])

    def test_typescript_budgeted_collection_passes(self) -> None:
        self.write_web(NEW_QUEUE_WEB)
        self.write_registry(
            budgets=[
                dict(
                    BUDGET,
                    collection='conversation_dispatch_queue',
                    owner='admin lane',
                    unit='dispatch',
                )
            ]
        )
        self.assertEqual(self.evaluate(), [])

    def test_typescript_template_collection_fails(self) -> None:
        self.write_web(COMPUTED_WEB)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection name', errors[0])
        self.assertIn('`new_${stage}_jobs`', errors[0])

    def test_typescript_template_with_dynamic_entry_passes(self) -> None:
        self.write_web(COMPUTED_WEB)
        self.write_registry(dynamic=[WEB_DYNAMIC])
        self.assertEqual(self.evaluate(), [])

    def test_typescript_static_collection_segments_in_template_are_not_computed(self) -> None:
        self.write_web(STATIC_PATH_WEB)
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn("jobs (matched 'jobs')", errors[0])
        self.assertNotIn('computed collection name', errors[0])

    def test_typescript_existing_collection_is_grandfathered(self) -> None:
        self.write_web(NEW_QUEUE_WEB)
        self.git('add', '-A')
        self.git('commit', '-m', 'existing queue')
        self.write_web(
            NEW_QUEUE_WEB
            + "\n\nexport async function again(id: string) {\n  return getDb().collection(\"conversation_dispatch_queue\").doc(id).get();\n}\n"
        )
        self.assertEqual(self.evaluate(), [])

    def test_typescript_concatenated_constant_fails(self) -> None:
        self.write_web(
            BASE_WEB
            + '\n\nconst NEW_JOBS = "conversation_" + "retry_jobs";\n'
            + "\nexport async function claim(id: string) {\n"
            + "  return getDb().collection(NEW_JOBS).doc(id).get();\n}\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection name', errors[0])
        self.assertIn('NEW_JOBS', errors[0])

    def test_typescript_multiline_concatenated_constant_fails(self) -> None:
        self.write_web(
            BASE_WEB
            + "\n\nconst NEW_JOBS =\n  \"conversation_\" +\n  \"retry_jobs\";\n"
            + "\nexport async function claim(id: string) {\n"
            + "  return getDb().collection(NEW_JOBS).doc(id).get();\n}\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('computed collection name', errors[0])

    def test_typescript_concatenated_constant_with_dynamic_entry_passes(self) -> None:
        self.write_web(
            BASE_WEB
            + '\n\nconst NEW_JOBS = "conversation_" + "retry_jobs";\n'
            + "\nexport async function claim(id: string) {\n"
            + "  return getDb().collection(NEW_JOBS).doc(id).get();\n}\n"
        )
        self.write_registry(dynamic=[dict(WEB_DYNAMIC, expression='NEW_JOBS')])
        self.assertEqual(self.evaluate(), [])

    def test_typescript_as_const_still_resolves(self) -> None:
        self.write_web(
            BASE_WEB
            + '\n\nconst NEW_JOBS = "conversation_retry_jobs" as const;\n'
            + "\nexport async function claim(id: string) {\n"
            + "  return getDb().collection(NEW_JOBS).doc(id).get();\n}\n"
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('conversation_retry_jobs', errors[0])
        self.assertNotIn('computed collection name', errors[0])

    def test_typescript_comment_is_not_a_collection(self) -> None:
        self.write_web(
            BASE_WEB
            + "\n\n// message doc (users/*/messages, rating in {1,-1}) joined to its journal\n"
            + "// a new_dispatch_queue would be a collection if this were code\n"
            + "export const note = 1;\n"
        )
        self.assertEqual(self.evaluate(), [])

    def test_modular_collection_and_doc_paths_resolve(self) -> None:
        self.write_web(MODULAR_WEB)
        self.assertEqual(self.evaluate(), [])

    def test_modular_new_subcollection_fails(self) -> None:
        self.write_web(
            BASE_WEB
            + '\n\nimport { collection } from "firebase/firestore";\n'
            + '\nexport function userJobs(db: unknown, uid: string) {\n  return collection(db, "users", uid, "jobs");\n}\n'
        )
        errors = self.evaluate()
        self.assertEqual(len(errors), 1)
        self.assertIn('jobs', errors[0])


class RegistryValidationTests(GuardFixture):
    def test_incomplete_budget_entry_fails(self) -> None:
        incomplete = dict(BUDGET)
        del incomplete['reads_per_day_budget']
        self.write_registry(budgets=[incomplete])
        _budgets, _exempt, _dynamic, errors = load_registry(self.registry)
        self.assertTrue(any('missing reads_per_day_budget' in error for error in errors), errors)

    def test_non_positive_budget_fails(self) -> None:
        self.write_registry(budgets=[dict(BUDGET, reads_per_unit_budget=0)])
        _budgets, _exempt, _dynamic, errors = load_registry(self.registry)
        self.assertTrue(any('reads_per_unit_budget must be a positive integer' in error for error in errors), errors)

    def test_duplicate_budget_entry_fails(self) -> None:
        self.write_registry(budgets=[BUDGET, BUDGET])
        _budgets, _exempt, _dynamic, errors = load_registry(self.registry)
        self.assertTrue(any('duplicate budget' in error for error in errors), errors)

    def test_budgeted_and_exempt_is_rejected(self) -> None:
        self.write_registry(
            budgets=[BUDGET],
            exempt=[{'collection': BUDGET['collection'], 'reason': 'contradiction'}],
        )
        _budgets, _exempt, _dynamic, errors = load_registry(self.registry)
        self.assertTrue(any('both declared and exempt' in error for error in errors), errors)

    def test_dynamic_entry_requires_pattern_and_budget(self) -> None:
        incomplete = dict(DYNAMIC)
        del incomplete['collection_pattern']
        self.write_registry(dynamic=[incomplete])
        _budgets, _exempt, _dynamic, errors = load_registry(self.registry)
        self.assertTrue(any('missing collection_pattern' in error for error in errors), errors)

    def test_dynamic_entry_requires_positive_budget(self) -> None:
        self.write_registry(dynamic=[dict(DYNAMIC, reads_per_day_budget=0)])
        _budgets, _exempt, _dynamic, errors = load_registry(self.registry)
        self.assertTrue(any('reads_per_day_budget must be a positive integer' in error for error in errors), errors)

    def test_missing_registry_fails_closed(self) -> None:
        self.registry.unlink()
        _budgets, _exempt, _dynamic, errors = load_registry(self.registry)
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
        _budgets, _exempt, _dynamic, errors = load_registry(root / '.github' / 'firestore-collection-budgets.json')
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
            for path in ('backend/database/new_queue.py', 'web/admin/lib/new-queue.ts'):
                selected = resolve_checks(manifest, [path], lane, include_pr_body_checks=False)
                self.assertIn(check, selected, (lane, path))


if __name__ == '__main__':
    unittest.main()

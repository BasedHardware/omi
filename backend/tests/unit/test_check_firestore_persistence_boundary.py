"""Tests for the Firestore persistence-boundary AST ratchet (WP1 seal)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_firestore_persistence_boundary.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    # CI checks out the full repo, so the boundary guard still runs there.
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_firestore_persistence_boundary', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_flags_forbidden_client_and_sdk_imports():
    source = '''
import database._client
from database._client import db, run_transactional
from google.cloud import firestore
from google.cloud.firestore_v1 import Increment
import google.cloud.firestore
from firebase_admin import firestore as fb_firestore
'''
    # 6 forbidden import statements above.
    assert _MODULE.count_boundary_violations(source) == 6


def test_flags_parent_package_client_and_sdk_imports():
    # Regression: parent-package import forms bypassed the seal — ``from google.cloud import
    # firestore_v1`` (versioned client, not the literal ``firestore`` member) and ``from database
    # import _client`` (raw client via its parent package).
    source = '''
from google.cloud import firestore_v1
from database import _client
'''
    assert _MODULE.count_boundary_violations(source) == 2


def test_flags_raw_ops_regardless_of_receiver():
    source = '''
snapshot = db_client.document(path).get()
rows = client.collection(name).stream()
hit = db.collection_group("events").where("k", "==", v)
txn = self._db_client.transaction()
'''
    # 4 raw persistence-op method calls.
    assert _MODULE.count_boundary_violations(source) == 4


def test_flags_firestore_sentinels_import():
    # Regression (CR PR#10887): ``database.sentinels`` re-exports Firestore SDK sentinels
    # (DELETE_FIELD, …) that are stored as literals on the Mongo adapter; domain code must use
    # the neutral ``database.store.sentinels``. Both import forms must be flagged.
    source = '''
from database.sentinels import DELETE_FIELD
from database import sentinels
'''
    assert _MODULE.count_boundary_violations(source) == 2


def test_ignores_blessed_database_ports_and_unrelated_code():
    source = '''
from database import document_store
from database.store.sentinels import DELETE
from database.firestore_errors import is_document_size_limit_error
from database.document_ids import document_id_from_seed

snap = document_store.get_document(db_client, path)
document_store.set_document(db_client, path, data)
value = some_dict.get("key")
router.include_router(other)
'''
    assert _MODULE.count_boundary_violations(source) == 0


def test_collect_counts_excludes_boundary_and_allowlisted_dirs(tmp_path):
    backend = tmp_path / 'backend'
    for rel in ('database', 'tests', 'testing', 'scripts', 'agent-proxy', 'routers'):
        (backend / rel).mkdir(parents=True)
    leak = 'from database._client import db\nx = db.document("p").get()\n'
    (backend / 'database' / 'users.py').write_text(leak)          # boundary: allowed
    (backend / 'tests' / 'test_x.py').write_text(leak)            # tests: allowed
    (backend / 'testing' / 'harness.py').write_text(leak)         # testing: allowed
    (backend / 'scripts' / 'oneoff.py').write_text(leak)          # scripts: allowed
    (backend / 'agent-proxy' / 'main.py').write_text(leak)        # separate service: allowed
    (backend / 'routers' / 'leaky.py').write_text(leak)           # runtime router: FLAGGED

    counts = _MODULE.collect_counts(tmp_path, Path('backend'))
    assert counts == {'backend/routers/leaky.py': 2}


def test_reports_only_count_increases_over_baseline():
    assert _MODULE.violations({'backend/routers/x.py': 2}, {'backend/routers/x.py': 1}) == [
        'backend/routers/x.py: found 2, baseline allows 1'
    ]
    assert _MODULE.violations({'backend/routers/x.py': 1}, {'backend/routers/x.py': 1}) == []

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


def test_allows_facade_accessor_and_sdk_imports():
    # ADR-0044: obtaining the facade (``from database._client import db``) and importing the Firestore
    # SDK for constants/decorators/FieldFilter are BOTH allowed — ``db`` is the neutral facade proxy
    # and the SDK values are consumed by it. None of these is a raw-client construction.
    source = '''
import database._client
from database._client import db, run_transactional, get_firestore_client
from database import _client
from google.cloud import firestore
from google.cloud.firestore_v1 import Increment, transactional
import google.cloud.firestore
from firebase_admin import firestore as fb_firestore
'''
    assert _MODULE.count_boundary_violations(source) == 0


def test_allows_facade_ops_and_flags_raw_client_construction():
    # ADR-0044: ``.document()/.collection()/.transaction()`` on the injected facade are allowed; what
    # stays forbidden is constructing a RAW SDK client (the only way to bypass the facade).
    allowed = '''
snapshot = db_client.document(path).get()
rows = client.collection(name).stream()
hit = db.collection_group("events").where("k", "==", v)
txn = self._db_client.transaction()
order = firestore.Query.DESCENDING
stamp = firestore.SERVER_TIMESTAMP
'''
    assert _MODULE.count_boundary_violations(allowed) == 0

    forbidden = '''
a = firestore.Client()
b = firestore.AsyncClient()
c = firestore_v1.Client(project="p")
d = firebase_admin.firestore.client()
'''
    assert _MODULE.count_boundary_violations(forbidden) == 4


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
    # A raw SDK client construction is the forbidden leak (ADR-0044); facade use around it is fine.
    leak = 'from google.cloud import firestore\ndb = firestore.Client()\nx = db.document("p").get()\n'
    (backend / 'database' / 'users.py').write_text(leak)          # boundary: allowed
    (backend / 'tests' / 'test_x.py').write_text(leak)            # tests: allowed
    (backend / 'testing' / 'harness.py').write_text(leak)         # testing: allowed
    (backend / 'scripts' / 'oneoff.py').write_text(leak)          # scripts: allowed
    (backend / 'agent-proxy' / 'main.py').write_text(leak)        # separate service: allowed
    (backend / 'routers' / 'leaky.py').write_text(leak)           # runtime router: FLAGGED

    counts = _MODULE.collect_counts(tmp_path, Path('backend'))
    assert counts == {'backend/routers/leaky.py': 1}


def test_reports_only_count_increases_over_baseline():
    assert _MODULE.violations({'backend/routers/x.py': 2}, {'backend/routers/x.py': 1}) == [
        'backend/routers/x.py: found 2, baseline allows 1'
    ]
    assert _MODULE.violations({'backend/routers/x.py': 1}, {'backend/routers/x.py': 1}) == []


def test_migrations_are_no_longer_excluded_from_the_boundary():
    # Regression: excluding migrations/ let a re-added migration use raw Firestore undetected.
    assert 'migrations/' not in _MODULE.EXCLUDED_PREFIXES


def test_load_baseline_rejects_boolean_counts(tmp_path):
    import json

    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps({'backend/x.py': True}))
    with pytest.raises(ValueError):
        _MODULE.load_baseline(path)

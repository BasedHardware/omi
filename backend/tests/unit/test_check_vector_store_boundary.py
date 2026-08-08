"""Tests for the vector-store boundary AST ratchet (WP4 seal, ADR-0033/D-vector)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_vector_store_boundary.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    # CI checks out the full repo, so the boundary guard still runs there.
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_vector_store_boundary', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_flags_forbidden_pinecone_imports():
    source = '''
import pinecone
from pinecone import Pinecone
from pinecone.grpc import PineconeGRPC
import langchain_pinecone
from langchain_pinecone import PineconeVectorStore
'''
    # 5 forbidden import statements above.
    assert _MODULE.count_boundary_violations(source) == 5


def test_flags_dynamic_pinecone_imports():
    # Regression: literal dynamic-import forms bypassed the static import check.
    source = '''
import importlib
importlib.import_module('pinecone')
__import__('langchain_pinecone')
'''
    assert _MODULE.count_boundary_violations(source) == 2


def test_ignores_the_neutral_port_and_unrelated_code():
    source = '''
from utils.vector import get_vector_store, VectorRecord

store = get_vector_store()
store.upsert("ns2", records)                 # port verbs named upsert/query must NOT trip the guard
hits = store.query("ns2", vector, top_k=5)
store.delete_by_ids("ns2", ["a"])
rows = db.query("SELECT 1")                   # unrelated "query" method
'''
    assert _MODULE.count_boundary_violations(source) == 0


def test_collect_counts_excludes_boundary_and_allowlisted_dirs(tmp_path):
    backend = tmp_path / 'backend'
    for rel in ('utils/vector', 'tests', 'testing', 'scripts', 'agent-proxy', 'routers'):
        (backend / rel).mkdir(parents=True)
    leak = 'from pinecone import Pinecone\nx = Pinecone(api_key="k").Index("i")\n'
    (backend / 'utils' / 'vector' / 'adapters.py').write_text(leak)  # boundary: allowed
    (backend / 'tests' / 'test_x.py').write_text(leak)               # tests: allowed
    (backend / 'testing' / 'harness.py').write_text(leak)            # testing: allowed
    (backend / 'scripts' / 'rag.py').write_text(leak)                # scripts (incl. rag): allowed
    (backend / 'agent-proxy' / 'main.py').write_text(leak)           # separate service: allowed
    (backend / 'routers' / 'leaky.py').write_text(leak)              # runtime router: FLAGGED

    counts = _MODULE.collect_counts(tmp_path, Path('backend'))
    assert counts == {'backend/routers/leaky.py': 1}


def test_reports_only_count_increases_over_baseline():
    assert _MODULE.violations({'backend/routers/x.py': 2}, {'backend/routers/x.py': 1}) == [
        'backend/routers/x.py: found 2, baseline allows 1'
    ]
    assert _MODULE.violations({'backend/routers/x.py': 1}, {'backend/routers/x.py': 1}) == []


def test_keyword_form_dynamic_import_is_flagged():
    # Regression: import_module(name='pinecone') dodged the positional-only check.
    assert _MODULE.count_boundary_violations("import importlib\nimportlib.import_module(name='pinecone')\n") == 1


def test_unrelated_import_module_method_is_not_a_false_positive():
    # A helper method named import_module (not importlib.import_module) must not be flagged.
    assert _MODULE.count_boundary_violations("self.import_module('pinecone')\nreg.import_module('pinecone')\n") == 0


def test_load_baseline_rejects_boolean_counts(tmp_path):
    import json

    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps({'backend/x.py': True}))
    with pytest.raises(ValueError):
        _MODULE.load_baseline(path)

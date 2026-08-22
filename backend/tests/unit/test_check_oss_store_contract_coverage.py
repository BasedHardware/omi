"""Tests for the dual-backend contract-coverage inventory (ADR-0044 facade, ADR-0002 store port).

The guard's job is to make one thing impossible: a `database/` module using a query shape the facade
must *translate* (composite filter, cursor, projection, aggregation, transaction, batch, atomic field
op, collection group) while no dual-backend contract test drives it. That combination is exactly what
let `database/apps.py` 500 every marketplace query under STORAGE_BACKEND=mongo with a green suite.

These tests drive the pure `check`/`detail` functions over source strings, so they are hermetic.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_oss_store_contract_coverage.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    # CI checks out the full repo, so the guard still runs there.
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_oss_store_contract_coverage', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


THE_SHIPPED_DEFECT = '''
from google.cloud.firestore_v1 import BaseCompositeFilter, FieldFilter

def get_public_approved_apps_db():
    return (
        db.collection('plugins_data')
        .where(filter=BaseCompositeFilter('AND', [FieldFilter('approved', '==', True)]))
        .stream()
    )
'''


def test_names_every_at_risk_shape():
    source = '''
from google.cloud import firestore
from google.cloud.firestore_v1 import BaseCompositeFilter

@firestore.transactional
def _tx(transaction, uid):
    pass

def reads(uid):
    q = db.collection('c').where(filter=BaseCompositeFilter('AND', [])).select(['a']).start_after(cursor)
    q.count().get()
    db.collection_group('items').stream()
    batch = db.batch()
    batch.update(ref, {'tags': firestore.ArrayUnion(['x']), 'n': firestore.Increment(1)})
'''
    assert _MODULE.module_shapes(source) == {
        'composite_filter',
        'cursor',
        'projection',
        'aggregation',
        'transaction',
        'batch',
        'atomic_field_ops',
        'collection_group',
    }


def test_a_plain_module_is_not_at_risk():
    """Shapes the facade passes straight through must not inflate the inventory."""
    source = '''
from google.cloud.firestore_v1 import FieldFilter

def get(uid):
    doc = db.collection('users').document(uid).get()
    rows = db.collection('users').where(filter=FieldFilter('uid', '==', uid)).order_by('created_at').limit(10).stream()
    db.collection('users').document(uid).set({'a': 1}, merge=True)
    db.collection('users').document(uid).delete()
'''
    assert _MODULE.module_shapes(source) == set()


def test_the_shipped_defect_is_flagged_when_uncovered():
    """The regression this guard exists for: apps.py's composite filter with no contract test."""
    counts = _MODULE.check({'apps': THE_SHIPPED_DEFECT}, {})
    assert counts == {'apps': 1}
    assert _MODULE.detail({'apps': THE_SHIPPED_DEFECT}, {})['apps'] == ['composite_filter']


@pytest.mark.parametrize(
    'contract_source',
    [
        'import database.apps as apps_db',
        'import database.apps',
        'from database import apps',
        'from database.apps import get_public_approved_apps_db',
    ],
)
def test_a_contract_test_clears_the_module_however_it_imports_it(contract_source):
    counts = _MODULE.check({'apps': THE_SHIPPED_DEFECT}, {'tests/contract/test_apps_contract.py': contract_source})
    assert counts == {}


def test_a_contract_test_for_a_sibling_does_not_clear_the_module():
    """Reviving users/conversations was necessary but not sufficient — neither uses a composite filter."""
    counts = _MODULE.check(
        {'apps': THE_SHIPPED_DEFECT},
        {'tests/contract/test_users_people_contract.py': 'import database.users as users_db'},
    )
    assert counts == {'apps': 1}


def test_infrastructure_modules_are_excluded():
    """The facade, the port and the other datastores have their own guards; counting them is noise."""
    for name in ('_client', 'document_store', 'vector_db', 'redis_db', 'helpers'):
        assert _MODULE.check({name: THE_SHIPPED_DEFECT}, {}) == {}


def test_transaction_is_detected_in_every_form_it_reaches_the_facade():
    """The L24 hole: a transaction handed to the facade as a decorator, a kwarg or a parameter."""
    assert _MODULE.module_shapes('@firestore.transactional\ndef f(transaction):\n    pass\n') == {'transaction'}
    assert _MODULE.module_shapes('def f(tx):\n    q.stream(transaction=tx)\n') == {'transaction'}
    assert _MODULE.module_shapes('def f(transaction, uid):\n    pass\n') == {'transaction'}


def test_shapes_inside_a_comment_or_string_do_not_count():
    """AST-based, not grep-based: prose about a shape is not a use of it."""
    source = '''
# db.collection('c').where(filter=BaseCompositeFilter('AND', [])) — what we deliberately avoid here
DOC = """use .count() instead"""
'''
    assert _MODULE.module_shapes(source) == set()


def test_syntax_error_does_not_crash_either_side():
    assert _MODULE.module_shapes('def broken(:\n') == set()
    assert _MODULE.contract_covered_modules({'t.py': 'import ('}) == set()


def test_violations_ratchet_against_the_baseline():
    counts = {'chat': 6, 'memories': 4}
    assert _MODULE.violations(counts, {'chat': 6, 'memories': 4}) == []
    assert _MODULE.violations(counts, {'chat': 6, 'memories': 3}) == [
        'database/memories.py: 4 at-risk shape(s) with no contract test, baseline allows 3'
    ]
    assert len(_MODULE.violations(counts, {})) == 2


def test_baseline_shape_is_validated(tmp_path):
    good = tmp_path / 'good.json'
    good.write_text('{"chat": 6}')
    assert _MODULE.load_baseline(good) == {'chat': 6}
    assert _MODULE.load_baseline(tmp_path / 'absent.json') == {}
    bad = tmp_path / 'bad.json'
    bad.write_text('{"chat": -1}')
    with pytest.raises(ValueError):
        _MODULE.load_baseline(bad)


def test_a_baseline_entry_that_outlived_its_debt_is_a_failure():
    """The ratchet's other direction. Without it the number only falls when somebody remembers to edit
    the file, so a module that has just been covered keeps appearing on the worklist and the reported
    debt drifts away from the measurement — which is how L32's list rotted into noise."""
    counts = {'chat': 6}

    assert _MODULE.stale(counts, {'chat': 6}) == []
    assert _MODULE.stale(counts, {'chat': 6, 'action_items': 4}) == [
        'database/action_items.py: baseline claims 4 uncovered shape(s), measured 0'
    ]
    assert _MODULE.stale(counts, {'chat': 7}) == ['database/chat.py: baseline claims 7 uncovered shape(s), measured 6']


def test_the_repository_is_at_or_below_its_baseline():
    """The ratchet itself, on the real tree — the check CI runs."""
    root = Path(__file__).resolve().parents[3]
    domain, contract = _MODULE._read_sources(root, _MODULE.DEFAULT_SCAN_ROOT)
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    counts = _MODULE.check(domain, contract)
    assert _MODULE.violations(counts, baseline) == []
    assert _MODULE.stale(counts, baseline) == [], 'the baseline must equal the measurement, not exceed it'


def test_a_python_list_tally_is_not_a_document_store_aggregation():
    """`.count(` matched anything, so `ordered_outcomes.count('imported')` — a plain list tally — was
    reported as a Firestore aggregation. `workstreams.py` carried an `aggregation` shape it does not
    have, and the worklist would have asked for a contract test of something that is not there.

    The discriminator is exact, not heuristic: Firestore's aggregation is `.count()` or
    `.count(alias=...)` and never takes a positional argument, while `list.count(x)` always does.
    Measured across every `.count(` in `database/` — 19 zero-arg Firestore calls, one one-arg tally.
    """
    source = """
def real(collection):
    return collection.where('a', '==', 1).count().get()

def tally(values):
    return values.count('imported')
"""

    assert 'aggregation' in _MODULE.module_shapes(source)

    tally_only = """
def tally(values):
    return values.count('imported') + values.count('failed')
"""

    assert 'aggregation' not in _MODULE.module_shapes(tally_only)

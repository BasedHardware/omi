"""Tests for the auth boundary AST ratchet (WP3 seal, ADR-0034)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_auth_boundary.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_auth_boundary', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_flags_firebase_auth_imports_and_attribute_access():
    source = '''
import firebase_admin.auth
from firebase_admin import auth
from firebase_admin.auth import InvalidIdTokenError
firebase_admin.auth.verify_id_token(token)
'''
    # 4 forbidden: import firebase_admin.auth, from firebase_admin import auth,
    # from firebase_admin.auth import ..., and the firebase_admin.auth attribute access.
    assert _MODULE.count_boundary_violations(source) == 4


def test_flags_aliased_firebase_admin_auth_access():
    # Regression: ``import firebase_admin as fb; fb.auth.verify_id_token(...)`` bypassed the guard
    # because the ``fb.auth`` attribute access was matched only against the literal ``firebase_admin``.
    source = '''
import firebase_admin as fb
fb.auth.verify_id_token(token)
'''
    assert _MODULE.count_boundary_violations(source) == 1


def test_ignores_non_auth_firebase_and_the_port():
    source = '''
import firebase_admin
from firebase_admin import messaging
from utils.auth import get_auth_provider

firebase_admin.initialize_app()          # bootstrap, not auth
messaging.send(m)                         # push (ADR-0011)
get_auth_provider().verify_token(token)   # the neutral port
p = obj.auth                              # an unrelated ".auth" attribute must not trip the guard
'''
    assert _MODULE.count_boundary_violations(source) == 0


def test_collect_counts_excludes_boundary_and_allowlisted_dirs(tmp_path):
    backend = tmp_path / 'backend'
    for rel in ('utils/auth', 'tests', 'testing', 'scripts', 'agent-proxy', 'pusher', 'routers'):
        (backend / rel).mkdir(parents=True)
    leak = 'from firebase_admin import auth\nuid = auth.verify_id_token(t)["uid"]\n'
    (backend / 'utils' / 'auth' / 'adapters.py').write_text(leak)  # boundary: allowed
    (backend / 'tests' / 'test_x.py').write_text(leak)             # tests: allowed
    (backend / 'testing' / 'harness.py').write_text(leak)          # testing: allowed
    (backend / 'scripts' / 'oneoff.py').write_text(leak)           # scripts: allowed
    (backend / 'agent-proxy' / 'main.py').write_text(leak)         # separate service: allowed
    (backend / 'pusher' / 'main.py').write_text(leak)              # separate service: allowed
    (backend / 'routers' / 'leaky.py').write_text(leak)            # runtime router: FLAGGED

    counts = _MODULE.collect_counts(tmp_path, Path('backend'))
    assert counts == {'backend/routers/leaky.py': 1}


def test_reports_only_count_increases_over_baseline():
    assert _MODULE.violations({'backend/routers/x.py': 2}, {'backend/routers/x.py': 1}) == [
        'backend/routers/x.py: found 2, baseline allows 1'
    ]
    assert _MODULE.violations({'backend/routers/x.py': 1}, {'backend/routers/x.py': 1}) == []


def test_literal_dynamic_import_of_firebase_auth_is_flagged():
    # Regression: importlib.import_module('firebase_admin.auth') had no visit_Call to catch it.
    assert _MODULE.count_boundary_violations("import importlib\nimportlib.import_module('firebase_admin.auth')\n") == 1


def test_propagated_alias_reaches_the_auth_surface():
    # Regression: an alias rebound by assignment (x = fb) still reaches .auth.
    assert _MODULE.count_boundary_violations("import firebase_admin as fb\nx = fb\nx.auth.verify_id_token(t)\n") == 1


def test_load_baseline_rejects_boolean_counts(tmp_path):
    import json

    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps({'backend/x.py': True}))
    with pytest.raises(ValueError):
        _MODULE.load_baseline(path)

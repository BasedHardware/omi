"""Tests for the auth boundary AST ratchet (WP3 seal, ADR-0034)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_oss_auth_boundary.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_oss_auth_boundary', _SCRIPT)
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


def test_migrations_are_no_longer_excluded_from_the_boundary():
    # Regression (cubic 4948841169 F6): excluding migrations/ let a re-added migration reach
    # firebase_admin.auth undetected. Parity with the Firestore persistence guard.
    assert 'migrations/' not in _MODULE.EXCLUDED_PREFIXES


# --- edge-case bypasses closed per cubic review PR 10887 ---


def test_with_context_expression_auth_access_is_flagged():
    # withitem is neither ast.stmt nor ast.expr; the ``with fb.auth...()`` context was missed before.
    src = "import firebase_admin as fb\nwith fb.auth.lock() as l:\n    pass\n"
    assert _MODULE.count_boundary_violations(src) == 1


def test_match_case_guard_auth_access_is_flagged():
    src = "import firebase_admin as fb\nmatch x:\n    case 1 if fb.auth.verify(t):\n        pass\n"
    assert _MODULE.count_boundary_violations(src) == 1


def test_class_attribute_does_not_shadow_module_alias_in_methods():
    # A class attribute named ``fb`` must not hide the module alias inside a method — a bare ``fb``
    # there is the module import, not the class attribute.
    src = "import firebase_admin as fb\nclass C:\n    fb = other\n    def m(self):\n        fb.auth.verify(t)\n"
    assert _MODULE.count_boundary_violations(src) == 1


def test_conditional_rebind_keeps_the_not_rebound_path_visible():
    rebound_one_branch = "import firebase_admin as fb\nif cond:\n    fb = build()\nfb.auth.verify(t)\n"
    assert _MODULE.count_boundary_violations(rebound_one_branch) == 1
    rebound_all_branches = (
        "import firebase_admin as fb\nif cond:\n    fb = build()\nelse:\n    fb = other()\nfb.auth.verify(t)\n"
    )
    assert _MODULE.count_boundary_violations(rebound_all_branches) == 0


# --- edge-case bypasses closed per cubic review 4948841169 ---


def test_flags_aliased_dynamic_import_of_firebase_auth():
    # F3: ``im = importlib.import_module; im('firebase_admin.auth')`` dodged the dynamic-import check
    # because the alias ``im`` was never tracked (only the literal import_module/__import__ receivers).
    src = "import importlib\nim = importlib.import_module\nim('firebase_admin.auth')\n"
    assert _MODULE.count_boundary_violations(src) == 1


def test_tuple_unpack_propagates_firebase_alias():
    # F4: tuple-unpack ``a, fb = 1, firebase_admin`` bound nothing before (target was not a bare Name),
    # so a later ``fb.auth`` was missed.
    src = "import firebase_admin\na, fb = 1, firebase_admin\nfb.auth.verify(t)\n"
    assert _MODULE.count_boundary_violations(src) == 1
    # And the non-alias element must NOT become an alias.
    clean = "import firebase_admin\nfb, a = firebase_admin, other\na.auth.verify(t)\n"
    assert _MODULE.count_boundary_violations(clean) == 0


def test_walrus_assignment_propagates_firebase_alias():
    # F4: a walrus ``(fb := firebase_admin)`` binds a name from an expression; the later ``fb.auth``
    # was missed because expressions never rebound before.
    src = "import firebase_admin\n(fb := firebase_admin)\nfb.auth.verify(t)\n"
    assert _MODULE.count_boundary_violations(src) == 1


def test_match_value_pattern_auth_access_is_flagged():
    # F5: a ``MatchValue`` value pattern reaching the auth surface (``case fb.auth.X:``) was never
    # scanned (only the guard/body were). Patterns forbid calls, so this is the narrow completeness gap.
    src = "import firebase_admin as fb\nmatch x:\n    case fb.auth.INVALID:\n        pass\n"
    assert _MODULE.count_boundary_violations(src) == 1


def test_match_as_capture_of_firebase_subject_propagates_alias():
    # F5: capturing a firebase-aliased subject (``match fb: case obj:``) must rebind the capture to the
    # package alias so a ``obj.auth`` in the guard/body is caught.
    guard = "import firebase_admin as fb\nmatch fb:\n    case obj if obj.auth.verify(t):\n        pass\n"
    assert _MODULE.count_boundary_violations(guard) == 1
    body = "import firebase_admin as fb\nmatch fb:\n    case obj:\n        obj.auth.verify(t)\n"
    assert _MODULE.count_boundary_violations(body) == 1
    # A capture of a NON-firebase subject must not become an alias.
    clean = "import firebase_admin as fb\nmatch other:\n    case obj:\n        obj.auth.verify(t)\n"
    assert _MODULE.count_boundary_violations(clean) == 0


# --- the coverage boundary, measured -------------------------------------------------------------
# The audit that produced BACKLOG L16 reported "11 of 14 bypass shapes are invisible". Measured, it was
# the other way round: 10 of 14 were already seen, and the shape it called "the idiom the adapter itself
# uses" (a helper returning the `auth` MODULE) was one of them. These tests pin what the guard sees AND
# what it deliberately does not, so the next reader does not have to re-measure — or mistake a decision
# for an oversight.


def test_every_realistic_shape_is_seen():
    seen = {
        'import firebase_admin.auth': 'import firebase_admin.auth\nfirebase_admin.auth.verify_id_token(t)\n',
        'from firebase_admin.auth import x': 'from firebase_admin.auth import verify_id_token\nverify_id_token(t)\n',
        'from firebase_admin import auth': 'from firebase_admin import auth\nauth.verify_id_token(t)\n',
        'package attribute': 'import firebase_admin\nfirebase_admin.auth.verify_id_token(t)\n',
        'aliased package': 'import firebase_admin as fb\nfb.auth.verify_id_token(t)\n',
        'lazy accessor returning the auth module': (
            'def _auth():\n    from firebase_admin import auth\n    return auth\n_auth().verify_id_token(t)\n'
        ),
        'from..import auth as alias': 'from firebase_admin import auth as fa\nfa.verify_id_token(t)\n',
        'module-level indirection': 'import firebase_admin\n_FB = firebase_admin\n_FB.auth.verify_id_token(t)\n',
        'literal importlib': (
            "import importlib\nimportlib.import_module('firebase_admin.auth').verify_id_token(t)\n"
        ),
        'walrus': 'import firebase_admin\nif (fb := firebase_admin):\n    fb.auth.verify_id_token(t)\n',
    }
    invisible = [name for name, source in seen.items() if _MODULE.count_boundary_violations(source) == 0]
    assert invisible == [], f'these shapes stopped being detected: {invisible}'


def test_handing_the_package_out_is_seen_now():
    """The one realistic blind spot that L16 was pointing at, from the wrong end.

    `def _fb(): return firebase_admin` makes every later `_fb().auth` invisible, because the attribute is
    then on a Call and attribute tracking works on names. The codebase already uses a lazy-accessor idiom
    (returning the auth module), so a variant returning the package is one small step away. Catching the
    provider side is tractable; the consumer side is not.
    """
    source = 'import firebase_admin\ndef _fb():\n    return firebase_admin\n_fb().auth.verify_id_token(t)\n'
    assert _MODULE.count_boundary_violations(source) == 1


def test_returning_the_package_does_not_false_positive_on_anything_else():
    """Returning the package has no legitimate use outside utils/auth/; returning other things does."""
    assert _MODULE.count_boundary_violations('import firebase_admin\ndef b():\n    return {"a": 1}\n') == 0
    assert _MODULE.count_boundary_violations('import firebase_admin\ndef b():\n    c = make()\n    return c\n') == 0
    # messaging is explicitly allowed (push, ADR-0011) and must stay allowed.
    messaging = 'import firebase_admin\ndef m():\n    return firebase_admin.messaging\n'
    assert _MODULE.count_boundary_violations(messaging) == 0


def test_the_dynamic_shapes_are_deliberately_not_detected():
    """Recorded as a DECISION, not an oversight: nothing in the tree writes these, product code has no
    reason to, and chasing every dynamic shape turns a precise guard into a false-positive machine. If one
    ever appears in a merge, this test is where to change the answer."""
    undetected = {
        'getattr on the package': "import firebase_admin\ngetattr(firebase_admin, 'auth').verify_id_token(t)\n",
        'sys.modules': "import sys\nsys.modules['firebase_admin'].auth.verify_id_token(t)\n",
        'package inside a container': (
            "import firebase_admin\nM = {'fb': firebase_admin}\nM['fb'].auth.verify_id_token(t)\n"
        ),
    }
    for name, source in undetected.items():
        assert _MODULE.count_boundary_violations(source) == 0, f'{name} is now detected — update this test'

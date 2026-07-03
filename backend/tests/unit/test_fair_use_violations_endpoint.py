"""GET /v1/fair-use/violations returns the caller's rolling fair-use event counts.

Complements /v1/fair-use/status with how many fair-use events the user has had in the
last 7 and 30 days, reusing the existing get_violation_counts helper.

Test isolation: routers.fair_use_admin imports cleanly, so the test imports it normally,
patches the import-cheap fair_use_db helper with monkeypatch.setattr, and calls the
handler directly (no sys.modules mutation, no TestClient).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import fair_use_admin as fu_mod  # noqa: E402


def test_violations_returns_counts(monkeypatch):
    counts = {'violation_count_7d': 2, 'violation_count_30d': 5}
    monkeypatch.setattr(fu_mod.fair_use_db, 'get_violation_counts', lambda uid: counts)
    assert fu_mod.get_my_fair_use_violations(uid='u1') == counts


def test_violations_scopes_to_caller_uid(monkeypatch):
    seen = {}

    def fake(uid):
        seen['uid'] = uid
        return {'violation_count_7d': 0, 'violation_count_30d': 0}

    monkeypatch.setattr(fu_mod.fair_use_db, 'get_violation_counts', fake)
    fu_mod.get_my_fair_use_violations(uid='user-42')
    assert seen['uid'] == 'user-42'

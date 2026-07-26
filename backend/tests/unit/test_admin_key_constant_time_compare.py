"""Admin-key checks in memory_admin.py and notifications.py must use constant-time
comparison and fail closed when ADMIN_KEY is unset/empty.

Both previously did a plain `secret_key != os.getenv('ADMIN_KEY')` comparison — a timing
side-channel on the admin secret, inconsistent with routers/fair_use_admin.py's
_verify_admin_key, which already used hmac.compare_digest plus an explicit `not ADMIN_KEY`
guard. Source-level structural check: both files have heavy import graphs (Firestore,
job orchestration), matching the approach used elsewhere for payment.py/imports.py.
"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (BACKEND_ROOT / relative_path).read_text(encoding="utf-8")


def test_memory_admin_uses_constant_time_compare():
    source = _source("routers/memory_admin.py")
    start = source.index("def _require_admin_key")
    end = source.index("\ndef ", start + 1)
    func = source[start:end]

    assert "hmac.compare_digest" in func, "_require_admin_key must use hmac.compare_digest, not `!=`"
    assert "secret_key !=" not in func, "_require_admin_key must not compare the admin key with plain `!=`"
    assert "not admin_key" in func or "not os.getenv" in func, "_require_admin_key must fail closed when ADMIN_KEY is unset/empty"


def test_notifications_uses_constant_time_compare():
    source = _source("routers/notifications.py")
    start = source.index("def send_notification_to_user")
    end = source.index("\ndef ", start + 1)
    func = source[start:end]

    assert "hmac.compare_digest" in func, "send_notification_to_user must use hmac.compare_digest, not `!=`"
    assert "secret_key !=" not in func, "send_notification_to_user must not compare the admin key with plain `!=`"
    assert "not admin_key" in func or "not os.getenv" in func, "send_notification_to_user must fail closed when ADMIN_KEY is unset/empty"


def test_hmac_imported_in_both_modules():
    assert "import hmac" in _source("routers/memory_admin.py")
    assert "import hmac" in _source("routers/notifications.py")

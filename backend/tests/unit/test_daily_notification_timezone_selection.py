"""Regression test for utils.other.notifications._get_timezones_at_time.

The daily morning reminder selected recipient timezones by an exact "HH:MM"
string match against "08:00". The cron fires at the top of each UTC hour, so
every sub-hour-offset timezone (India +5:30, Nepal +5:45, Iran +3:30, ...) read
"08:30"/"08:45" and was silently excluded. The fix matches on the local hour,
like the sibling _get_timezones_grouped_by_hour already does.

notifications.py pulls heavy deps at import, so the leaf modules it imports are
stubbed (parent packages stay on their real paths so the module resolves from
disk). pytz is kept real because the test depends on actual UTC offsets.
"""

import datetime as _dt
import os
import sys
import types
from datetime import timezone
from unittest.mock import MagicMock, patch

import pytz  # real dependency: the test needs actual timezone offsets

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENCRYPTION_SECRET", "omi_test_secret")


def _real_pkg(name, *relpath):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    mod.__path__ = [os.path.join(_BACKEND, *relpath)]
    return mod


def _stub_leaf(name):
    sys.modules[name] = MagicMock(name=name)


# Snapshot sys.modules first so the stubs below do not leak into other test files during
# bulk ``pytest tests/unit/`` collection (issue #8661); restored right after the import.
_SYS_MODULES_SNAPSHOT = dict(sys.modules)

for _pkg, _rel in [
    ("utils", ("utils",)),
    ("utils.other", ("utils", "other")),
    ("utils.conversations", ("utils", "conversations")),
    ("utils.llm", ("utils", "llm")),
    ("database", ("database",)),
    ("models", ("models",)),
]:
    _real_pkg(_pkg, *_rel)

for _leaf in [
    "utils.executors",
    "utils.conversations.factory",
    "utils.llm.external_integrations",
    "utils.notifications",
    "utils.subscription",
    "utils.webhooks",
    "database.chat",
    "database.conversations",
    "database.notifications",
    "database.redis_db",
    "database.daily_summaries",
    "models.notification_message",
    "models.conversation",
]:
    _stub_leaf(_leaf)

import utils.other.notifications as notif  # noqa: E402

# Restore sys.modules so the stubs above do not leak into other test files during bulk
# collection (issue #8661). ``notif`` is already bound to the stubbed deps, and the test
# patches ``notif.datetime`` directly, so the restore does not change behaviour.
for _name in list(sys.modules):
    if _name in _SYS_MODULES_SNAPSHOT:
        if sys.modules[_name] is not _SYS_MODULES_SNAPSHOT[_name]:
            sys.modules[_name] = _SYS_MODULES_SNAPSHOT[_name]
    else:
        del sys.modules[_name]
del _SYS_MODULES_SNAPSHOT


class _FixedDateTime:
    """datetime stand-in whose now(tz) is a fixed 03:00 UTC instant.

    At 03:00 UTC the local hour is 8 for every +5:00 / +5:30 / +5:45 zone, which
    is exactly the set that exposes the sub-hour-offset bug.
    """

    _fixed = _dt.datetime(2026, 6, 29, 3, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls._fixed
        return cls._fixed.astimezone(tz)


def test_sub_hour_offset_timezones_are_included_at_target_hour():
    with patch.object(notif, "datetime", _FixedDateTime):
        result = notif._get_timezones_at_time("08:00")

    # Whole-hour offset: selected before and after the fix.
    assert "Asia/Karachi" in result  # +5:00 -> 08:00
    # Sub-hour offsets: dropped by the old exact "HH:MM" match, now included.
    assert "Asia/Kolkata" in result  # +5:30 -> 08:30
    assert "Asia/Kathmandu" in result  # +5:45 -> 08:45
    # A zone not at local hour 8 is still excluded.
    assert "UTC" not in result  # 03:00 -> hour 3


def test_every_selected_timezone_reads_the_target_hour():
    with patch.object(notif, "datetime", _FixedDateTime):
        result = notif._get_timezones_at_time("08:00")

    assert result, "expected at least the +5 offset zones"
    for tz_name in result:
        assert _FixedDateTime.now(pytz.timezone(tz_name)).hour == 8

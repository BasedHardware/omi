#!/usr/bin/env python3
"""The foreground-task patch calls startForeground before stop, once."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("patch_flutter_foreground_task.py")
SPEC = importlib.util.spec_from_file_location("patch_flutter_foreground_task", SCRIPT)
assert SPEC and SPEC.loader
patch_mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = patch_mod
SPEC.loader.exec_module(patch_mod)

FIXTURE = """
class ForegroundService : Service() {
        if (action == ForegroundServiceAction.API_STOP) {
            stopForegroundService()
            return START_NOT_STICKY
        }

    private fun startForegroundService() {
        val serviceId = notificationOptions.serviceId
        val notification = createNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(serviceId, notification, foregroundServiceTypes.value)
        } else {
            startForeground(serviceId, notification)
        }
    }
}
"""


class PatchFlutterForegroundTaskTests(unittest.TestCase):
    def test_stop_and_start_both_promote_before_giving_up(self) -> None:
        patched = patch_mod.apply_patch(FIXTURE)
        self.assertIn("OMI_FGS_START_CONTRACT", patched)
        self.assertIn("FOREGROUND_SERVICE_TYPE_SHORT_SERVICE", patched)
        self.assertIn("FOREGROUND_SERVICE_TYPE_LOCATION", patched)
        self.assertNotIn(patch_mod.STOP_OLD, patched)
        self.assertNotIn(patch_mod.START_OLD, patched)
        stop_at = patched.index("API_STOP")
        promote_at = patched.index("promoteForeground", stop_at)
        stop_call = patched.index("stopForegroundService()", promote_at)
        self.assertLess(promote_at, stop_call)
        self.assertIn("allowRequestedType = false", patched[stop_at:stop_call])
        self.assertIn("throw IllegalStateException", patched)

    def test_second_apply_is_a_no_op(self) -> None:
        once = patch_mod.apply_patch(FIXTURE)
        twice = patch_mod.apply_patch(once)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count("private fun promoteForeground"), 1)


if __name__ == "__main__":
    unittest.main()

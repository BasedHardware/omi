#!/usr/bin/env python3
"""The foreground-task patch promotes before cold-start plugin work."""

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
    override fun onCreate() {
        super.onCreate()
        registerBroadcastReceiver()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        loadDataFromPreferences()
        if (action == ForegroundServiceAction.API_STOP) {
            stopForegroundService()
            return START_NOT_STICKY
        }
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
    def test_cold_start_promotes_before_preferences_and_receiver(self) -> None:
        patched = patch_mod.apply_patch(FIXTURE)
        create = patched[patched.index("override fun onCreate()"):patched.index("override fun onStartCommand")]
        self.assertLess(create.index("promoteColdStart()"), create.index("registerBroadcastReceiver()"))
        helper = patched[patched.index("private fun promoteColdStart()"):patched.index("private fun startForegroundService()")]
        self.assertIn("FOREGROUND_SERVICE_TYPE_SHORT_SERVICE", helper)
        self.assertIn("fallbackContractNotification()", helper)
        self.assertNotIn("notificationOptions", helper)
        self.assertNotIn("loadDataFromPreferences", create)
        self.assertLess(patched.index("promoteColdStart()"), patched.index("loadDataFromPreferences()"))

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
        self.assertEqual(twice.count("private fun promoteColdStart"), 1)

    def test_upgrades_round_one_patch_in_pub_cache(self) -> None:
        old = FIXTURE.replace(patch_mod.STOP_OLD, patch_mod.STOP_NEW).replace(
            patch_mod.START_OLD, patch_mod.START_NEW
        ).replace("    private fun startForegroundService() {", patch_mod.HELPERS + "    private fun startForegroundService() {")
        patched = patch_mod.apply_patch(old)
        self.assertEqual(patched.count("private fun promoteForeground"), 1)
        self.assertEqual(patched.count("private fun promoteColdStart"), 1)
        self.assertEqual(patch_mod.apply_patch(patched), patched)


if __name__ == "__main__":
    unittest.main()

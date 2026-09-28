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
    private var isTimeout: Boolean = false

    override fun onCreate() {
        super.onCreate()
        registerBroadcastReceiver()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        isTimeout = false
        loadDataFromPreferences()
        if (action == ForegroundServiceAction.API_STOP) {
            stopForegroundService()
            return START_NOT_STICKY
        }
        try {
            when (action) {
                ForegroundServiceAction.API_UPDATE -> {
                    updateNotification()
                }
            }
        } catch (e: Exception) {
            stopForegroundService()
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        super.onTaskRemoved(rootIntent)
        stopSelf()
    }

    private fun stopForegroundService() {
        RestartReceiver.cancelRestartAlarm(this)
        stopForeground(true)
        stopSelf()

        _isRunningServiceState.update { false }
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

    def test_sticky_restart_promotes_before_preferences_or_null_intent(self) -> None:
        patched = patch_mod.apply_patch(FIXTURE)
        start = patched[patched.index("override fun onStartCommand"):patched.index("override fun onTaskRemoved")]
        self.assertLess(start.index("promoteColdStart()"), start.index("loadDataFromPreferences()"))
        self.assertLess(start.index("promoteColdStart()"), start.index("isTimeout = false"))
        self.assertIn(patch_mod.RESTART_MARKER, start)

    def test_stop_and_later_errors_cannot_precede_promotion(self) -> None:
        patched = patch_mod.apply_patch(FIXTURE)
        removed = patched[patched.index("override fun onTaskRemoved"):patched.index("private fun stopForegroundService()")]
        self.assertLess(removed.index("promoteColdStart()"), removed.index("stopSelf()"))
        stop = patched[patched.index("private fun stopForegroundService()"):patched.index("private fun promoteForeground(")]
        self.assertLess(stop.index("promoteColdStart()"), stop.index("stopForeground(true)"))
        start = patched[patched.index("override fun onStartCommand"):patched.index("override fun onTaskRemoved")]
        self.assertLess(start.index("promoteColdStart()"), start.index("loadDataFromPreferences()"))
        helper = patched[patched.index("private fun promoteColdStart()"):patched.index("private fun startForegroundService()")]
        self.assertIn('throw IllegalStateException("cold-start foreground promotion failed", e)', helper)
        update = patched[patched.index("ForegroundServiceAction.API_UPDATE -> {"):]
        self.assertLess(update.index("startForegroundService()"), update.index("updateNotification()"))

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
        self.assertEqual(twice.count(patch_mod.RESTART_MARKER), 1)

    def test_upgrades_round_one_patch_in_pub_cache(self) -> None:
        old = FIXTURE.replace(patch_mod.STOP_OLD, patch_mod.STOP_NEW).replace(
            patch_mod.START_OLD, patch_mod.START_NEW
        ).replace("    private fun startForegroundService() {", patch_mod.HELPERS + "    private fun startForegroundService() {")
        patched = patch_mod.apply_patch(old)
        self.assertEqual(patched.count("private fun promoteForeground"), 1)
        self.assertEqual(patched.count("private fun promoteColdStart"), 1)
        self.assertEqual(patch_mod.apply_patch(patched), patched)

    def test_upgrades_round_two_patch_in_pub_cache(self) -> None:
        round_two = FIXTURE.replace(patch_mod.STOP_OLD, patch_mod.STOP_NEW).replace(
            patch_mod.START_OLD, patch_mod.START_NEW
        ).replace(
            "    private fun startForegroundService() {",
            patch_mod.HELPERS + patch_mod.EARLY_HELPER.replace(
                'Log.e(TAG, "OMI_FGS_EARLY_PROMOTION: startForeground failed", e)\n'
                '            throw IllegalStateException("cold-start foreground promotion failed", e)',
                'Log.e(TAG, "OMI_FGS_EARLY_PROMOTION: startForeground failed in onCreate", e)',
            ) + "    private fun startForegroundService() {",
        ).replace(patch_mod.CREATE_OLD, patch_mod.CREATE_NEW)
        patched = patch_mod.apply_patch(round_two)
        self.assertEqual(patched.count(patch_mod.RESTART_MARKER), 1)
        self.assertEqual(patch_mod.apply_patch(patched), patched)

    def test_upgrades_round_three_patch_in_pub_cache(self) -> None:
        patched = patch_mod.apply_patch(FIXTURE)
        round_three = patched.replace(patch_mod.START_ID_NEW, patch_mod.START_ID_OLD).replace(
            patch_mod.START_COMMAND_NEW, patch_mod.START_COMMAND_ROUND3
        ).replace(patch_mod.STOP_SELF_NEW, patch_mod.STOP_SELF_OLD)
        upgraded = patch_mod.apply_patch(round_three)
        self.assertEqual(upgraded, patched)
        self.assertIn("stopSelf(lastDeliveredStartId)", upgraded)


if __name__ == "__main__":
    unittest.main()

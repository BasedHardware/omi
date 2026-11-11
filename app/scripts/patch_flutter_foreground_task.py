#!/usr/bin/env python3
"""Patch flutter_foreground_task 10.0.0 foreground start and stop races.

The plugin reads preferences and builds its configurable notification before
its first startForeground(). On a background cold start, that path can consume
the Android deadline or reject the location type. Promote with a static
shortService notification in onCreate, before either preferences or Flutter
work; then let the normal path change to location if it is permitted.

The patch also keeps the earlier stop-path guards and uses the last delivered
start ID when stopping, so a newer pending start does not lose its service
record. It upgrades already-patched pub-cache copies before compilation.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "OMI_FGS_START_CONTRACT"
EARLY_MARKER = "OMI_FGS_EARLY_PROMOTION"
RESTART_MARKER = "OMI_FGS_RESTART_PROMOTION"
STOP_ID_MARKER = "OMI_FGS_STOP_START_ID"

START_ID_OLD = """    private var isTimeout: Boolean = false
"""

START_ID_NEW = """    private var isTimeout: Boolean = false
    // OMI_FGS_STOP_START_ID: preserve a newer start while an older one stops.
    private var lastDeliveredStartId: Int = 0
"""

CREATE_OLD = """    override fun onCreate() {
        super.onCreate()
        registerBroadcastReceiver()
    }
"""

CREATE_NEW = """    override fun onCreate() {
        super.onCreate()
        // OMI_FGS_EARLY_PROMOTION: no preferences, task, or Dart engine needed.
        promoteColdStart()
        registerBroadcastReceiver()
    }
"""

START_COMMAND_OLD = """    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        isTimeout = false
"""

START_COMMAND_NEW = """    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // OMI_FGS_RESTART_PROMOTION: startForegroundService can target an
        // existing instance, so onCreate will not run for this deadline.
        promoteColdStart()
        lastDeliveredStartId = startId
        isTimeout = false
"""

START_COMMAND_ROUND3 = """    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // OMI_FGS_RESTART_PROMOTION: startForegroundService can target an
        // existing instance, so onCreate will not run for this deadline.
        promoteColdStart()
        isTimeout = false
"""

TASK_REMOVED_OLD = """    override fun onTaskRemoved(rootIntent: Intent?) {
        super.onTaskRemoved(rootIntent)
"""

TASK_REMOVED_NEW = """    override fun onTaskRemoved(rootIntent: Intent?) {
        // A new start may be pending when stopWithTask removes the task.
        promoteColdStart()
        super.onTaskRemoved(rootIntent)
"""

STOP_SERVICE_OLD = """    private fun stopForegroundService() {
        RestartReceiver.cancelRestartAlarm(this)
"""

STOP_SERVICE_NEW = """    private fun stopForegroundService() {
        // A visibility callback can stop this existing instance before its
        // queued start command runs. Promote before removing foreground state.
        promoteColdStart()
        RestartReceiver.cancelRestartAlarm(this)
"""

STOP_SELF_OLD = """        stopForeground(true)
        stopSelf()

        _isRunningServiceState.update { false }
"""

STOP_SELF_NEW = """        stopForeground(true)
        // OMI_FGS_STOP_START_ID: an unconditional stopSelf() tears down the
        // ServiceRecord even when startForegroundService has a newer pending
        // command. Android can then time out that new foreground start.
        stopSelf(lastDeliveredStartId)

        _isRunningServiceState.update { false }
"""

UPDATE_OLD = """                ForegroundServiceAction.API_UPDATE -> {
                    updateNotification()
"""

UPDATE_NEW = """                ForegroundServiceAction.API_UPDATE -> {
                    // onStartCommand first used shortService even for updates.
                    // Restore the long-running location type before continuing.
                    startForegroundService()
                    updateNotification()
"""

EARLY_HELPER = """    // The fallback channel and icon are native constants. On Android 14+ the
    // shortService type has no while-in-use location prerequisite. The normal
    // promotion below replaces it with location when that type is allowed;
    // otherwise the service stops before the shortService timeout.
    private fun promoteColdStart() {
        try {
            val notification = fallbackContractNotification()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                startForeground(
                    1000,
                    notification,
                    android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SHORT_SERVICE
                )
            } else {
                startForeground(1000, notification)
            }
            Log.i(TAG, "OMI_FGS_EARLY_PROMOTION: startForeground succeeded in onCreate")
        } catch (e: Exception) {
            Log.e(TAG, "OMI_FGS_EARLY_PROMOTION: startForeground failed", e)
            throw IllegalStateException("cold-start foreground promotion failed", e)
        }
    }

"""

STOP_OLD = """        if (action == ForegroundServiceAction.API_STOP) {
            stopForegroundService()
            return START_NOT_STICKY
        }
"""

STOP_NEW = """        if (action == ForegroundServiceAction.API_STOP) {
            // OMI_FGS_START_CONTRACT: restart() calls startForegroundService()
            // again. If this stop wins, Android 14+ still crashes unless
            // startForeground() has succeeded.
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    createNotificationChannel()
                }
                val serviceId = notificationOptions.serviceId
                val notification = try {
                    createNotification()
                } catch (e: Exception) {
                    Log.e(TAG, "createNotification", e)
                    fallbackContractNotification()
                }
                promoteForeground(serviceId, notification, allowRequestedType = false)
            } catch (e: Exception) {
                Log.e(TAG, "stop-path startForeground contract failed", e)
            }
            stopForegroundService()
            return START_NOT_STICKY
        }
"""

START_OLD = """        val serviceId = notificationOptions.serviceId
        val notification = createNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(serviceId, notification, foregroundServiceTypes.value)
        } else {
            startForeground(serviceId, notification)
        }
"""

START_NEW = """        val serviceId = notificationOptions.serviceId
        val notification = try {
            createNotification()
        } catch (e: Exception) {
            Log.e(TAG, "createNotification", e)
            fallbackContractNotification()
        }
        // OMI_FGS_START_CONTRACT: a rejected type still calls startForeground
        // (shortService) before this throws, so the outer catch can stop
        // without leaving the timeout armed.
        if (!promoteForeground(serviceId, notification, allowRequestedType = true)) {
            throw IllegalStateException("foreground type rejected after satisfying start contract")
        }
"""

HELPERS = """
    // OMI_FGS_START_CONTRACT
    @SuppressLint("WrongConstant", "InlinedApi")
    private fun promoteForeground(
        serviceId: Int,
        notification: Notification,
        allowRequestedType: Boolean
    ): Boolean {
        if (allowRequestedType) {
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    var type = foregroundServiceTypes.value
                    // MANIFEST (-1) would also adopt shortService from the
                    // manifest and put the 3-minute shortService limit on the
                    // long-running location task. This service is location.
                    if (type <= 0) {
                        type = android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
                    }
                    startForeground(serviceId, notification, type)
                } else {
                    startForeground(serviceId, notification)
                }
                return true
            } catch (e: Exception) {
                Log.e(TAG, "startForeground rejected", e)
            }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            try {
                startForeground(
                    serviceId,
                    notification,
                    android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SHORT_SERVICE
                )
            } catch (e: Exception) {
                Log.e(TAG, "shortService startForeground failed", e)
            }
        }
        return false
    }

    private fun fallbackContractNotification(): Notification {
        val channelId = "foreground_service"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            if (nm.getNotificationChannel(channelId) == null) {
                nm.createNotificationChannel(
                    NotificationChannel(channelId, "Foreground Service", NotificationManager.IMPORTANCE_LOW)
                )
            }
            return Notification.Builder(this, channelId)
                .setSmallIcon(android.R.drawable.stat_notify_sync)
                .setContentTitle("Omi")
                .setOngoing(true)
                .build()
        }
        @Suppress("DEPRECATION")
        return Notification()
    }

"""


def apply_patch(source: str) -> str:
    if STOP_ID_MARKER in source:
        if (source.count("private var lastDeliveredStartId: Int = 0") != 1
                or source.count("stopSelf(lastDeliveredStartId)") != 1
                or source.count("lastDeliveredStartId = startId") != 1):
            raise SystemExit("round-4 foreground-service patch is incomplete")
        return source
    if RESTART_MARKER in source:
        if source.count("private fun promoteColdStart()") != 1 or UPDATE_NEW not in source:
            raise SystemExit("round-3 foreground-service patch is incomplete")
        if source.count(START_ID_OLD) != 1 or source.count(START_COMMAND_ROUND3) != 1 or source.count(STOP_SELF_OLD) != 1:
            raise SystemExit("round-3 start-id anchors missing or not unique")
        return (source.replace(START_ID_OLD, START_ID_NEW, 1)
                .replace(START_COMMAND_ROUND3, START_COMMAND_NEW, 1)
                .replace(STOP_SELF_OLD, STOP_SELF_NEW, 1))
    if EARLY_MARKER not in source and source.count(CREATE_OLD) != 1:
        raise SystemExit("flutter_foreground_task onCreate block missing or not unique")
    patched = source
    if MARKER not in source:
        if source.count(START_OLD) != 1 or source.count(STOP_OLD) != 1:
            raise SystemExit("flutter_foreground_task start/stop anchors missing or not unique")
        patched = source.replace(STOP_OLD, STOP_NEW, 1).replace(START_OLD, START_NEW, 1)
        annotated = (
            '    @SuppressLint("WrongConstant", "SuspiciousIndentation")\n'
            "    private fun startForegroundService() {\n"
        )
        plain = "    private fun startForegroundService() {\n"
        if annotated in patched:
            patched = patched.replace(annotated, HELPERS + annotated, 1)
        elif plain in patched:
            patched = patched.replace(plain, HELPERS + plain, 1)
        else:
            raise SystemExit("startForegroundService() not found after patch")
    elif patched.count("private fun fallbackContractNotification()") != 1:
        raise SystemExit("round-1 foreground-service patch is incomplete")

    if EARLY_MARKER not in patched:
        patched = patched.replace(CREATE_OLD, CREATE_NEW, 1)
    annotated = (
        '    @SuppressLint("WrongConstant", "SuspiciousIndentation")\n'
        "    private fun startForegroundService() {\n"
    )
    plain = "    private fun startForegroundService() {\n"
    if EARLY_MARKER not in source:
        if annotated in patched:
            patched = patched.replace(annotated, EARLY_HELPER + annotated, 1)
        elif plain in patched:
            patched = patched.replace(plain, EARLY_HELPER + plain, 1)
        else:
            raise SystemExit("startForegroundService() not found after early promotion")
    else:
        old_catch = """            Log.e(TAG, "OMI_FGS_EARLY_PROMOTION: startForeground failed in onCreate", e)
        }
"""
        new_catch = """            Log.e(TAG, "OMI_FGS_EARLY_PROMOTION: startForeground failed", e)
            throw IllegalStateException("cold-start foreground promotion failed", e)
        }
"""
        if patched.count(old_catch) != 1:
            raise SystemExit("round-2 cold-start promotion catch missing or not unique")
        patched = patched.replace(old_catch, new_catch, 1)

    for old, new in (
        (START_COMMAND_OLD, START_COMMAND_NEW),
        (TASK_REMOVED_OLD, TASK_REMOVED_NEW),
        (STOP_SERVICE_OLD, STOP_SERVICE_NEW),
    ):
        if patched.count(old) != 1:
            raise SystemExit("flutter_foreground_task lifecycle anchor missing or not unique")
        patched = patched.replace(old, new, 1)
    if patched.count(UPDATE_OLD) != 1:
        raise SystemExit("flutter_foreground_task update anchor missing or not unique")
    patched = patched.replace(UPDATE_OLD, UPDATE_NEW, 1)
    if patched.count(START_ID_OLD) != 1 or patched.count(STOP_SELF_OLD) != 1:
        raise SystemExit("flutter_foreground_task start-id anchors missing or not unique")
    patched = patched.replace(START_ID_OLD, START_ID_NEW, 1).replace(STOP_SELF_OLD, STOP_SELF_NEW, 1)
    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <ForegroundService.kt>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    original = path.read_text(encoding="utf-8")
    patched = apply_patch(original)
    if patched != original:
        path.write_text(patched, encoding="utf-8")
        print(f"patched {path}")
    else:
        print(f"already patched {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

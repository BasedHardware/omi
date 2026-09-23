#!/usr/bin/env python3
"""Patch flutter_foreground_task 10.0.0 so startForeground succeeds in time.

Android 14+ delivers ForegroundServiceDidNotStartInTimeException unless
Service.startForeground() returns. The plugin catches a rejected location
promotion and stops, and its API_STOP branch returns without ever calling
startForeground after restart() has already called startForegroundService().

The patch is idempotent. It is applied to the pub-cache plugin from Gradle
before that module compiles.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "OMI_FGS_START_CONTRACT"

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
    if MARKER in source:
        return source
    if STOP_OLD not in source:
        raise SystemExit("flutter_foreground_task API_STOP block not found; plugin source drifted")
    if START_OLD not in source:
        raise SystemExit("flutter_foreground_task startForeground block not found; plugin source drifted")
    if source.count(START_OLD) != 1 or source.count(STOP_OLD) != 1:
        raise SystemExit("foreground service anchors are not unique")
    patched = source.replace(STOP_OLD, STOP_NEW, 1).replace(START_OLD, START_NEW, 1)
    annotated = (
        '    @SuppressLint("WrongConstant", "SuspiciousIndentation")\n'
        "    private fun startForegroundService() {\n"
    )
    plain = "    private fun startForegroundService() {\n"
    if annotated in patched:
        return patched.replace(annotated, HELPERS + annotated, 1)
    if plain in patched:
        return patched.replace(plain, HELPERS + plain, 1)
    raise SystemExit("startForegroundService() not found after patch")


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

package com.friend.ios.ondevice
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

object PhoneBatteryChannel {
    fun register(context: Context, engine: FlutterEngine) {
        MethodChannel(engine.dartExecutor.binaryMessenger, "com.omi/phone_battery").setMethodCallHandler {
            call, result ->
            if (call.method != "read") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            try {
                val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
                val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
                val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
                val status = battery?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
                val plugged = battery?.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1) ?: -1
                if (level < 0 || scale <= 0 || level > scale || plugged < 0 ||
                    status <= BatteryManager.BATTERY_STATUS_UNKNOWN) {
                    result.error("battery_unavailable", "Phone battery unavailable", null)
                } else {
                    val power = context.getSystemService(Context.POWER_SERVICE) as PowerManager
                    // Snapshot only. Older Android and failed/unknown reads
                    // have no thermal coverage; never synthesize a normal state.
                    val thermal = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                        try {
                            when (power.currentThermalStatus) {
                                PowerManager.THERMAL_STATUS_NONE -> "none"
                                PowerManager.THERMAL_STATUS_LIGHT -> "light"
                                PowerManager.THERMAL_STATUS_MODERATE -> "moderate"
                                PowerManager.THERMAL_STATUS_SEVERE -> "severe"
                                PowerManager.THERMAL_STATUS_CRITICAL -> "critical"
                                PowerManager.THERMAL_STATUS_EMERGENCY -> "emergency"
                                PowerManager.THERMAL_STATUS_SHUTDOWN -> "shutdown"
                                else -> null
                            }
                        } catch (_: Exception) { null }
                    } else { null }
                    result.success(mapOf(
                        "elapsed_realtime_ms" to SystemClock.elapsedRealtime(),
                        "thermal_state" to thermal,
                        "battery_level" to ((level.toDouble() / scale) * 100).toInt(),
                        "battery_charging" to (plugged != 0),
                        "os_battery_saver" to power.isPowerSaveMode
                    ))
                }
            } catch (_: Exception) {
                result.error("battery_unavailable", "Phone battery read failed", null)
            }
        }

    }
}

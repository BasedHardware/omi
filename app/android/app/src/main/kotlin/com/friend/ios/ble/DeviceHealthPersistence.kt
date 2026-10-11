package com.friend.ios.ble

import android.content.Context

/** Main-thread BLE/policy operations share this persisted consent and epoch. */
internal object DeviceHealthPersistence {
    fun enabled(context: Context) = context.getSharedPreferences("device_health_policy", Context.MODE_PRIVATE).getBoolean("enabled", false)
    fun epoch(context: Context) = context.getSharedPreferences("device_health_policy", Context.MODE_PRIVATE).getLong("epoch", -1)
    fun build(context: Context): String {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        return "${info.versionName}+${info.longVersionCode}"
    }
    @Synchronized
    fun setPolicy(context: Context, enabled: Boolean, epoch: Long, retire: Boolean) {
        val policy = context.getSharedPreferences("device_health_policy", Context.MODE_PRIVATE)
        // Disable before clearing; stale in-memory recovery state is also retired.
        policy.edit().putBoolean("enabled", false).commit()
        if (retire || policy.getLong("epoch", -1) != epoch) {
            context.getSharedPreferences("ble_diagnostics", Context.MODE_PRIVATE).edit().clear().commit()
            context.getSharedPreferences("battery_history", Context.MODE_PRIVATE).edit().clear().commit()
            OmiBleForegroundService.instance?.retireDeviceHealth()
            if (OmiBleManager.isInitialized) OmiBleManager.instance.retireDeviceHealth()
        }
        policy.edit().putLong("epoch", epoch).putBoolean("enabled", enabled).commit()
        if (enabled) OmiBleForegroundService.instance?.beginDeviceHealthSessions()
    }
    fun sessions(context: Context): BatteryHistorySessionStore {
        val prefs = context.getSharedPreferences("ble_diagnostics", Context.MODE_PRIVATE)
        return BatteryHistorySessionStore(
            { key -> if (key.startsWith("audio_outage_")) prefs.getLong(key, 0).takeIf { it > 0 }?.toString() else prefs.getString(key, null) },
            { key, value -> if (key.startsWith("audio_outage_")) prefs.edit().putLong(key, value.toLong()).commit() else prefs.edit().putString(key, value).commit() },
            { key -> prefs.edit().remove(key).commit() }, { epoch(context) }, { enabled(context) })
    }
}

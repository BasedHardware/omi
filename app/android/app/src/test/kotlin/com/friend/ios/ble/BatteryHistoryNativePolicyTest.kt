package com.friend.ios.ble

import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class BatteryHistoryNativePolicyTest {
    @Test fun `sign out clears native outage session and history stores`() {
        val context = RuntimeEnvironment.getApplication()
        DeviceHealthPersistence.setPolicy(context, true, 7, true)
        DeviceHealthPersistence.sessions(context).start("device", 1000, "build")
        val history = context.getSharedPreferences("battery_history", Context.MODE_PRIVATE)
        history.edit().putString("battery_history_device", "[{\"ts\":1}]").commit()
        val diagnostics = context.getSharedPreferences("ble_diagnostics", Context.MODE_PRIVATE)
        diagnostics.edit().putLong("audio_outage_device", 2000).putString("disconnect_history_device", "[]").commit()
        DeviceHealthPersistence.setPolicy(context, false, 8, true)
        assertTrue(history.all.isEmpty())
        assertTrue(diagnostics.all.isEmpty())
        DeviceHealthPersistence.sessions(context).start("device", 3000, "build")
        assertTrue(diagnostics.all.isEmpty())
    }
    @Test fun `native build provenance comes from installed package at write time`() {
        val context = RuntimeEnvironment.getApplication()
        context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE).edit()
            .putString("flutter.device_health_app_build", "previous-installation").commit()
        assertNotEquals("previous-installation", DeviceHealthPersistence.build(context))
    }
}

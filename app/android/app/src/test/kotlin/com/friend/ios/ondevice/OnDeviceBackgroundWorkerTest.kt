package com.friend.ios.ondevice

import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.concurrent.TimeUnit

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class OnDeviceBackgroundWorkerTest {
    @Test fun chargingScheduleRequiresExternalPower() {
        val request = OnDeviceBackgroundWorker.request(true, "while_charging")
        assertTrue(request.workSpec.constraints.requiresCharging())
        assertEquals(TimeUnit.MINUTES.toMillis(15), request.workSpec.intervalDuration)
    }
    @Test fun intervalScheduleUsesThreeHoursWithoutChargingConstraint() {
        val request = OnDeviceBackgroundWorker.request(false, "every_few_hours")
        assertFalse(request.workSpec.constraints.requiresCharging())
        assertEquals(TimeUnit.HOURS.toMillis(3), request.workSpec.intervalDuration)
    }
}

package com.friend.ios.ble

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RssiDiagnosticsPolicyTest {
    @Test
    fun pollingRequiresAnExplicitMatchingDiagnosticsSubscription() {
        val policy = RssiDiagnosticsPolicy()

        assertFalse(policy.shouldPoll("AA:BB:CC:DD:EE:FF", isConnected = true))

        policy.subscribe("aa:bb:cc:dd:ee:ff")

        assertTrue(policy.shouldPoll("AA:BB:CC:DD:EE:FF", isConnected = true))
        assertFalse(policy.shouldPoll("11:22:33:44:55:66", isConnected = true))
    }

    @Test
    fun disconnectPausesPollingAndReconnectResumesWithoutResubscribing() {
        val policy = RssiDiagnosticsPolicy()
        policy.subscribe("AA:BB:CC:DD:EE:FF")

        assertFalse(policy.shouldPoll("AA:BB:CC:DD:EE:FF", isConnected = false))
        assertTrue(policy.shouldPoll("AA:BB:CC:DD:EE:FF", isConnected = true))
    }

    @Test
    fun onlyTheMatchingDiagnosticsViewCanStopPolling() {
        val policy = RssiDiagnosticsPolicy()
        policy.subscribe("AA:BB:CC:DD:EE:FF")

        assertFalse(policy.unsubscribe("11:22:33:44:55:66"))
        assertTrue(policy.shouldPoll("AA:BB:CC:DD:EE:FF", isConnected = true))
        assertTrue(policy.unsubscribe("AA:BB:CC:DD:EE:FF"))
        assertFalse(policy.shouldPoll("AA:BB:CC:DD:EE:FF", isConnected = true))
    }

    @Test
    fun missingDiagnosticsRssiCallbackDoesNotForceAReconnect() {
        assertFalse(shouldRecoverAfterGattTimeout(GattOperationKind.READ_RSSI))
        assertTrue(shouldRecoverAfterGattTimeout(GattOperationKind.DISCOVER_SERVICES))
        assertTrue(shouldRecoverAfterGattTimeout(GattOperationKind.WRITE_DESCRIPTOR))
    }
}

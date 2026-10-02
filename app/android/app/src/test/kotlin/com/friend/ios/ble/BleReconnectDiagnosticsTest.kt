package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test

class BleReconnectDiagnosticsTest {
    @Test fun `failed retries preserve the original disconnect and full recovery duration`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "disconnect", false)
        diagnostics.record(4_000, "fail_to_connect", false)
        diagnostics.record(7_000, "fail_to_connect", false)

        assertEquals(BleReconnectDiagnostics.Recovery(1_000, 10_000), diagnostics.recovered(11_000, true))
        assertNull(diagnostics.recovered(12_000, true))
    }

    @Test fun `first connection failure is consumed before a later connection loss`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "fail_to_connect", false)
        assertNull(diagnostics.recovered(3_000, false))
        assertNull(diagnostics.recovered(4_000, true))

        diagnostics.record(10_000, "disconnect", false)
        diagnostics.record(12_000, "fail_to_connect", false)
        assertEquals(BleReconnectDiagnostics.Recovery(10_000, 5_000), diagnostics.recovered(15_000, true))
    }

    @Test fun `a new established link loss replaces an earlier pending failure`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "fail_to_connect", false)
        diagnostics.record(5_000, "disconnect", false)
        assertEquals(BleReconnectDiagnostics.Recovery(5_000, 3_000), diagnostics.recovered(8_000, true))
    }

    @Test fun `manual disconnect discards pending recovery timing`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "disconnect", false)
        diagnostics.record(4_000, "disconnect", true)
        assertNull(diagnostics.recovered(10_000, true))
    }

    @Test fun `clock rollback cannot yield a negative duration`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(5_000, "disconnect", false)
        assertEquals(BleReconnectDiagnostics.Recovery(5_000, 0), diagnostics.recovered(4_000, true))
        assertNull(diagnostics.recovered(6_000, true))
    }
}

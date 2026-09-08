package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Test

class BleConnectRouterTest {

    /**
     * Regression for issue #10847. Background Mode keeps OmiBleForegroundService and the
     * GATT link alive after the Flutter engine dies, so the connect request a fresh engine
     * sends on app start lands while the peripheral is still connected. Routing that to a
     * plain reconnect made it a silent no-op: Dart never received onDeviceReady, its connect
     * timed out after 60s, and the app sat on "disconnected" with the link up.
     */
    @Test
    fun `already-connected request re-emits ready instead of being swallowed`() {
        assertEquals(
            ConnectRequestAction.ResyncReady,
            routeConnectRequest(serviceRunning = true, peripheralConnected = true),
        )
    }

    @Test
    fun `running service with a down link reconnects`() {
        assertEquals(
            ConnectRequestAction.Reconnect,
            routeConnectRequest(serviceRunning = true, peripheralConnected = false),
        )
    }

    @Test
    fun `no service instance starts one`() {
        assertEquals(
            ConnectRequestAction.StartService,
            routeConnectRequest(serviceRunning = false, peripheralConnected = false),
        )
        assertEquals(
            ConnectRequestAction.StartService,
            routeConnectRequest(serviceRunning = false, peripheralConnected = true),
        )
    }
}

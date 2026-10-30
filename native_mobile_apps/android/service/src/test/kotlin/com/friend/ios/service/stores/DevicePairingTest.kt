package com.friend.ios.service.stores

import com.friend.ios.device.OmiDeviceManager
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Android's pairing step (and-askomi): the companion association before the connect, the bond flag. */
@OptIn(ExperimentalCoroutinesApi::class)
class DevicePairingTest {
    private val discovery = OmiDeviceManager.Discovery("AA:BB:CC:DD:EE:01", "Omi", -50)

    @Test fun pairingAssociatesBeforeConnecting() = runTest {
        val driver = FakeDriver()
        val store = DeviceStore({ driver }, freshPreferences(), backgroundScope)
        val chooser = CompletableDeferred<Unit>()
        val asked = mutableListOf<String>()
        store.associate = { address ->
            asked += address
            chooser.await()
        }
        store.pair(discovery)
        runCurrent()
        assertEquals(listOf(discovery.id), asked)
        assertTrue(driver.log.none { it.startsWith("connect") })
        chooser.complete(Unit)
        runCurrent()
        assertEquals(listOf("connect ${discovery.id}"), driver.log)
        assertEquals(listOf(false), driver.bonds)
    }

    @Test fun aFailedAssociationStillConnects() = runTest {
        val driver = FakeDriver()
        val store = DeviceStore({ driver }, freshPreferences(), backgroundScope)
        store.associate = { throw IllegalStateException("no chooser") }
        store.pair(discovery)
        runCurrent()
        assertTrue("connect ${discovery.id}" in driver.log)
    }

    @Test fun withoutAssociationTheConnectIsImmediate() = runTest {
        val driver = FakeDriver()
        val store = DeviceStore({ driver }, freshPreferences(), backgroundScope)
        store.pair(discovery)
        assertEquals("connect ${discovery.id}", driver.log.last())
    }
}

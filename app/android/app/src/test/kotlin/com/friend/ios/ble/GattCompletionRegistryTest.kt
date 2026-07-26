package com.friend.ios.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GattCompletionRegistryTest {
    private fun key(
        sessionId: Long,
        instanceId: Int = 7,
    ) = GattCompletionKey(
        address = "aa:bb:cc:dd:ee:ff",
        sessionId = sessionId,
        serviceUuid = "0000180f-0000-1000-8000-00805f9b34fb",
        characteristicUuid = "00002a19-0000-1000-8000-00805f9b34fb",
        characteristicInstanceId = instanceId,
    )

    @Test
    fun staleOldSessionReadCallbackCannotCompleteOrRemoveReplacementRead() {
        val registry = GattCompletionRegistry<ByteArray>()
        val oldGatt = Any()
        val newGatt = Any()
        val oldCharacteristic = Any()
        val newCharacteristic = Any()
        val oldResults = mutableListOf<Result<ByteArray>>()
        val newResults = mutableListOf<Result<ByteArray>>()

        registry.register(key(sessionId = 1), oldGatt, oldCharacteristic, oldResults::add)
        assertEquals(1, registry.failSession(1) { Exception("reconnected") })
        registry.register(key(sessionId = 2), newGatt, newCharacteristic, newResults::add)

        assertNull(registry.takeMatching(key(sessionId = 1), oldGatt, oldCharacteristic))
        assertEquals(1, registry.pendingCount())
        assertEquals(1, oldResults.size)
        assertTrue(oldResults.single().isFailure)
        assertTrue(newResults.isEmpty())

        val replacement = registry.takeMatching(key(sessionId = 2), newGatt, newCharacteristic)
        assertNotNull(replacement)
        replacement?.invoke(Result.success(byteArrayOf(0x2A)))
        assertEquals(0, registry.pendingCount())
        assertArrayEquals(byteArrayOf(0x2A), newResults.single().getOrThrow())
    }

    @Test
    fun staleOldSessionWriteCallbackAndCleanupCannotAffectReplacementWrite() {
        val registry = GattCompletionRegistry<Unit>()
        val oldGatt = Any()
        val newGatt = Any()
        val oldCharacteristic = Any()
        val newCharacteristic = Any()
        val oldResults = mutableListOf<Result<Unit>>()
        val newResults = mutableListOf<Result<Unit>>()

        registry.register(key(sessionId = 10), oldGatt, oldCharacteristic, oldResults::add)
        registry.register(key(sessionId = 11), newGatt, newCharacteristic, newResults::add)

        assertEquals(1, registry.failSession(10) { Exception("old session disconnected") })
        assertEquals(1, registry.pendingCount())
        assertTrue(oldResults.single().isFailure)
        assertTrue(newResults.isEmpty())
        assertNull(registry.takeMatching(key(sessionId = 10), oldGatt, oldCharacteristic))

        val replacement = registry.takeMatching(key(sessionId = 11), newGatt, newCharacteristic)
        assertNotNull(replacement)
        replacement?.invoke(Result.success(Unit))
        assertTrue(newResults.single().isSuccess)
        assertEquals(0, registry.pendingCount())
    }

    @Test
    fun callbackRequiresExactGattAndCharacteristicObjects() {
        val registry = GattCompletionRegistry<ByteArray>()
        val gatt = Any()
        val characteristic = Any()
        val callbackResults = mutableListOf<Result<ByteArray>>()
        val completionKey = key(sessionId = 22, instanceId = 3)

        registry.register(completionKey, gatt, characteristic, callbackResults::add)

        assertNull(registry.takeMatching(completionKey, Any(), characteristic))
        assertNull(registry.takeMatching(completionKey, gatt, Any()))
        assertEquals(1, registry.pendingCount())

        registry.takeMatching(completionKey, gatt, characteristic)?.invoke(Result.success(byteArrayOf(1)))
        assertEquals(0, registry.pendingCount())
        assertFalse(callbackResults.isEmpty())
    }

    @Test
    fun sessionCleanupFailsAndClearsEveryRetainedCompletionExactlyOnce() {
        val registry = GattCompletionRegistry<Unit>()
        val gatt = Any()
        val firstCharacteristic = Any()
        val secondCharacteristic = Any()
        var firstCallbackCount = 0
        var secondCallbackCount = 0

        registry.register(
            key(sessionId = 30, instanceId = 1),
            gatt,
            firstCharacteristic,
            onceGattCompletion<Unit> { firstCallbackCount++ },
        )
        registry.register(
            key(sessionId = 30, instanceId = 2),
            gatt,
            secondCharacteristic,
            onceGattCompletion<Unit> { secondCallbackCount++ },
        )

        assertEquals(2, registry.failSession(30) { Exception("disconnected") })
        assertEquals(0, registry.pendingCount())
        assertEquals(1, firstCallbackCount)
        assertEquals(1, secondCallbackCount)
        assertEquals(0, registry.failSession(30) { Exception("duplicate cleanup") })
        assertEquals(1, firstCallbackCount)
        assertEquals(1, secondCallbackCount)
    }
}

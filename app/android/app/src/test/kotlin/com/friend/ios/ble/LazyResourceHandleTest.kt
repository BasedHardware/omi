package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LazyResourceHandleTest {
    @Test
    fun stoppingAnUninitializedResourceDoesNotCreateIt() {
        var creations = 0
        val handle = LazyResourceHandle {
            creations += 1
            Any()
        }

        assertFalse(handle.stopIfInitialized { error("a dormant resource must not be stopped") })
        assertEquals(0, creations)
    }

    @Test
    fun stoppingAnExistingResourceInvokesTheStopper() {
        var stopped = 0
        val handle = LazyResourceHandle { Any() }
        handle.getOrCreate()

        assertTrue(handle.stopIfInitialized { stopped += 1 })
        assertEquals(1, stopped)
    }
}

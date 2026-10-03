package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Test

class OnceCompletionTest {
    @Test fun `throwing subscriber is not delivered a second failure result`() {
        var count = 0
        val complete = OnceCompletion<Result<Unit>> { count++; throw IllegalStateException("consumer failed") }
        try { complete(Result.failure(IllegalStateException("missing CCCD"))) }
        catch (e: Exception) { complete(Result.failure(e)) }
        assertEquals(1, count)
    }

    @Test fun `reentrant completion claims delivery before invoking the subscriber`() {
        var count = 0
        lateinit var complete: OnceCompletion<Unit>
        complete = OnceCompletion { count++; complete(Unit) }
        complete(Unit)
        assertEquals(1, count)
    }
}

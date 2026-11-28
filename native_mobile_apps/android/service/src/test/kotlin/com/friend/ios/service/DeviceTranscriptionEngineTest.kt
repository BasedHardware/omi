package com.friend.ios.service

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

/** `LiveDeviceTranscriptionEngine`: what keeps the Omi's words off the phone's recognizer. */
class DeviceTranscriptionEngineTest {
    private suspend fun failure(engine: DeviceTranscriptionEngine): Throwable? = runCatching { engine.start() }.exceptionOrNull()

    @Test
    fun withoutThePermissionItAsksForNothingAndSaysSo() = runTest {
        var asked = 0
        val engine = LiveDeviceTranscriptionEngine(isPermitted = { false }, makeTranscriber = { asked += 1; null }, makeDecoder = { null })
        assertEquals(CaptureFailure.SpeechPermission, failure(engine))
        assertEquals(0, asked)
    }

    @Test
    fun withoutARecognizerTheServerTranscribes() = runTest {
        val engine = LiveDeviceTranscriptionEngine(isPermitted = { true }, makeTranscriber = { null }, makeDecoder = { null })
        assertEquals(CaptureFailure.SpeechUnavailable, failure(engine))
    }
}

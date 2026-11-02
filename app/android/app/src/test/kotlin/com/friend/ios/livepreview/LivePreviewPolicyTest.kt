package com.friend.ios.livepreview

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Assert.assertSame
import org.junit.Test

class LivePreviewPolicyTest {
    @Test fun `word timing is anchored to input audio and absent timing cannot prove coverage`() {
        val spans = LivePreviewPolicy.timedSpans(1000, listOf("first" to 10L, "last" to 500L))
        assertEquals(1010L, spans.first()["startMs"])
        assertEquals(1501L, spans.last()["endMs"])
        assertEquals("last", spans.last()["text"])
        assertTrue(LivePreviewPolicy.timedSpans(1000, listOf("untimed" to 0L)).isEmpty())
        assertTrue(LivePreviewPolicy.timedSpans(1000, listOf("late" to 10L, "early" to 5L)).isEmpty())
        assertTrue(LivePreviewPolicy.timedSpans(1000, listOf("invalid" to -1L)).isEmpty())
    }

    @Test fun `os older than Android 13 cannot feed the recognizer and is never probed`() {
        var probed = false
        assertEquals("os_too_old", LivePreviewPolicy.preflight(32, true) { probed = true; true })
        assertEquals("os_too_old", LivePreviewPolicy.preflight(30, true) { true })
        assertFalse(probed)
    }

    @Test fun `missing record-audio permission is reported, never requested`() {
        assertEquals("speech_permission_denied", LivePreviewPolicy.preflight(34, false) { true })
    }

    @Test fun `no on-device recognition service is os_engine_unavailable`() {
        assertEquals("os_engine_unavailable", LivePreviewPolicy.preflight(34, true) { false })
        assertNull(LivePreviewPolicy.preflight(33, true) { true })
    }

    @Test fun `installed languages only, device tag first, never a download`() {
        val pick = LivePreviewPolicy.pickLanguage("en", listOf("en-GB", "en-US", "fr-FR"), emptyList(),
            listOf("en-AU"), "en-US")
        assertEquals(LivePreviewPolicy.LocalePick("en-US", "ok"), pick)
        assertEquals("en-GB", LivePreviewPolicy.pickLanguage("en", listOf("en-GB"), emptyList(), emptyList(), "de-DE").tag)
        assertEquals(LivePreviewPolicy.LocalePick(null, "locale_asset_missing"),
            LivePreviewPolicy.pickLanguage("de", listOf("en-US"), emptyList(), listOf("de-DE"), "de-DE"))
        assertEquals(LivePreviewPolicy.LocalePick(null, "locale_asset_missing"),
            LivePreviewPolicy.pickLanguage("de", emptyList(), listOf("de-DE"), emptyList(), "de-DE"))
        assertEquals("locale_unsupported",
            LivePreviewPolicy.pickLanguage("xx", listOf("en-US"), emptyList(), listOf("en-US"), "en-US").reason)
    }

    @Test fun `language codes`() {
        assertEquals("de", LivePreviewPolicy.languageCode("multi", "de"))
        assertEquals("en", LivePreviewPolicy.languageCode("en-US", "de"))
        assertEquals("pt", LivePreviewPolicy.languageCode("pt_BR", "de"))
    }

    @Test fun `wire values stay on the closed Dart contract`() {
        assertEquals(mapOf("engine" to "none", "reason" to "locale_unsupported", "bundledInstalled" to false),
            LivePreviewPolicy.none("locale_unsupported"))
        assertEquals("engine_error", LivePreviewPolicy.none("made_up")["reason"])
        assertEquals("engine_error", LivePreviewPolicy.none("ok")["reason"])
        assertEquals("android_on_device", LivePreviewPolicy.running()["engine"])
    }

    @Test fun `segment ids advance only on a final result`() {
        val ids = LivePreviewSegmentIds("g")
        assertEquals("g0", ids.id(false))
        assertEquals("g0", ids.id(true))
        assertEquals("g1", ids.current)
    }

    @Test fun `silence reopens the session, other recognizer errors count toward a runtime failure`() {
        assertFalse(LivePreviewPolicy.isRuntimeFailure(android.speech.SpeechRecognizer.ERROR_NO_MATCH))
        assertFalse(LivePreviewPolicy.isRuntimeFailure(android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT))
        assertTrue(LivePreviewPolicy.isRuntimeFailure(android.speech.SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE))
        assertTrue(LivePreviewPolicy.isRuntimeFailure(android.speech.SpeechRecognizer.ERROR_CLIENT))
    }

    private class Fd : java.io.Closeable {
        var closed = 0
        override fun close() { closed++ }
    }

    @Test fun `a recognizer that fails to start closes both pipe ends and rethrows`() {
        val read = Fd()
        val write = Fd()
        val error = assertThrows(IllegalStateException::class.java) {
            LivePreviewPolicy.startOnPipe(read, write) { throw IllegalStateException("startListening") }
        }
        assertEquals("startListening", error.message)
        assertEquals(1, read.closed)
        assertEquals(1, write.closed)
    }

    @Test fun `a started recognizer keeps only the write end`() {
        val read = Fd()
        val write = Fd()
        var handed: Fd? = null
        assertSame(write, LivePreviewPolicy.startOnPipe(read, write) { handed = it })
        assertSame(read, handed)
        assertEquals(1, read.closed)
        assertEquals(0, write.closed)
    }
}

package com.friend.ios.batch

import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NativeBleGeolocationHeaderTest {
    @Test
    fun `authenticated native listen request carries the bounded private snapshot`() {
        val raw = """{"latitude":37.7749,"longitude":-122.4194,"capture_source":"current_position"}"""
        val request = addConversationGeolocationHeader(
            Request.Builder().url("https://api.omiapi.com/v4/listen").header("Authorization", "Bearer token"),
            raw,
        ).build()

        assertEquals("Bearer token", request.header("Authorization"))
        assertEquals(raw, request.header(CONVERSATION_GEOLOCATION_HEADER))
    }

    @Test
    fun `missing malformed and oversized snapshots omit the header`() {
        for (raw in listOf<String?>(null, "", "{not-json", "x".repeat(CONVERSATION_GEOLOCATION_HEADER_MAX_BYTES + 1))) {
            val request = addConversationGeolocationHeader(Request.Builder().url("https://example.test/v4/listen"), raw).build()
            assertNull(request.header(CONVERSATION_GEOLOCATION_HEADER))
        }
    }
}

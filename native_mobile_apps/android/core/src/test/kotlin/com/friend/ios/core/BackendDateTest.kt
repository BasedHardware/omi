package com.friend.ios.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class BackendDateTest {
    @Test fun parsesMicroseconds() {
        assertEquals(Instant.parse("2026-07-18T20:30:00.123456Z"), BackendDate.parse("2026-07-18T20:30:00.123456+00:00"))
    }

    @Test fun readsMissingZoneAsUtc() {
        assertEquals(Instant.parse("2026-07-18T20:30:00Z"), BackendDate.parse("2026-07-18T20:30:00"))
    }

    @Test fun rejectsGarbage() {
        assertNull(BackendDate.parse("yesterday"))
        assertNull(BackendDate.parse(""))
    }
}

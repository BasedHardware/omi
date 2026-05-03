package com.omi.ambientcompanion

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant

class FallbackSegmentTest {
    @Test
    fun liveCaptionNotificationUsesPluginSourceName() {
        val segment = FallbackSegment(
            text = "caption text",
            source = FallbackSource.LIVE_CAPTION_NOTIFICATION,
            start = Instant.parse("2026-05-02T00:00:00Z"),
            end = Instant.parse("2026-05-02T00:00:01Z"),
            healthState = AmbientHealthState.CAPTION_FALLBACK_ACTIVE,
            rawAudioAvailable = false,
        )

        assertEquals("live_caption", segment.apiSource())
    }
}

package com.omi.ambientcompanion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationClassifierTest {
    @Test
    fun meetingPackageStartsCaptureEvenWithSparseText() {
        val trigger = NotificationClassifier.classify("us.zoom.videomeetings", "Zoom", "")

        assertTrue(trigger.shouldStartCapture)
        assertFalse(trigger.shouldQueueCaption)
    }

    @Test
    fun liveTranscribeNotificationQueuesCaptionFallback() {
        val trigger = NotificationClassifier.classify(null, "Live Transcribe", "speech detected")

        assertTrue(trigger.shouldStartCapture)
        assertTrue(trigger.shouldQueueCaption)
    }

    @Test
    fun unrelatedNotificationIsIgnored() {
        val trigger = NotificationClassifier.classify("com.example", "Package delivered", "front door")

        assertFalse(trigger.shouldStartCapture)
        assertFalse(trigger.shouldQueueCaption)
    }
}

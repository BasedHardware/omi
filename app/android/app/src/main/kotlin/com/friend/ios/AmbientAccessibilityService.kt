package com.friend.ios

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

class AmbientAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() {
        isEnabled = true
        AmbientCaptureMethodChannel.emitTelemetry(
            mapOf("type" to "accessibility_enabled", "timestamp" to System.currentTimeMillis()),
        )
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            ForegroundAppDetector.update(event.packageName?.toString())
        }
        if (event.eventType == AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED ||
            event.eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
        ) {
            maybeEmitCaptionText(event)
        }
    }

    override fun onInterrupt() {
    }

    override fun onDestroy() {
        isEnabled = false
        super.onDestroy()
    }

    private fun maybeEmitCaptionText(event: AccessibilityEvent) {
        val prefs = getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
        val captionEnabled = prefs.getBoolean("flutter.ambient_capture_caption_fallback_enabled", false)
        if (!captionEnabled) {
            if (fallbackActive) {
                fallbackActive = false
                AmbientCaptureMethodChannel.emitTelemetry(
                    mapOf("type" to "fallback_stopped", "timestamp" to System.currentTimeMillis()),
                )
            }
            return
        }
        val packageName = event.packageName?.toString() ?: return
        if (!captionPackageAllowlist.contains(packageName)) return
        val className = event.className?.toString()?.lowercase() ?: ""
        val looksLikeCaption = captionClassTokens.any { className.contains(it) }
        if (!looksLikeCaption) return
        val text = event.text?.joinToString(" ")?.trim().orEmpty()
        if (text.isBlank() || text == lastCaptionText) return
        lastCaptionText = text
        if (!fallbackActive) {
            fallbackActive = true
            AmbientCaptureMethodChannel.emitTelemetry(
                mapOf("type" to "fallback_started", "timestamp" to System.currentTimeMillis()),
            )
        }
        AmbientCaptureMethodChannel.emitTelemetry(
            mapOf(
                "type" to "fallback_segment_queued",
                "fallback_source" to "accessibility_caption",
                "foregroundPackage" to packageName,
                "timestamp" to System.currentTimeMillis(),
                "text" to text,
            ),
        )
    }

    companion object {
        @Volatile
        var isEnabled = false
        private val captionPackageAllowlist = setOf(
            "com.microsoft.teams",
            "us.zoom.videomeetings",
            "com.google.android.apps.meetings",
            "com.slack",
            "com.Slack",
        )
        private val captionClassTokens = listOf("caption", "subtitle", "transcript")
        private var lastCaptionText: String? = null
        private var fallbackActive = false
    }
}

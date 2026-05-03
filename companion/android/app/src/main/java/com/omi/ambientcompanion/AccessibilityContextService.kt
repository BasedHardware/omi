package com.omi.ambientcompanion

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

class AccessibilityContextService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return
        val packageName = event.packageName?.toString()
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            ContextSignals.updateForeground(this, packageName)
        }
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED ||
            event.eventType == AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED ||
            event.eventType == AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED
        ) {
            maybeCollectCaption(event, packageName)
        }
    }

    override fun onInterrupt() = Unit

    private fun maybeCollectCaption(event: AccessibilityEvent, packageName: String?) {
        if (!AppPrefs(this).allowCaptionFallback) return
        if (packageName !in captionPackages) return
        val className = event.className?.toString()?.lowercase().orEmpty()
        val looksLikeCaptionSurface = captionClassTokens.any { className.contains(it) }
        val text = event.text?.joinToString(" ")?.trim().orEmpty()
        if (!looksLikeCaptionSurface && text.length < 12) return
        ContextSignals.enqueueCaption(this, text, FallbackSource.ACCESSIBILITY_CAPTION)
    }

    companion object {
        private val captionPackages = setOf(
            "com.microsoft.teams",
            "us.zoom.videomeetings",
            "com.google.android.apps.meetings",
            "com.google.audio.hearing.visualization.accessibility.scribe",
            "com.google.android.apps.accessibility.soundamplifier",
            "com.slack",
        )
        private val captionClassTokens = listOf("caption", "subtitle", "transcript", "textview")
    }
}

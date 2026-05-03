package com.omi.ambientcompanion

import android.content.Context
import org.json.JSONObject
import java.time.Instant

object ContextSignals {
    @Volatile var foregroundPackage: String? = null
    @Volatile var lastTriggerReason: String = "manual"
    @Volatile var captionFallbackActive: Boolean = false
    @Volatile var lastNotificationAtMs: Long = 0
    @Volatile var lastRouteChangeAtMs: Long = 0
    @Volatile var lastHighRiskAtMs: Long = 0
    private var lastCaptionText: String = ""

    val highRiskPackages = setOf(
        "com.microsoft.teams",
        "us.zoom.videomeetings",
        "com.google.android.apps.meetings",
        "com.google.android.dialer",
        "com.samsung.android.dialer",
        "com.slack",
    )

    fun updateForeground(context: Context, packageName: String?) {
        if (packageName.isNullOrBlank()) return
        foregroundPackage = packageName
        if (packageName in highRiskPackages) {
            lastHighRiskAtMs = System.currentTimeMillis()
            lastTriggerReason = "high_risk_foreground:$packageName"
            AuditLog(context).record("high_risk_app_active", mapOf("package" to packageName))
            AmbientForegroundMicService.start(context, "accessibility_high_risk_app")
        }
    }

    fun enqueueCaption(context: Context, text: String, source: FallbackSource) {
        if (!AppPrefs(context).allowCaptionFallback) return
        val normalized = text.trim().replace(Regex("\\s+"), " ")
        if (normalized.length < 3 || normalized == lastCaptionText) return
        lastCaptionText = normalized
        captionFallbackActive = true
        lastTriggerReason = source.name.lowercase()
        val health = AmbientForegroundMicService.lastHealthState()
        FallbackSegmentQueue(context).enqueue(
            FallbackSegment(
                text = normalized,
                source = source,
                start = Instant.now(),
                end = Instant.now(),
                healthState = health,
                rawAudioAvailable = health == AmbientHealthState.AUDIO_OK || health == AmbientHealthState.SPEECH_DETECTED,
                foregroundApp = foregroundPackage,
            )
        )
        AuditLog(context).record("fallback_segment_queued", mapOf("source" to source.name, "foreground" to foregroundPackage))
        AmbientForegroundMicService.start(context, "caption_fallback")
    }

    fun triggerFromNotification(context: Context, packageName: String?, title: String, text: String) {
        triggerFromNotification(context, packageName, title, text, "", "")
    }

    fun triggerFromNotification(context: Context, packageName: String?, title: String, text: String, subText: String, bigText: String) {
        val trigger = NotificationClassifier.classify(packageName, title, text, subText, bigText)
        if (!trigger.shouldStartCapture) return
        lastNotificationAtMs = System.currentTimeMillis()
        lastTriggerReason = trigger.reason
        AuditLog(context).record("notification_trigger", mapOf("package" to packageName, "title" to title.take(80)))
        if (trigger.shouldQueueCaption) {
            enqueueCaption(context, text.ifBlank { title }, FallbackSource.LIVE_CAPTION_NOTIFICATION)
        } else {
            AmbientForegroundMicService.start(context, "notification_context")
        }
    }

    fun triggerFromAudioRoute(context: Context, reason: String) {
        lastRouteChangeAtMs = System.currentTimeMillis()
        lastTriggerReason = reason
        AuditLog(context).record("audio_route_trigger", mapOf("reason" to reason))
        AmbientForegroundMicService.start(context, reason)
    }

    fun snapshot(): JSONObject = JSONObject()
        .put("foreground_package", foregroundPackage)
        .put("last_trigger_reason", lastTriggerReason)
        .put("caption_fallback_active", captionFallbackActive)
        .put("last_notification_at_ms", lastNotificationAtMs)
        .put("last_route_change_at_ms", lastRouteChangeAtMs)
        .put("last_high_risk_at_ms", lastHighRiskAtMs)
}

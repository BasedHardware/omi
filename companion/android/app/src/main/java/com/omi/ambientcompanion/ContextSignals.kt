package com.omi.ambientcompanion

import android.content.Context
import org.json.JSONObject
import java.time.Instant

object ContextSignals {
    @Volatile var foregroundPackage: String? = null
    @Volatile var lastTriggerReason: String = "manual"
    @Volatile var captionFallbackActive: Boolean = false
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
            lastTriggerReason = "high_risk_foreground:$packageName"
            AuditLog(context).record("high_risk_app_active", mapOf("package" to packageName))
            AmbientForegroundMicService.start(context, "accessibility_high_risk_app")
        }
    }

    fun enqueueCaption(context: Context, text: String, source: FallbackSource) {
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
        val combined = "$title $text".lowercase()
        val interesting = listOf("meeting", "call", "transcribe", "caption", "sound notification", "teams", "zoom", "meet")
            .any { combined.contains(it) }
        if (!interesting) return
        lastTriggerReason = "notification:${packageName.orEmpty()}"
        AuditLog(context).record("notification_trigger", mapOf("package" to packageName, "title" to title.take(80)))
        if (combined.contains("caption") || combined.contains("transcribe") || combined.contains("sound notification")) {
            enqueueCaption(context, text.ifBlank { title }, FallbackSource.LIVE_CAPTION_NOTIFICATION)
        } else {
            AmbientForegroundMicService.start(context, "notification_context")
        }
    }

    fun snapshot(): JSONObject = JSONObject()
        .put("foreground_package", foregroundPackage)
        .put("last_trigger_reason", lastTriggerReason)
        .put("caption_fallback_active", captionFallbackActive)
}

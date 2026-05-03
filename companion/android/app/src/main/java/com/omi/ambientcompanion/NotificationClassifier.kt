package com.omi.ambientcompanion

data class NotificationTrigger(
    val shouldStartCapture: Boolean,
    val shouldQueueCaption: Boolean,
    val reason: String,
)

object NotificationClassifier {
    private val meetingPackages = setOf(
        "com.microsoft.teams",
        "us.zoom.videomeetings",
        "com.google.android.apps.meetings",
        "com.slack",
        "com.google.audio.hearing.visualization.accessibility.scribe",
        "com.google.android.apps.accessibility.soundamplifier",
        "com.google.android.dialer",
        "com.samsung.android.dialer",
    )

    private val meetingTerms = listOf(
        "meeting",
        "call",
        "calling",
        "huddle",
        "teams",
        "zoom",
        "meet",
        "live transcribe",
        "transcribe",
        "caption",
        "sound notification",
        "sound detected",
        "speech detected",
    )

    private val captionTerms = listOf(
        "caption",
        "transcribe",
        "transcript",
        "sound notification",
        "speech detected",
    )

    fun classify(packageName: String?, title: String, text: String, subText: String = "", bigText: String = ""): NotificationTrigger {
        val combined = listOf(title, text, subText, bigText).joinToString(" ").lowercase()
        val packageMatch = packageName in meetingPackages
        val termMatch = meetingTerms.any { combined.contains(it) }
        if (!packageMatch && !termMatch) return NotificationTrigger(false, false, "not_interesting")
        val caption = captionTerms.any { combined.contains(it) }
        val reason = if (packageMatch) "notification_package:${packageName.orEmpty()}" else "notification_text"
        return NotificationTrigger(shouldStartCapture = true, shouldQueueCaption = caption, reason = reason)
    }
}

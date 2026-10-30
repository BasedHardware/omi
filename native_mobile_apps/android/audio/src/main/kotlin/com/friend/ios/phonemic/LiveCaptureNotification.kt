package com.friend.ios.phonemic

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.os.Build
import android.text.format.DateUtils
import com.friend.ios.audio.R

/**
 * Android's stand-in for the iOS recording Live Activity (`CaptureLockScreenView`): one ongoing
 * notification per recording, whatever records it. The phone microphone's foreground service
 * shows it ([PhoneMicForegroundService]); an Omi or watch recording is posted by the app while the
 * Omi's own Bluetooth service keeps the process alive. On Android 16 it asks to be promoted to a
 * Live Update (the status-bar chip with the time).
 */
object LiveCaptureNotification {
    const val CHANNEL_ID = "omi_live_capture"

    /** The notification's buttons: Stop holds the audio back, Start brings it back, End saves. */
    enum class Action { PAUSE, RESUME, STOP }

    /** What the recording notification shows; all strings already localized by the app. */
    data class Content(
        /** `CaptureStatusView.title`: Listening, Recording, Paused, or Open Omi to reconnect. */
        val title: String,
        /** The source, and what happens to the audio ("Omi pendant · Transcribing live"). */
        val text: String,
        /** The newest words, under the status line when expanded; empty hides them. */
        val words: String = "",
        /** When the running clock reads zero (paused time left off); null while stopped. */
        val startedAtMillis: Long?,
        /** The clock's frozen value while stopped, in seconds. */
        val frozenSeconds: Int? = null,
        val isPaused: Boolean,
        /** Stop and Start (the Omi and the phone, not the watch). */
        val canPause: Boolean = true,
        /** No buttons: the recording cannot be controlled from here until the app is opened. */
        val showsActions: Boolean = true,
        val pauseLabel: String,
        val resumeLabel: String,
        val stopLabel: String,
        /** The status-bar chip's short text (Android 16), e.g. "Omi". */
        val shortText: String = "Omi",
    )

    fun createChannel(context: Context) {
        // Default importance (no sound, no vibration): Android 16 promotes only channels above
        // IMPORTANCE_MIN, and LOW hides the chip on some launchers.
        val channel = NotificationChannel(CHANNEL_ID, "Omi recording", NotificationManager.IMPORTANCE_DEFAULT).apply {
            setShowBadge(false)
            setSound(null, null)
            enableVibration(false)
        }
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    /** [actionIntent] turns a button into the intent that reaches the app (a service or a receiver). */
    fun build(context: Context, content: Content?, actionIntent: (Action) -> PendingIntent): Notification {
        val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
        val open = launchIntent?.let { PendingIntent.getActivity(context, 0, it, PendingIntent.FLAG_IMMUTABLE) }
        val shown = content ?: Content("Omi", "", startedAtMillis = null, isPaused = false, pauseLabel = "Pause", resumeLabel = "Resume", stopLabel = "Stop")
        val expanded = listOf(shown.text, shown.words).filter { it.isNotEmpty() }.joinToString("\n")
        val builder = Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_omi_live)
            .setContentTitle(shown.title)
            .setContentText(shown.text)
            .setStyle(Notification.BigTextStyle().bigText(expanded))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_STATUS)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE)
        if (open != null) builder.setContentIntent(open)
        if (shown.startedAtMillis != null) {
            builder.setWhen(shown.startedAtMillis).setShowWhen(true).setUsesChronometer(true)
        } else {
            builder.setShowWhen(false).setUsesChronometer(false)
            // A chronometer cannot stop: the stopped clock's value sits in the header instead.
            shown.frozenSeconds?.let { builder.setSubText(DateUtils.formatElapsedTime(it.toLong())) }
        }
        if (shown.showsActions) {
            if (shown.canPause) {
                val toggle = if (shown.isPaused) Action.RESUME to shown.resumeLabel else Action.PAUSE to shown.pauseLabel
                builder.addAction(Notification.Action.Builder(null, toggle.second, actionIntent(toggle.first)).build())
            }
            builder.addAction(Notification.Action.Builder(null, shown.stopLabel, actionIntent(Action.STOP)).build())
        }
        if (Build.VERSION.SDK_INT >= 36) {
            // Android 16 Live Updates: a promoted ongoing notification (status-bar chip with the timer).
            // `setRequestPromotedOngoing` is not in the android-36 stubs yet: the extra it sets
            // (what NotificationCompat 1.17 writes too).
            builder.addExtras(android.os.Bundle().apply { putBoolean("android.requestPromotedOngoing", true) })
            builder.setShortCriticalText(shown.shortText)
        }
        return builder.build()
    }
}

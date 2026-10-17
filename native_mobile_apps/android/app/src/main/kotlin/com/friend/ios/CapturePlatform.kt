package com.friend.ios

import android.Manifest
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.snapshotFlow
import androidx.core.content.ContextCompat
import com.friend.ios.audio.MicrophonePermission
import com.friend.ios.design.Strings
import com.friend.ios.phonemic.PhoneMicForegroundService
import com.friend.ios.phonemic.LiveCaptureNotification
import com.friend.ios.system.CapturePauseClock
import com.friend.ios.system.LiveActivity
import com.friend.ios.system.widgets.WidgetStrings
import com.friend.ios.service.stores.CaptureStore
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * The microphone prompt iOS shows on the first recording (`AVAudioApplication.requestRecordPermission`).
 * Android asks through the visible activity; notifications are asked in the same prompt (Android
 * 13+) so the recording notification shows. Only the microphone is required.
 */
class ActivityMicrophonePermission(private val context: Context) : MicrophonePermission {
    private var launcher: ActivityResultLauncher<Array<String>>? = null
    private var pending: CompletableDeferred<Boolean>? = null

    /** Called from `MainActivity.onCreate` (before it is started), as the result API requires. */
    fun attach(activity: ComponentActivity) {
        launcher = activity.registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
            val granted = results[Manifest.permission.RECORD_AUDIO] ?: isGranted()
            pending?.complete(granted)
            pending = null
        }
    }

    private fun isGranted(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    override suspend fun request(): Boolean {
        if (isGranted()) return true
        val launcher = launcher ?: return false
        pending?.let { return it.await() }
        val deferred = CompletableDeferred<Boolean>()
        pending = deferred
        val permissions = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) add(Manifest.permission.POST_NOTIFICATIONS)
        }
        launcher.launch(permissions.toTypedArray())
        return deferred.await()
    }
}

/**
 * Port of `ExtrasBridge.publishCapture` with `CaptureViews.swift`: Android's stand-in for the iOS
 * recording Live Activity. Keeps one ongoing notification in step with the capture store (the
 * status, the source, the running time without the paused stretches, the newest words) and routes
 * its Stop/Start and End buttons back to the store. The phone microphone's foreground service
 * shows it for a phone recording; an Omi or watch recording gets the same notification, posted
 * here while the Omi's Bluetooth service keeps the app running.
 */
class LiveCaptureNotifier(
    private val context: Context,
    private val capture: CaptureStore,
    private val scope: CoroutineScope,
    /** The watch's own name once it reported in (`WatchStore.info`). */
    private val watchName: () -> String? = { null },
) {
    /** Leaves stopped time off the recording's clock. */
    private val pauseClock = CapturePauseClock()

    fun start() {
        PhoneMicForegroundService.onAction = ::perform
        CaptureActionReceiver.onAction = ::perform
        scope.launch {
            snapshotFlow { capture.phase to content() }.collectLatest { (phase, content) ->
                val phone = capture.source == CaptureStore.Source.Phone
                // A paused phone recording keeps its notification (Resume, Stop) while the mic is off.
                PhoneMicForegroundService.holdsWhilePaused = capture.isPaused && phone
                if (content != null) {
                    if (phone) {
                        cancelOther()
                        PhoneMicForegroundService.update(context, content)
                    } else {
                        postOther(content)
                    }
                } else if (phase == CaptureStore.Phase.Idle || phase is CaptureStore.Phase.Failed) {
                    // Never while starting: the controller may already have started the service.
                    PhoneMicForegroundService.release(context)
                    cancelOther()
                }
            }
        }
    }

    private fun perform(action: LiveCaptureNotification.Action) {
        scope.launch {
            when (action) {
                LiveCaptureNotification.Action.PAUSE -> capture.pause()
                LiveCaptureNotification.Action.RESUME -> capture.resume()
                LiveCaptureNotification.Action.STOP -> capture.stop()
            }
        }
    }

    /** What the notification shows; null when nothing is live. */
    private fun content(): LiveCaptureNotification.Content? {
        val phase = capture.phase as? CaptureStore.Phase.Live ?: return null
        val source = capture.source ?: return null
        val (startedAt, frozen) = pauseClock.observe(since = phase.sinceMillis, paused = capture.isPaused, now = System.currentTimeMillis())
        // Live, or kept on the phone and transcribed later (Transcribe later, or the connection dropped).
        val status = when {
            capture.isPaused -> LiveActivity.CaptureStatus.Paused
            capture.isBuffering -> LiveActivity.CaptureStatus.Recording
            else -> LiveActivity.CaptureStatus.Listening
        }
        val card = LiveActivity.Capture.of(
            id = phase.sinceMillis.toString(), startedAtMillis = startedAt, source = source.card, status = status, elapsedSeconds = frozen,
            // iOS: the card Omi stopped refreshing. Android keeps the app running while it records;
            // what needs the app in front is a microphone the system took (it is only given back
            // to an app on screen).
            isStale = capture.notice != null,
        )
        return LiveCaptureNotification.Content(
            title = title(card),
            text = subtitle(card),
            words = capture.liveWords.takeLast(160),
            startedAtMillis = if (card.status == LiveActivity.CaptureStatus.Paused) null else card.startedAtMillis,
            frozenSeconds = card.elapsedSeconds,
            isPaused = capture.isPaused,
            canPause = card.canPause,
            showsActions = !card.isStale,
            pauseLabel = widget("Stop"),
            resumeLabel = widget("Start"),
            stopLabel = widget("End"),
        )
    }

    /** `CaptureStatusView.title`. */
    private fun title(card: LiveActivity.Capture): String = widget(
        if (card.isStale) "Open Omi to reconnect" else when (card.status) {
            LiveActivity.CaptureStatus.Paused -> "Paused"
            LiveActivity.CaptureStatus.Recording -> "Recording"
            LiveActivity.CaptureStatus.Listening -> "Listening"
        },
    )

    /** `CaptureStatusView.subtitle` (with the source, as on the lock screen). */
    private fun subtitle(card: LiveActivity.Capture): String {
        val source = when (card.source) {
            LiveActivity.Source.Omi -> widget("Omi pendant")
            LiveActivity.Source.Phone -> Strings.get(context, "phone")
            LiveActivity.Source.Watch -> watchName() ?: Strings.get(context, "nativeRecordWithWatch")
        }
        val detail = when (card.status) {
            LiveActivity.CaptureStatus.Listening -> widget("Transcribing live")
            LiveActivity.CaptureStatus.Recording -> widget("Transcribe Later")
            LiveActivity.CaptureStatus.Paused -> return source
        }
        return "$source · $detail"
    }

    private fun widget(key: String) = WidgetStrings.get(context, key)

    /** The Omi's and the watch's recording notification (the phone's belongs to its service). */
    private fun postOther(content: LiveCaptureNotification.Content) {
        if (content == shownOther) return
        shownOther = content
        LiveCaptureNotification.createChannel(context)
        val notification = LiveCaptureNotification.build(context, content) { action -> CaptureActionReceiver.intent(context, action) }
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        runCatching { manager.notify(OTHER_NOTIFICATION_ID, notification) }
    }

    private var shownOther: LiveCaptureNotification.Content? = null

    private fun cancelOther() {
        if (shownOther == null) return
        shownOther = null
        context.getSystemService(NotificationManager::class.java)?.cancel(OTHER_NOTIFICATION_ID)
    }

    private val CaptureStore.Source.card: LiveActivity.Source
        get() = when (this) {
            CaptureStore.Source.Device -> LiveActivity.Source.Omi
            CaptureStore.Source.Phone -> LiveActivity.Source.Phone
            CaptureStore.Source.Watch -> LiveActivity.Source.Watch
        }

    private companion object {
        /** BLE uses 2001, the phone microphone 2002. */
        const val OTHER_NOTIFICATION_ID = 2003
    }
}

/** The Omi's and the watch's recording notification buttons (the phone's go to its service). */
class CaptureActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val raw = intent.getStringExtra(EXTRA_ACTION) ?: return
        val action = runCatching { LiveCaptureNotification.Action.valueOf(raw) }.getOrNull() ?: return
        onAction?.invoke(action)
    }

    companion object {
        private const val EXTRA_ACTION = "com.friend.ios.capture.action"

        /** The app's handler (`LiveCaptureNotifier`), called on the main thread. */
        @Volatile
        var onAction: ((LiveCaptureNotification.Action) -> Unit)? = null

        fun intent(context: Context, action: LiveCaptureNotification.Action): PendingIntent {
            val intent = Intent(context, CaptureActionReceiver::class.java).putExtra(EXTRA_ACTION, action.name)
            return PendingIntent.getBroadcast(
                context, 10 + action.ordinal, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
        }
    }
}

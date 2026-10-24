package com.friend.ios.service.watch

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import com.friend.ios.core.watch.WatchInfo
import com.friend.ios.core.watch.WatchMessage
import com.friend.ios.core.watch.WatchPhoneState
import com.friend.ios.core.watch.WatchStopReason
import com.friend.ios.service.stores.CaptureStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/**
 * The phone's end of the watch link (the Wear OS Data Layer in the app, a fake in tests).
 * Port of the `WatchLink` protocol in `WatchStore.swift` (WatchConnectivity there).
 */
interface WatchLink {
    /** Decoded messages from the watch, in arrival order. */
    val messages: Flow<WatchMessage>
    fun send(message: WatchMessage)
    /** Latest state only (iOS application context): the watch reads it whenever it runs. */
    fun updateState(state: WatchPhoneState)
    /** A watch is connected to this phone (onboarding offers it as a recording source). */
    val isWatchPaired: Boolean get() = false
    /** The Omi watch app is installed on it. */
    val isWatchAppInstalled: Boolean get() = false
}

/**
 * Port of `WatchStore.swift`. The watch companion: a recording started on the watch streams its
 * microphone through the phone into `/v4/listen` (`source=apple_watch`, the only watch source the
 * backend knows), like the Flutter app's watch device. Messages are handled one at a time, so
 * audio that arrives while the conversation opens waits its turn.
 */
class WatchStore(
    val link: WatchLink,
    private val capture: CaptureStore,
    /** Ready for capture; null while the session is still restoring. */
    private val isSignedIn: () -> Boolean?,
    private val omiBattery: () -> Int?,
    private val scope: CoroutineScope,
    /**
     * How long a recording started from the watch waits for the session to restore (the watch can
     * start the phone app in the background).
     */
    private val signInWaitMillis: Long = 10_000,
) {
    /** The watch's own battery, 0-100, as it last reported it. */
    var battery: Int? by mutableStateOf(null)
        private set
    var info: WatchInfo? by mutableStateOf(null)
        private set
    /** The watch's answer to `requestMicrophone()`: null until it gave one. */
    var microphoneGranted: Boolean? by mutableStateOf(null)
        private set
    /** Asked the watch for its microphone and waiting for the answer. */
    var isRequestingMicrophone: Boolean by mutableStateOf(false)
        private set

    private var loop: Job? = null
    private var microphoneWait: Job? = null
    /** The watch asked to stop: no need to tell it back. */
    private var stoppingFromWatch = false

    /** Starts handling watch messages and mirroring the phone's state to the watch. */
    fun start() {
        if (loop != null) return
        capture.onWatchCaptureEnded = { captureEnded() }
        loop = scope.launch { link.messages.collect { handle(it) } }
        publishState()
    }

    /**
     * The watch permission page (Flutter `apple_watch_permission_page`): the watch asks for its
     * microphone and answers with `microphonePermissionResult`. A watch that is not reachable never
     * answers: the wait ends after [answerWaitMillis].
     */
    fun requestMicrophone(answerWaitMillis: Long = 20_000) {
        isRequestingMicrophone = true
        link.send(WatchMessage.RequestMicrophonePermission)
        microphoneWait?.cancel()
        microphoneWait = scope.launch {
            delay(answerWaitMillis)
            isRequestingMicrophone = false
        }
    }

    internal suspend fun handle(message: WatchMessage) {
        when (message) {
            WatchMessage.StartRecording -> watchStarted()
            is WatchMessage.StopRecording -> {
                if (capture.source != CaptureStore.Source.Watch || !capture.isLive) return
                stoppingFromWatch = true
                try {
                    capture.stop()
                } finally {
                    stoppingFromWatch = false
                }
            }
            is WatchMessage.AudioChunk -> {
                // Like Flutter: audio outside a watch recording (e.g. queued from before a relaunch) is dropped.
                if (message.chunk.data.isEmpty()) return
                capture.ingestWatchAudio(message.chunk.data)
            }
            is WatchMessage.BatteryUpdate -> battery = message.level.roundToInt().coerceIn(0, 100)
            is WatchMessage.WatchInfoUpdate -> info = message.info
            is WatchMessage.MicrophonePermissionResult -> {
                microphoneGranted = message.granted
                isRequestingMicrophone = false
                microphoneWait?.cancel()
            }
            is WatchMessage.RecordingError, WatchMessage.RequestMicrophonePermission,
            WatchMessage.RequestBattery, WatchMessage.RequestWatchInfo,
            -> Unit
        }
    }

    private suspend fun watchStarted() {
        if (capture.isLive) {
            if (capture.source != CaptureStore.Source.Watch) link.send(WatchMessage.StopRecording(WatchStopReason.Busy))
            return
        }
        if (!waitForSignIn()) {
            link.send(WatchMessage.StopRecording(WatchStopReason.SignedOut))
            return
        }
        capture.startWatch()
        if (!(capture.source == CaptureStore.Source.Watch && capture.isLive)) {
            link.send(WatchMessage.StopRecording(WatchStopReason.Failed))
        }
    }

    private suspend fun waitForSignIn(): Boolean {
        var waited = 0L
        while (true) {
            isSignedIn()?.let { return it }
            if (waited >= signInWaitMillis) return false
            delay(SIGN_IN_POLL_MILLIS)
            waited += SIGN_IN_POLL_MILLIS
        }
    }

    /** A watch recording ended on the phone (Stop in the app): the watch stops its microphone. */
    private fun captureEnded() {
        if (stoppingFromWatch) return
        link.send(WatchMessage.StopRecording(null))
    }

    /** Sends the phone's capture state and the Omi battery whenever either changes. */
    private fun publishState() {
        scope.launch {
            snapshotFlow { WatchPhoneState(captureState(capture), omiBattery()) }
                .distinctUntilChanged()
                .collect { link.updateState(it) }
        }
    }

    companion object {
        private const val SIGN_IN_POLL_MILLIS = 50L

        fun captureState(capture: CaptureStore): WatchPhoneState.Capture {
            if (!capture.isLive) return WatchPhoneState.Capture.Idle
            return when (capture.source) {
                CaptureStore.Source.Watch -> WatchPhoneState.Capture.Watch
                CaptureStore.Source.Device -> WatchPhoneState.Capture.Omi
                CaptureStore.Source.Phone, null -> WatchPhoneState.Capture.Phone
            }
        }
    }
}

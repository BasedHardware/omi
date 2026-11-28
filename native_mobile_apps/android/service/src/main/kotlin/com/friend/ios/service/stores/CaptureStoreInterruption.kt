package com.friend.ios.service.stores

import com.friend.ios.audio.AudioSessionEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.service.stores.CaptureStore.LogLevel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.currentCoroutineContext

/*
 * Port of `CaptureStore+Interruption.swift`: the phone recording survives the system taking the
 * microphone, and a dropped phone socket is reopened instead of ending the live transcription.
 *
 * Android signals the same things through a different door (`AndroidAudioSessionMonitor`: the
 * recording-config callback, the audio mode, the input devices, the app coming to the front), and
 * the capture controller parks a silenced session by itself (`PhoneMicController`). So the store
 * answers the signals it gets the same way, without tearing down a capture that was never stopped:
 * see [CaptureStore.suspendCapture].
 */

/**
 * Why phone capture is not running, when the reason came from outside the app.
 * (`CaptureNotice` on iOS.)
 */
sealed interface CaptureNotice {
    /** A call, the assistant or another recorder has the microphone; `sinceMillis` is when capture stopped. */
    data class MicrophoneTaken(val sinceMillis: Long) : CaptureNotice

    /** The audio route has no input at all (the microphone itself went away). */
    data object InputGone : CaptureNotice
}

/**
 * Watches the session for as long as the phone records. Only the phone: the Omi's audio arrives
 * over Bluetooth and does not use the app's audio session.
 */
internal fun CaptureStore.startCaptureHealth() {
    if (source != CaptureStore.Source.Phone) return
    audioSession?.start { event -> handleAudioSession(event) }
    if (healthJob != null) return
    healthJob = scope.launch {
        while (isActive) {
            delay(healthTickMillis)
            if (source != CaptureStore.Source.Phone || !isLive) return@launch
            // Either the system took the microphone, or the engine died without saying so.
            if (suspendedBySystem || (!isPaused && !engine.isRunning)) takeMicrophoneBack()
        }
    }
}

internal fun CaptureStore.stopCaptureHealth() {
    healthJob?.cancel()
    healthJob = null
    audioSession?.stop()
    notice = null
    suspendedBySystem = false
}

/** What the phone capture does about one OS signal. */
internal fun CaptureStore.handleAudioSession(event: AudioSessionEvent) {
    if (source != CaptureStore.Source.Phone || !isLive) return
    when (event) {
        AudioSessionEvent.Interrupted -> {
            log(LogLevel.Warning, "capture", "microphone taken by a call or another app: capture paused")
            suspendCapture(CaptureNotice.MicrophoneTaken(clock()))
        }
        is AudioSessionEvent.InterruptionEnded -> {
            // Probing even without the OS's blessing: Android never withholds one, and waiting for a
            // signal that never comes would leave a recording stopped for good.
            log(LogLevel.Info, "capture", "interruption ended (shouldResume: ${event.shouldResume})")
            scope.launch { takeMicrophoneBack() }
        }
        is AudioSessionEvent.RouteChanged -> {
            val input = event.input
            if (input == null) {
                log(LogLevel.Warning, "capture", "audio route has no input: capture paused")
                suspendCapture(CaptureNotice.InputGone)
                return
            }
            log(LogLevel.Info, "capture", "audio route is now $input: rebuilding capture")
            scope.launch { takeMicrophoneBack() }
        }
        AudioSessionEvent.MediaServicesReset -> {
            log(LogLevel.Warning, "capture", "audio services were reset: rebuilding capture")
            scope.launch { takeMicrophoneBack() }
        }
        AudioSessionEvent.AppBecameActive -> {
            if (!suspendedBySystem) return
            scope.launch { takeMicrophoneBack() }
        }
    }
}

/**
 * Pauses capture because the system took the microphone, keeping the recording alive: the socket,
 * the file and the conversation all stay, and the health loop keeps asking for the mic.
 *
 * Android difference: iOS stops the engine here, because its engine is dead after an interruption.
 * Android's capture controller parks a session the system silenced on its own, keeps its engine and
 * drops the frames it would deliver, so only the phone's audio is held back from the socket here
 * and the microphone is left to the controller (see [PhoneCaptureEngine.recoversItself]).
 */
internal fun CaptureStore.suspendCapture(reason: CaptureNotice) {
    if (suspendedBySystem || !isLive) return
    suspendedBySystem = true
    notice = reason
    isPaused = true
    cancelJobs(phoneTasks)
    level = 0f
    partial?.let { flushFinal(it) }
}

/**
 * Starts the phone microphone again, after the system stopped it or a route change pulled the
 * tap out from under it.
 *
 * A failure here is not a failed recording: the words so far are already sent or on disk, so
 * capture stays live, `notice` says why, and the health loop tries again.
 */
internal suspend fun CaptureStore.takeMicrophoneBack() {
    // One at a time: the OS event, the health loop and the user's own resume all ask for this,
    // and two overlapping starts would leave a second engine (and a second pipe) behind.
    if (source != CaptureStore.Source.Phone || !isLive || takingMicrophoneBack) return
    takingMicrophoneBack = true
    try {
        val streams = phoneStreams
        if (streams != null && engine.isRunning) {
            // The capture is live again (the controller resumed a silenced session in place, or the
            // route came back): the same streams carry on, on the same socket and recording id, so
            // nothing is re-acquired and no audio is spliced over.
            suspendedBySystem = false
            isPaused = false
            notice = null
            pipe(streams)
            return
        }
        if (engine.recoversItself) {
            // The controller holds a parked session and brings it back by itself; the next tick
            // re-checks and clears the notice within [CaptureStore.healthTickMillis] of the audio.
            return
        }
        engine.stop()
        cancelJobs(phoneTasks)
        phoneStreams = null
        val started = try {
            engine.start(transcribeOnDevice = transcribesOnDevice && channel != null)
        } catch (error: Exception) {
            suspendedBySystem = true
            isPaused = true
            if (notice == null) notice = CaptureNotice.MicrophoneTaken(clock())
            log(LogLevel.Warning, "capture", "microphone not available yet (${CaptureStore.describe(error)}): still trying")
            return
        }
        // Still wanted? The user may have paused (or stopped) while the microphone was starting
        // up; a pause is theirs to keep, so the fresh engine goes away again.
        if (source != CaptureStore.Source.Phone || !isLive || !(suspendedBySystem || !isPaused)) {
            engine.stop()
            return
        }
        suspendedBySystem = false
        isPaused = false
        notice = null
        pipe(started)
    } finally {
        takingMicrophoneBack = false
    }
}

/** Fails the live capture, and stops the health watch so nothing restarts the microphone after it. */
internal fun CaptureStore.fail(reason: String) {
    stopCaptureHealth()
    phase = CaptureStore.Phase.Failed(reason)
    markEnded()
}

// MARK: A dropped phone socket

/**
 * The phone's socket dropped while the phone still records. The recording stays live: the audio of
 * the gap goes to the phone's file (nothing is lost), and the socket is reopened with the same
 * options and recording id, so the rest of the conversation is transcribed live again instead of
 * waiting for an upload at the end.
 *
 * Without the options or a user to open a socket for, it falls back to the plain file recording
 * (`connectionLost`), which is what the phone did before there was a reconnect.
 */
internal fun CaptureStore.phoneSocketLost() {
    val options = listenOptionsInUse
    val uid = userID()
    if (source != CaptureStore.Source.Phone || phase !is CaptureStore.Phase.Live || reconnectingPhone || options == null || uid == null) {
        connectionLost()
        return
    }
    channel?.close("socket_lost")
    channel = null
    beginBuffering(manual = false)
    recovery = CaptureRecovery.ConnectionLost
    reconnectingPhone = true
    log(LogLevel.Warning, "stt", "phone socket lost: recording to the phone while reconnecting")
    tasks += scope.launch { reopenPhoneSocket(uid, options) }
}

internal suspend fun CaptureStore.reopenPhoneSocket(uid: String, options: ListenSocket.Options) {
    var attempt = 0
    while (true) {
        delay(phoneReconnectDelays[minOf(attempt, phoneReconnectDelays.size - 1)])
        attempt += 1
        if (!stillReconnectingPhone()) return
        val channel = try {
            api.openListenSocket(uid, options)
        } catch (error: Exception) {
            continue
        }
        if (!stillReconnectingPhone()) {
            channel.close("user_stop")
            return
        }
        this.channel = channel
        reconnectingPhone = false
        // The file closes into the upload queue; the socket carries the recording from here.
        endBuffering()
        recovery = null
        listen(channel, acceptServerSegments = transcriber == Transcriber.Omi)
        log(LogLevel.Info, "stt", "phone socket reopened after $attempt attempt(s)")
        return
    }
}

/**
 * The recording did not end (stop, user paused for good) while the phone's socket was away. Read
 * inside the reconnect, so the job that runs it is still alive.
 */
internal suspend fun CaptureStore.stillReconnectingPhone(): Boolean =
    reconnectingPhone &&
        source == CaptureStore.Source.Phone &&
        phase is CaptureStore.Phase.Live &&
        currentCoroutineContext().isActive

/** Clears the "the system stopped this" banner. The recording itself stays paused. */
fun CaptureStore.dismissNotice() {
    notice = null
}

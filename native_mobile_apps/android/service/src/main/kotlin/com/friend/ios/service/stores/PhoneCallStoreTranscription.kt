package com.friend.ios.service.stores

import com.friend.ios.network.listen.PhoneCallSocketEvent
import com.friend.ios.service.phonecalls.PhoneCallAudio
import com.friend.ios.service.stores.PhoneCallStore.Phase
import com.friend.ios.service.stores.PhoneCallStore.TranscriptionStatus
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/*
 * Port of `PhoneCallStore+Transcription.swift`. The call's transcription socket (Flutter
 * `PhoneCallProvider._connectTranscriptionSocket` and friends): opened when the call connects, both
 * sides' audio as channel-tagged frames, frames buffered while it reconnects (1 s, 2 s, 4 s ... up to
 * ten tries), a no-audio watchdog.
 */

internal fun PhoneCallStore.connectTranscription() {
    if (phase != Phase.Active) return
    val callID = callID ?: return
    val uid = userID()
    if (uid == null) {
        transcription = TranscriptionStatus.Failed
        return
    }
    reconnectTask?.cancel()
    reconnectTask = null
    transcription = TranscriptionStatus.Connecting
    val callGeneration = generation
    val language = language()
    socketTask = scope.launch {
        try {
            val channel = api.openPhoneCallSocket(uid, callID, language)
            if (callGeneration != generation || phase != Phase.Active) {
                channel.close()
                return@launch
            }
            socket = channel
            reconnectAttempts = 0
            channel.events.collect { event ->
                if (callGeneration != generation) throw CancellationException("an earlier call")
                received(event)
            }
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            // Falls through to the reconnect below.
        }
        // Closed by the server or the network; our own close happens once the call is over.
        if (!isActive || callGeneration != generation || phase != Phase.Active) return@launch
        socket = null
        scheduleReconnect()
    }
}

internal fun PhoneCallStore.received(event: PhoneCallSocketEvent) {
    if (event is PhoneCallSocketEvent.Closed) return
    if (transcription != TranscriptionStatus.Active) {
        transcription = TranscriptionStatus.Active
        socketAccepted = true
        armNoAudioWatchdog()
    }
    when (event) {
        is PhoneCallSocketEvent.Segments -> transcript = transcript.merge(event.segments)
        is PhoneCallSocketEvent.Translations -> transcript = transcript.applyTranslations(event.translations)
        is PhoneCallSocketEvent.Status, is PhoneCallSocketEvent.Closed -> Unit
    }
}

internal fun PhoneCallStore.scheduleReconnect() {
    if (phase != Phase.Active) return
    if (reconnectAttempts >= PhoneCallStore.MAX_RECONNECT_ATTEMPTS) {
        transcription = TranscriptionStatus.Failed
        return
    }
    transcription = TranscriptionStatus.Reconnecting
    val wait = timing.reconnectBase * (1 shl reconnectAttempts)
    reconnectAttempts += 1
    val callGeneration = generation
    reconnectTask = scope.launch {
        delay(wait)
        if (callGeneration != generation || phase != Phase.Active) return@launch
        connectTranscription()
    }
}

/** One side's audio as `[channel byte] + PCM16`, the backend's two-channel frame. */
internal fun PhoneCallStore.forward(audio: PhoneCallAudio) {
    if (!isInProgress) return
    // Start-of-call only: the first frame disarms the watchdog for the rest of the call.
    watchdogTask?.cancel()
    watchdogTask = null
    val frame = ByteArray(audio.pcm16.size + 1)
    frame[0] = audio.channel.rawValue
    audio.pcm16.copyInto(frame, destinationOffset = 1)
    val socket = socket
    if (socket == null) {
        if (pendingFrames.size < PhoneCallStore.MAX_PENDING_FRAMES) pendingFrames += frame
        return
    }
    for (pending in pendingFrames) socket.send(pending)
    framesSent += pendingFrames.size + 1
    pendingFrames = mutableListOf()
    socket.send(frame)
    if (transcription == TranscriptionStatus.NoAudio) transcription = TranscriptionStatus.Active
}

/** Armed once the server answered; says so when no call audio arrives. */
internal fun PhoneCallStore.armNoAudioWatchdog() {
    watchdogTask?.cancel()
    val timeout = timing.noAudioTimeout
    watchdogTask = scope.launch {
        delay(timeout)
        if (phase != Phase.Active || !socketAccepted || socket == null || framesSent != 0) return@launch
        transcription = TranscriptionStatus.NoAudio
    }
}

internal fun PhoneCallStore.disconnectTranscription() {
    watchdogTask?.cancel()
    watchdogTask = null
    reconnectTask?.cancel()
    reconnectTask = null
    socketTask?.cancel()
    socketTask = null
    reconnectAttempts = 0
    socket?.close()
    socket = null
}

package com.friend.ios.service.stores

import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.network.APIError
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.stores.CaptureStore.LogLevel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.coroutines.coroutineContext

/*
 * Port of `CaptureStore+Lifecycle.swift`. When a conversation ends. The backend finalizes a
 * conversation on its silence timeout while its socket lives, and when the app asks
 * (`POST v1/conversations`). It does not when a phone or Omi socket closes, and a new socket (a new
 * recording id) never resumes the old conversation. So the app remembers the conversation its
 * socket records into, and one still open at the next start (the app was closed, the Omi or the
 * socket went away) is finalized before the new socket opens. A dropped Omi socket reopens with
 * the same recording id, which resumes the same conversation (Flutter's reconnect keeps its
 * recording id), and the Omi's audio meanwhile is held and sent first.
 */

// MARK: The open conversation

internal fun CaptureStore.rememberOpenConversation(id: String) {
    preferences.set(NativeKey.CaptureOpenConversation, id)
}

/** Forgets [id] (or whatever is remembered when null); a different remembered id stays. */
internal fun CaptureStore.forgetOpenConversation(id: String? = null) {
    if (id != null && preferences.string(NativeKey.CaptureOpenConversation) != id) return
    preferences.set(NativeKey.CaptureOpenConversation, null as String?)
}

/**
 * The end of a recording: finalizes its conversation (`POST v1/conversations`). When that
 * fails it stays remembered and the next start finalizes it.
 */
internal suspend fun CaptureStore.finalizeOpenConversation(): String? = try {
    api.finalizeInProgressConversation().also { forgetOpenConversation() }
} catch (error: Exception) {
    log(LogLevel.Warning, "capture", "finalizing failed, retried at the next start: $error")
    null
}

/**
 * Finalizes the conversation an earlier socket left open, when it has words or photos. An empty
 * one is left to the backend, which deletes it.
 */
internal suspend fun CaptureStore.finalizeLeftoverConversation() {
    val id = preferences.string(NativeKey.CaptureOpenConversation) ?: return
    val detail: ConversationDetail = try {
        api.conversationDetail(id)
    } catch (error: APIError.Http) {
        if (error.status == 404) {
            forgetOpenConversation(id)
        } else {
            log(LogLevel.Warning, "capture", "open conversation not checked: $error")
        }
        return
    } catch (error: Exception) {
        log(LogLevel.Warning, "capture", "open conversation not checked: $error")
        return
    }
    forgetOpenConversation(id)
    if (detail.conversation.status != Conversation.Status.InProgress || (detail.transcript.isEmpty() && detail.photos.isEmpty())) return
    try {
        finalizeLeftover(id)
    } catch (error: Exception) {
        log(LogLevel.Warning, "capture", "finalizing the open conversation failed, retried at the next start: $error")
        rememberOpenConversation(id)
        return
    }
    log(LogLevel.Info, "capture", "finalized a conversation left open")
    onConversationFinished?.invoke()
}

private suspend fun CaptureStore.finalizeLeftover(id: String) {
    try {
        api.finalizeConversation(id)
    } catch (error: APIError.Http) {
        if (error.status != 503) throw error
        // No durable finalization worker (a local backend). The in-progress endpoint finalizes
        // the newest conversation in progress: only while that is this one, never another.
        if (api.inProgressConversationID() != id) {
            log(LogLevel.Warning, "capture", "the open conversation is not the newest in progress: left to the backend")
            return
        }
        api.finalizeInProgressConversation()
    }
}

// MARK: Omi audio without a socket

/** About eight minutes of opus; the oldest goes first beyond it. */
internal const val heldDeviceAudioLimit = 2_000_000

/** Holds a frame while a socket is on its way (never while muted). */
internal fun CaptureStore.holdDeviceAudio(frame: ByteArray) {
    if (isDeviceMuted) return
    if (!(phase == CaptureStore.Phase.Starting || phase == CaptureStore.Phase.Finishing || reconnectingDevice)) return
    heldDeviceAudio.addLast(frame)
    heldDeviceAudioBytes += frame.size
    while (heldDeviceAudioBytes > heldDeviceAudioLimit && heldDeviceAudio.isNotEmpty()) {
        heldDeviceAudioBytes -= heldDeviceAudio.removeFirst().size
    }
}

/** The socket is open: what was held goes first, in order. */
internal fun CaptureStore.sendHeldDeviceAudio() {
    val frames = heldDeviceAudio.toList()
    discardHeldDeviceAudio()
    frames.forEach(::ingestDeviceAudio)
}

internal fun CaptureStore.discardHeldDeviceAudio() {
    heldDeviceAudio = ArrayDeque()
    heldDeviceAudioBytes = 0
}

// MARK: A dropped Omi socket

/**
 * The Omi's socket dropped while the Omi still streams: reopen it with the same options (and
 * recording id) until it opens or the recording ends.
 */
internal fun CaptureStore.deviceSocketLost() {
    if (source != CaptureStore.Source.Device || phase !is CaptureStore.Phase.Live || reconnectingDevice) return
    val options = listenOptionsInUse ?: return
    val uid = userID() ?: return
    channel?.close("socket_lost")
    channel = null
    reconnectingDevice = true
    log(LogLevel.Warning, "stt", "socket lost: reconnecting")
    tasks += scope.launch { reopenDeviceSocket(uid, options) }
}

private suspend fun CaptureStore.reopenDeviceSocket(uid: String, options: ListenSocket.Options) {
    var attempt = 0
    while (true) {
        delay(deviceReconnectDelays[minOf(attempt, deviceReconnectDelays.size - 1)])
        attempt += 1
        if (!stillReconnecting()) return
        val channel = try {
            api.openListenSocket(uid, options)
        } catch (error: Exception) {
            continue
        }
        if (!stillReconnecting()) {
            channel.close("user_stop")
            return
        }
        this.channel = channel
        reconnectingDevice = false
        listen(channel, acceptServerSegments = transcriber == Transcriber.Omi)
        sendHeldDeviceAudio()
        log(LogLevel.Info, "stt", "socket reopened after $attempt attempt(s)")
        return
    }
}

/** The recording did not end (stop, Omi gone) while the socket was away. */
private suspend fun CaptureStore.stillReconnecting(): Boolean =
    reconnectingDevice && source == CaptureStore.Source.Device && phase is CaptureStore.Phase.Live && coroutineContext.isActive

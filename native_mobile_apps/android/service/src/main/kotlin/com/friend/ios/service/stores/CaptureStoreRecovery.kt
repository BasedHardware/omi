package com.friend.ios.service.stores

import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.stores.CaptureStore.LogLevel

/**
 * Where phone audio goes when it cannot be streamed (the app: `SyncStore`, which keeps the file
 * across relaunches and uploads it to `v2/sync-local-files`).
 */
interface PhoneAudioBuffering {
    /** Opens a file. [manual]: Transcribe later, uploaded only when the user asks. */
    fun beginPhoneAudio(manual: Boolean)

    fun appendPhoneAudio(pcm: ByteArray)

    /** Closes the file; it joins the upload queue. */
    fun endPhoneAudio()

    /** Store audio on phone: a copy of what streams live, kept on the phone and never uploaded. */
    fun beginKeptCopy(source: KeptAudioSource)

    /** PCM16 from the phone, or one opus packet from the Omi. */
    fun appendKeptCopy(audio: ByteArray)

    fun endKeptCopy()
}

/** What a kept copy of a recording holds (iOS `KeptAudioSource`). */
sealed interface KeptAudioSource {
    data object Phone : KeptAudioSource

    data class Device(val codec: ListenSocket.Options.Codec) : KeptAudioSource
}

/** A recording that did not end the way it was meant to (Flutter `capture_recovery_banner`). */
sealed interface CaptureRecovery {
    /**
     * The app was closed while recording (crash, or the system ended it). What reached the server
     * or the phone is kept.
     */
    data class Interrupted(val sinceMillis: Long) : CaptureRecovery

    /**
     * The connection dropped mid-recording: the rest was kept on the phone and uploads when
     * the recording ends (or once the phone is online).
     */
    data object ConnectionLost : CaptureRecovery
}

/** The listen options every source shares: the server model and the developer VAD gate. */
internal fun CaptureStore.listenOptions(options: ListenSocket.Options): ListenSocket.Options = options.copy(
    sttService = if (usesParakeet) "parakeet" else null,
    vadGate = preferences.bool(Key.VadGateEnabled, false),
)

/**
 * Live from now; the mark survives until the recording ends, so a relaunch can tell. Only
 * the phone microphone loses audio when the app is closed: an Omi keeps recording to its own
 * storage and syncs it on reconnect, so its recordings set no mark (no false alarm on every
 * relaunch of an always-on wearable).
 */
internal fun CaptureStore.setLive() {
    val now = clock()
    phase = CaptureStore.Phase.Live(now)
    // Seconds since 1970 as text, the iOS encoding (`String(Date.now.timeIntervalSince1970)`).
    val mark = if (source == CaptureStore.Source.Device) null else (now / 1000.0).toString()
    preferences.set(NativeKey.CaptureActiveSince, mark)
    log(LogLevel.Info, "capture", "recording started (${(source ?: CaptureStore.Source.Phone).name.lowercase()})")
    startCaptureHealth()
}

internal fun CaptureStore.markEnded() {
    preferences.set(NativeKey.CaptureActiveSince, null as String?)
}

internal fun recoveredInterruption(preferences: Preferences): CaptureRecovery? {
    val since = preferences.string(NativeKey.CaptureActiveSince)?.toDoubleOrNull() ?: return null
    preferences.set(NativeKey.CaptureActiveSince, null as String?)
    return CaptureRecovery.Interrupted((since * 1000).toLong())
}

internal fun CaptureStore.beginBuffering(manual: Boolean) {
    if (isBuffering) return
    val buffer = phoneBuffer ?: return
    buffer.beginPhoneAudio(manual)
    isBuffering = true
    log(LogLevel.Info, "capture", if (manual) "recording to the phone (transcribe later)" else "recording to the phone (offline)")
}

internal fun CaptureStore.endBuffering() {
    if (!isBuffering) return
    phoneBuffer?.endPhoneAudio()
    isBuffering = false
}

/** The socket dropped while the phone mic records: keep going into a file. */
internal fun CaptureStore.connectionLost() {
    channel = null
    beginBuffering(manual = false)
    recovery = CaptureRecovery.ConnectionLost
}

internal fun CaptureStore.routePhoneAudio(chunk: ByteArray) {
    if (source != CaptureStore.Source.Phone) return
    if (keepsCopy) phoneBuffer?.appendKeptCopy(chunk)
    if (isBuffering) {
        phoneBuffer?.appendPhoneAudio(chunk)
    } else {
        channel?.send(chunk)
        customTranscriber?.feed(chunk)
    }
}

fun CaptureStore.dismissRecovery() {
    recovery = null
}

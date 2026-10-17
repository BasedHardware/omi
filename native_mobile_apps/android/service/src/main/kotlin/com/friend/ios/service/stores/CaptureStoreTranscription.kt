package com.friend.ios.service.stores

import com.friend.ios.core.models.TranscriptionAllowance
import com.friend.ios.network.customstt.CustomSTTConfig
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.service.PhoneCaptureStreams
import com.friend.ios.service.stores.CaptureStore.LogLevel
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** Who transcribes a live recording. */
sealed interface Transcriber {
    /** Omi's servers (the managed transcription the plan's minutes pay for). */
    data object Omi : Transcriber

    /** The phone's own recognizer: the user chose it, or the plan's minutes are used up. */
    data object Phone : Transcriber

    /** The user's own provider (its name). */
    data class Custom(val name: String) : Transcriber
}

/**
 * Something about this recording's transcription the person should know (Flutter's freemium
 * threshold and its on-device switch).
 */
sealed interface TranscriptionNotice {
    /** The plan's transcription minutes run out soon (Flutter shows Plus users the plans). */
    data class MinutesRunningLow(val seconds: Int) : TranscriptionNotice

    /** The minutes are used up: the phone transcribes instead (Flutter "Switched to on-device"). */
    data object SwitchedToPhone : TranscriptionNotice

    /** Transcription is not allowed on this account right now: the audio is kept on the phone. */
    data object RecordingOnly : TranscriptionNotice
}

/*
 * Port of `CaptureStore+Transcription.swift`: which transcriber a recording starts with, the plan's
 * fallback when its minutes run out, the backend's translations, and Store audio on phone.
 * The user's own provider (`CustomSTTSettings`, `CustomTranscribing`) takes phone and Omi recordings.
 * On-device transcription is the phone's SpeechRecognizer (`OnDeviceTranscriber`); without one
 * the plan falls back to Omi's server as iOS does without speech permission.
 */

internal sealed interface Plan {
    data object Omi : Plan
    data object Phone : Plan
    data class Custom(val config: CustomSTTConfig) : Plan
    /** Record to a file on the phone, transcribe when asked (Transcribe later, or nothing may transcribe). */
    data object Later : Plan
}

/**
 * The order Flutter's `SttModeResolver` uses: Transcribe later, the user's own provider, then the
 * plan (`transcription_allowance`): `on_device` falls back to the phone, `blocked` keeps the audio
 * on the phone. [opus]: the source can feed the phone's recognizer (the phone mic always can).
 */
internal fun CaptureStore.transcriptionPlan(laterRequested: Boolean, opus: Boolean): Plan {
    if (laterRequested) return Plan.Later
    // The Omi's opus reaches the provider as PCM through the phone's decoder (iOS `OpusPCM16Decoder`,
    // here the platform's `audio/opus`); without one only the phone microphone's PCM goes there.
    val config = customSTT?.config
    val decodes = source == CaptureStore.Source.Phone || makeOpusDecoder != null
    if (opus && decodes && config != null && config.isComplete && makeCustomTranscriber != null) return Plan.Custom(config)
    val allowance = transcriptionAllowance
    if (allowance == TranscriptionAllowance.OnDevice && opus) {
        transcriptionNotice = TranscriptionNotice.SwitchedToPhone
        log(LogLevel.Info, "stt", "no transcription minutes left: the phone transcribes")
        return Plan.Phone
    }
    if (allowance == TranscriptionAllowance.Blocked && source == CaptureStore.Source.Phone && phoneBuffer != null) {
        transcriptionNotice = TranscriptionNotice.RecordingOnly
        log(LogLevel.Warning, "stt", "transcription not available on this plan: recording to the phone")
        return Plan.Later
    }
    return if (transcribesOnDevice && opus) Plan.Phone else Plan.Omi
}

/**
 * The phone engine for a plan, and the plan it ends up with. The plan's own switch to the phone
 * needs speech recognition; without it the recording still runs on Omi's socket (the audio is
 * kept, the transcript waits).
 */
internal suspend fun CaptureStore.startPhoneStreams(plan: Plan): Pair<PhoneCaptureStreams, Plan> = try {
    startPhoneEngine(onDevice = plan == Plan.Phone, preview = plan == Plan.Omi) to plan
} catch (error: Exception) {
    if (plan != Plan.Phone || transcribesOnDevice) throw error
    engine.stop()
    transcriptionNotice = TranscriptionNotice.MinutesRunningLow(0)
    startPhoneEngine(onDevice = false, preview = false) to Plan.Omi
}

/**
 * The live session is on: the chosen transcriber starts, and the plan is checked again for the
 * next recording.
 */
internal fun CaptureStore.beginTranscriber(plan: Plan) {
    when (plan) {
        Plan.Omi, Plan.Later -> transcriber = Transcriber.Omi
        Plan.Phone -> transcriber = Transcriber.Phone
        is Plan.Custom -> {
            val custom = makeCustomTranscriber?.invoke(plan.config) ?: return
            customTranscriber = custom
            transcriber = Transcriber.Custom(custom.providerName)
            val name = custom.providerName
            tasks += scope.launch {
                custom.start().collect { segment ->
                    upsert(segment)
                    channel?.sendSuggestedTranscript(listOf(segment), provider = name)
                }
            }
        }
    }
    scope.launch { refreshTranscriptionAllowance() }
}

internal fun CaptureStore.endTranscriber() {
    customTranscriber?.stop()
    customTranscriber = null
    opusToPCM?.release()
    opusToPCM = null
}

// MARK: Plan

/**
 * The backend's last word on who may transcribe (kept across launches, Flutter's
 * `TranscriptionAllowanceCache`): a failed refresh does not put an account without minutes
 * back on Omi's transcription.
 */
internal val CaptureStore.transcriptionAllowance: TranscriptionAllowance?
    get() {
        val text = preferences.string(Key.TranscriptionAllowanceLastKnown) ?: return null
        return TranscriptionAllowance.from(runCatching { Json.parseToJsonElement(text).jsonObject["mode"]?.jsonPrimitive?.contentOrNull }.getOrNull())
    }

internal fun CaptureStore.setTranscriptionAllowance(allowance: TranscriptionAllowance?) {
    preferences.set(Key.TranscriptionAllowanceLastKnown, allowance?.let { """{"mode":"${it.rawValue}"}""" })
}

/**
 * `GET v1/users/me/subscription`. A backend without `transcription_allowance` still says when the
 * minutes are used up (the managed socket then sends no transcript at all).
 */
suspend fun CaptureStore.refreshTranscriptionAllowance() {
    val subscription = try {
        api.subscription()
    } catch (error: Exception) {
        return
    }
    setTranscriptionAllowance(
        subscription.transcriptionAllowance
            ?: if (subscription.isOutOfMinutes) TranscriptionAllowance.OnDevice else TranscriptionAllowance.Managed,
    )
}

/** `freemium_threshold_reached`: low (a notice) or out (`remaining` 0, the phone takes over). */
internal suspend fun CaptureStore.freemiumThresholdReached(remainingSeconds: Int, requiresOnDevice: Boolean) {
    log(LogLevel.Warning, "stt", "transcription minutes: $remainingSeconds s left")
    if (remainingSeconds > 0 || !requiresOnDevice) {
        transcriptionNotice = TranscriptionNotice.MinutesRunningLow(remainingSeconds)
        return
    }
    setTranscriptionAllowance(TranscriptionAllowance.OnDevice)
    switchToPhoneTranscription()
}

/**
 * Mid-recording: the phone's recognizer, already running as the live preview, becomes the
 * transcript, and the socket reopens with `custom_stt` (the conversation stays open on the
 * server until its silence timeout, so nothing is finalized).
 */
internal suspend fun CaptureStore.switchToPhoneTranscription() {
    val options = listenOptionsInUse
    val uid = userID()
    if (phase !is CaptureStore.Phase.Live || transcriber != Transcriber.Omi || !previewOnly || options == null || uid == null) {
        if (transcriber == Transcriber.Omi) transcriptionNotice = TranscriptionNotice.MinutesRunningLow(0)
        return
    }
    previewOnly = false
    transcriber = Transcriber.Phone
    transcriptionNotice = TranscriptionNotice.SwitchedToPhone
    log(LogLevel.Info, "stt", "no transcription minutes left: switching to the phone")
    channel?.close("retry")
    channel = null
    val reopened = options.copy(clientTranscription = true)
    try {
        val channel = api.openListenSocket(uid, reopened)
        if (phase !is CaptureStore.Phase.Live) {
            channel.close("user_stop")
            return
        }
        this.channel = channel
        listenOptionsInUse = reopened
        listen(channel, acceptServerSegments = false)
    } catch (error: Exception) {
        log(LogLevel.Warning, "stt", "listen socket failed: $error")
        if (source == CaptureStore.Source.Phone && phoneBuffer != null) connectionLost()
    }
}

// MARK: Translation

/** `translating`: the backend's translations join the segments already shown (by id). */
internal fun CaptureStore.applyTranslations(incoming: List<LiveSegment>) {
    var updated = segments
    for (segment in incoming) {
        if (segment.translations.isEmpty()) continue
        val index = updated.indexOfFirst { it.id == segment.id }
        if (index < 0) continue
        updated = updated.toMutableList().also { it[index] = it[index].copy(translations = segment.translations) }
    }
    segments = updated
}

// MARK: Store audio on phone

/**
 * Settings > Privacy > Store audio on phone (Flutter `unlimitedLocalStorageEnabled`): every
 * recording also stays on the phone, not only the ones that could not be sent.
 */
internal val CaptureStore.keepsAudioOnPhone: Boolean
    get() = preferences.bool(Key.UnlimitedLocalStorageEnabled)

internal fun CaptureStore.beginKeptCopy(source: KeptAudioSource) {
    if (!keepsAudioOnPhone || keepsCopy) return
    val buffer = phoneBuffer ?: return
    buffer.beginKeptCopy(source)
    keepsCopy = true
}

internal fun CaptureStore.endKeptCopy() {
    if (!keepsCopy) return
    keepsCopy = false
    phoneBuffer?.endKeptCopy()
}

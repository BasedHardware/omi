package com.friend.ios.service.phonecalls

import com.friend.ios.network.endpoints.PhoneCallErrorDetail
import kotlinx.coroutines.flow.Flow

/**
 * Port of `PhoneCallEngine.swift`. The VoIP leg of a call (Twilio Voice + Telecom in the app; a fake
 * in tests). The call itself is placed by Twilio from the app (`Voice.connect`), Twilio's TwiML
 * webhook dials the number with the user's verified caller ID (backend `/v1/phone/twiml`); there is
 * no bridging to the phone's own dialer. Flutter: `android/.../phonecalls/PhoneCallsPlugin.kt`.
 */
interface PhoneCallEngine {
    suspend fun requestMicrophonePermission(): Boolean

    /** Asks the system for the call (Telecom) and connects it; events and audio follow on the streams. */
    suspend fun start(request: PhoneCallRequest): PhoneCallStreams

    fun end()

    fun setMuted(muted: Boolean)

    fun setSpeaker(on: Boolean)

    /** DTMF tones (menus, extensions). */
    fun sendDigits(digits: String)
}

data class PhoneCallRequest(
    val accessToken: String,
    /** E.164 destination (`To` of the TwiML request). */
    val phoneNumber: String,
    /** Carried as `CallId` to the TwiML webhook and as `call_id` to the transcription socket. */
    val callID: String,
    val contactName: String?,
)

sealed interface PhoneCallEngineEvent {
    data object Ringing : PhoneCallEngineEvent
    data object Connected : PhoneCallEngineEvent

    /** Hung up (either side, or from the system call UI). */
    data object Ended : PhoneCallEngineEvent
    data class Failed(val message: String) : PhoneCallEngineEvent

    /** Confirmed by the engine, including mute from the system call UI. */
    data class Muted(val muted: Boolean) : PhoneCallEngineEvent
    data class Speaker(val on: Boolean) : PhoneCallEngineEvent
}

/** About 100 ms of one side of the call: PCM16 mono at 48 kHz. */
class PhoneCallAudio(val channel: Channel, val pcm16: ByteArray) {
    enum class Channel(val rawValue: Byte) { You(1), Them(2) }

    override fun equals(other: Any?): Boolean =
        other is PhoneCallAudio && other.channel == channel && other.pcm16.contentEquals(pcm16)

    override fun hashCode(): Int = 31 * channel.hashCode() + pcm16.contentHashCode()
}

class PhoneCallStreams(val events: Flow<PhoneCallEngineEvent>, val audio: Flow<PhoneCallAudio>)

/** Why a call did not start or ended early; the screens word it. */
sealed interface PhoneCallFailure {
    data object AlreadyInProgress : PhoneCallFailure
    data object MicrophonePermission : PhoneCallFailure
    data object NoVerifiedNumber : PhoneCallFailure

    /** The backend refused (no verified number, plan without calls, quota reached ...). */
    data class Server(val detail: PhoneCallErrorDetail?) : PhoneCallFailure

    /** The call system or Twilio failed; the message is theirs. */
    data class Engine(val message: String) : PhoneCallFailure
}

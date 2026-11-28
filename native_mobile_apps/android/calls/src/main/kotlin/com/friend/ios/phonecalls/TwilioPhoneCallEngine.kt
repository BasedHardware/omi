package com.friend.ios.phonecalls

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import com.friend.ios.audio.MicrophonePermission
import com.friend.ios.service.phonecalls.PhoneCallAudio
import com.friend.ios.service.phonecalls.PhoneCallEngine
import com.friend.ios.service.phonecalls.PhoneCallEngineEvent
import com.friend.ios.service.phonecalls.PhoneCallRequest
import com.friend.ios.service.phonecalls.PhoneCallStreams
import com.twilio.voice.Call
import com.twilio.voice.CallException
import com.twilio.voice.ConnectOptions
import com.twilio.voice.Voice
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.receiveAsFlow
import java.util.UUID

/**
 * Port of `TwilioPhoneCallEngine.swift`. The VoIP leg of a phone call: Twilio Voice places it from
 * the app (`Voice.connect` with `To` and `CallId`; the backend's TwiML webhook dials with the
 * verified caller ID), Telecom shows it as a system call, and a custom audio device taps both sides
 * for the transcript. Flutter: `android/.../phonecalls/PhoneCallsPlugin.kt`. Outgoing only: Flutter
 * has no incoming calls, so neither does this. Runs on the main thread (the store's scope).
 */
class TwilioPhoneCallEngine(
    private val context: Context,
    private val permission: MicrophonePermission,
    private val makeCoordinator: (Context) -> CallSystemCoordinator = CallSystemCoordinator::make,
) : PhoneCallEngine {
    private class Prepared(val coordinator: CallSystemCoordinator, val audioDevice: CallRecordingAudioDevice)

    private var prepared: Prepared? = null
    private var call: Call? = null
    private var callUUID: UUID? = null
    private var events: Channel<PhoneCallEngineEvent>? = null
    private var audio: Channel<PhoneCallAudio>? = null
    private var coalescer: CallAudioCoalescer? = null
    private var proximity: PowerManager.WakeLock? = null
    private val main = Handler(Looper.getMainLooper())

    override suspend fun requestMicrophonePermission(): Boolean = permission.request()

    override suspend fun start(request: PhoneCallRequest): PhoneCallStreams {
        cleanup()
        val prepared = prepare()
        val events = Channel<PhoneCallEngineEvent>(Channel.UNLIMITED)
        val audio = Channel<PhoneCallAudio>(64, BufferOverflow.DROP_OLDEST)
        this.events = events
        this.audio = audio
        val coalescer = CallAudioCoalescer { audio.trySend(it) }
        this.coalescer = coalescer
        prepared.audioDevice.tap = { pcm, channel -> coalescer.append(pcm, channel) }
        prepared.audioDevice.micMuted = false

        val uuid = UUID.randomUUID()
        callUUID = uuid
        try {
            prepared.coordinator.startCall(uuid, request.phoneNumber, request.contactName)
        } catch (error: Exception) {
            if (callUUID == uuid) cleanup()
            throw error
        }
        if (callUUID != uuid) throw IllegalStateException("The call was ended while the system set it up")
        PhoneCallForegroundService.start(context, request.contactName ?: request.phoneNumber)
        val options = ConnectOptions.Builder(request.accessToken)
            .params(mapOf("To" to request.phoneNumber, "CallId" to request.callID))
            .build()
        call = Voice.connect(context, options, listener)
        return PhoneCallStreams(events.receiveAsFlow(), audio.receiveAsFlow())
    }

    override fun end() {
        val ending = call
        call = null
        ending?.disconnect()
        callUUID?.let { prepared?.coordinator?.endCall(it) }
        events?.trySend(PhoneCallEngineEvent.Ended)
        cleanup()
    }

    override fun setMuted(muted: Boolean) {
        call?.mute(muted)
        prepared?.audioDevice?.micMuted = muted
        events?.trySend(PhoneCallEngineEvent.Muted(muted))
    }

    override fun setSpeaker(on: Boolean) {
        // The route stays as it was when it cannot change; the button keeps showing it.
        if (prepared?.coordinator?.setSpeaker(on) == true) events?.trySend(PhoneCallEngineEvent.Speaker(on))
    }

    override fun sendDigits(digits: String) {
        call?.sendDigits(digits)
    }

    // MARK: Setup and teardown

    /** Telecom and Twilio's audio device are set up with the first call, not at launch. */
    private fun prepare(): Prepared {
        prepared?.let { return it }
        val audioDevice = CallRecordingAudioDevice()
        val coordinator = makeCoordinator(context)
        coordinator.onSystemEndCall = { systemEnded() }
        coordinator.onSystemMute = { muted -> setMuted(muted) }
        coordinator.onSystemSpeaker = { on -> events?.trySend(PhoneCallEngineEvent.Speaker(on)) }
        PhoneCallForegroundService.onHangUp = { main.post { end() } }
        Voice.setAudioDevice(audioDevice)
        return Prepared(coordinator, audioDevice).also { prepared = it }
    }

    /** Hung up from a headset, a watch or the system. */
    private fun systemEnded() {
        val ending = call ?: return
        call = null
        ending.disconnect()
        events?.trySend(PhoneCallEngineEvent.Ended)
        cleanup()
    }

    private fun cleanup() {
        call = null
        callUUID = null
        prepared?.audioDevice?.tap = null
        coalescer?.flush()
        coalescer = null
        events?.close()
        events = null
        // The flushed tail is queued on the coalescer's executor; close the audio stream after it.
        val audio = audio
        this.audio = null
        main.postDelayed({ audio?.close() }, 200)
        proximity?.takeIf { it.isHeld }?.release()
        proximity = null
        PhoneCallForegroundService.stop(context)
    }

    private fun report(event: PhoneCallEngineEvent, endedUUID: UUID? = null, failed: Boolean = false) {
        events?.trySend(event)
        if (endedUUID != null) {
            prepared?.coordinator?.reportEnded(endedUUID, failed)
            cleanup()
        }
    }

    /** The phone at the ear turns the screen off. */
    private fun holdProximity() {
        val power = context.getSystemService(PowerManager::class.java) ?: return
        if (!power.isWakeLockLevelSupported(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK)) return
        proximity = power.newWakeLock(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK, "omi:phone-call").apply {
            setReferenceCounted(false)
            acquire(4 * 60 * 60 * 1000L)
        }
    }

    // Twilio delivers these on the main thread (the thread that called connect).
    private val listener = object : Call.Listener {
        override fun onRinging(call: Call) {
            holdProximity()
            report(PhoneCallEngineEvent.Ringing)
        }

        override fun onConnected(call: Call) {
            callUUID?.let { prepared?.coordinator?.reportConnected(it) }
            report(PhoneCallEngineEvent.Connected)
        }

        override fun onConnectFailure(call: Call, error: CallException) {
            val uuid = callUUID ?: return
            if (this@TwilioPhoneCallEngine.call !== call) return
            report(PhoneCallEngineEvent.Failed(error.message ?: "Call failed (${error.errorCode})"), uuid, failed = true)
        }

        override fun onReconnecting(call: Call, error: CallException) {}

        override fun onReconnected(call: Call) {}

        override fun onDisconnected(call: Call, error: CallException?) {
            val uuid = callUUID ?: return
            if (this@TwilioPhoneCallEngine.call !== call) return
            val event = error?.let { PhoneCallEngineEvent.Failed(it.message ?: "Call failed (${it.errorCode})") } ?: PhoneCallEngineEvent.Ended
            report(event, uuid, failed = error != null)
        }
    }
}

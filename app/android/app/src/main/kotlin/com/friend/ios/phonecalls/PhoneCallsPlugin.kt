package com.friend.ios.phonecalls


import android.app.Activity
import android.content.Context
import android.media.AudioManager
import android.util.Log
import androidx.annotation.NonNull
import com.twilio.voice.Call
import com.twilio.voice.CallException
import com.twilio.voice.ConnectOptions
import com.twilio.voice.Voice
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Flutter plugin for phone call functionality via Twilio Voice SDK.
 * Handles method channel communication between Flutter and native Android.
 * Integrates with Twilio Voice SDK for VoIP calling with real-time audio capture.
 */
class PhoneCallsPlugin private constructor(
    private val context: Context,
    private val activity: Activity?
) : MethodChannel.MethodCallHandler, EventChannel.StreamHandler {

    private var eventSink: EventChannel.EventSink? = null
    private var accessToken: String? = null
    private var activeCall: Call? = null
    private var currentCallId: String? = null
    private var isMuted: Boolean = false
    private var isSpeakerOn: Boolean = false
    private val audioDevice = OmiRecordingAudioDevice()
    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())

    // Audio emissions drain through ONE main-looper post at a time carrying a
    // bounded queue of coalesced batches: a blocked main thread delays audio
    // instead of accumulating queued Handler runnables without bound (the
    // coalescer's byte caps cannot bound posts that are already queued).
    // Entries are tagged with a generation so batches queued before call
    // teardown can never reach the next call's sink.
    private val audioEmitLock = Any()
    private val pendingAudioEmissions = ArrayDeque<Triple<Int, ByteArray, Int>>()
    private var audioEmissionGeneration = 0
    private var audioDrainPosted = false

    private val audioEventCoalescer = AudioEventCoalescer { data, channel ->
        offerAudioEmission(data, channel)
    }

    companion object {
        private const val TAG = "PhoneCallsPlugin"
        private const val METHOD_CHANNEL = "com.omi/phone_calls"
        private const val EVENT_CHANNEL = "com.omi/phone_calls/events"

        // Bound on coalesced audio batches queued for main-thread delivery
        // (each ~100 ms per channel): a blocked main looper drops the oldest
        // queued batches instead of growing the queue without limit.
        private const val MAX_PENDING_AUDIO_EMISSIONS = 32

        fun registerWith(flutterEngine: FlutterEngine, context: Context) {
            val activity = context as? Activity
            val instance = PhoneCallsPlugin(context, activity)

            // Wire audio data callback to stream captured audio to Flutter
            instance.audioDevice.onAudioData = { data, channel ->
                instance.sendAudioDataEvent(data, channel)
            }

            // Set custom audio device before any Voice.connect() calls
            Voice.setAudioDevice(instance.audioDevice)

            val methodChannel = MethodChannel(
                flutterEngine.dartExecutor.binaryMessenger,
                METHOD_CHANNEL
            )
            methodChannel.setMethodCallHandler(instance)

            val eventChannel = EventChannel(
                flutterEngine.dartExecutor.binaryMessenger,
                EVENT_CHANNEL
            )
            eventChannel.setStreamHandler(instance)
        }
    }

    // Twilio Call.Listener for call state callbacks
    private val callListener = object : Call.Listener {
        override fun onRinging(call: Call) {
            Log.d(TAG, "Call ringing")
            sendCallStateEvent("ringing")
        }

        override fun onConnectFailure(call: Call, callException: CallException) {
            Log.e(TAG, "Call failed to connect: ${callException.message}")
            resetAudioMode()
            sendCallStateEvent("failed")
            activeCall = null
            currentCallId = null
        }

        override fun onConnected(call: Call) {
            Log.d(TAG, "Call connected")
            activeCall = call
            setAudioModeInCommunication()
            sendCallStateEvent("active")
        }

        override fun onReconnecting(call: Call, callException: CallException) {
            Log.d(TAG, "Call reconnecting: ${callException.message}")
            sendCallStateEvent("connecting")
        }

        override fun onReconnected(call: Call) {
            Log.d(TAG, "Call reconnected")
            sendCallStateEvent("active")
        }

        override fun onDisconnected(call: Call, callException: CallException?) {
            resetAudioMode()
            // Invalidate audio batches already queued for main-thread delivery
            // BEFORE flushing: a quickly-following new call must not receive
            // this call's stale queued batches, while the flush's own tail
            // emission below (the final ~100 ms) still delivers because it is
            // queued after the bump, under the new generation.
            synchronized(audioEmitLock) {
                audioEmissionGeneration++
            }
            audioEventCoalescer.flush()
            audioEventCoalescer.reset()
            if (callException != null) {
                Log.e(TAG, "Call disconnected with error: ${callException.message}")
                sendCallStateEvent("failed")
            } else {
                Log.d(TAG, "Call disconnected")
                sendCallStateEvent("ended")
            }
            activeCall = null
            currentCallId = null
        }
    }

    override fun onMethodCall(@NonNull call: MethodCall, @NonNull result: MethodChannel.Result) {
        when (call.method) {
            "initialize" -> handleInitialize(call, result)
            "makeCall" -> handleMakeCall(call, result)
            "endCall" -> handleEndCall(result)
            "toggleMute" -> handleToggleMute(call, result)
            "toggleSpeaker" -> handleToggleSpeaker(call, result)
            "sendDtmf" -> handleSendDtmf(call, result)
            "getAudioRoutes" -> {
                // Basic routes for Android — Speaker and Phone
                val routes = listOf(
                    mapOf("id" to "phone", "name" to "Phone", "type" to "iPhone"),
                    mapOf("id" to "speaker", "name" to "Speaker", "type" to "speaker")
                )
                result.success(routes)
            }
            "selectAudioRoute" -> {
                val routeId = call.argument<String>("routeId")
                val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
                if (routeId == "speaker") {
                    audioManager.isSpeakerphoneOn = true
                } else {
                    audioManager.isSpeakerphoneOn = false
                }
                result.success(true)
            }
            "isCallKitAvailable" -> result.success(false) // CallKit is iOS-only
            else -> result.notImplemented()
        }
    }

    // MARK: - Method Handlers

    private fun handleInitialize(call: MethodCall, result: MethodChannel.Result) {
        val token = call.argument<String>("accessToken")
        if (token == null) {
            result.error("INVALID_ARGS", "Missing accessToken", null)
            return
        }

        accessToken = token
        result.success(true)
    }

    private fun handleMakeCall(call: MethodCall, result: MethodChannel.Result) {
        val phoneNumber = call.argument<String>("phoneNumber")
        val callId = call.argument<String>("callId")

        if (phoneNumber == null || callId == null) {
            result.error("INVALID_ARGS", "Missing phoneNumber or callId", null)
            return
        }

        val token = accessToken
        if (token == null) {
            result.error("NOT_INITIALIZED", "Call initialize first", null)
            return
        }

        currentCallId = callId
        sendCallStateEvent("connecting")

        // Connect via Twilio Voice SDK
        val params = HashMap<String, String>()
        params["To"] = phoneNumber
        params["CallId"] = callId

        val connectOptions = ConnectOptions.Builder(token)
            .params(params)
            .build()

        activeCall = Voice.connect(context, connectOptions, callListener)
        result.success(true)
    }

    private fun handleEndCall(result: MethodChannel.Result) {
        if (activeCall == null) {
            resetAudioMode()
            sendCallStateEvent("ended")
        } else {
            // onDisconnected callback will handle resetAudioMode + state event
            activeCall?.disconnect()
        }
        result.success(null)
    }

    private fun handleToggleMute(call: MethodCall, result: MethodChannel.Result) {
        val muted = call.argument<Boolean>("muted") ?: false
        isMuted = muted
        activeCall?.mute(muted)
        audioDevice.isMicStreamMuted = muted
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            eventSink?.success(mapOf("type" to "muteConfirmed", "muted" to muted))
        }
        result.success(null)
    }

    private fun handleToggleSpeaker(call: MethodCall, result: MethodChannel.Result) {
        val speakerOn = call.argument<Boolean>("speakerOn") ?: false
        isSpeakerOn = speakerOn

        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        if (speakerOn) {
            // Disable Bluetooth SCO when switching to speaker
            if (audioManager.isBluetoothScoOn) {
                audioManager.stopBluetoothSco()
                audioManager.isBluetoothScoOn = false
            }
            audioManager.isSpeakerphoneOn = true
        } else {
            audioManager.isSpeakerphoneOn = false
            // Re-enable Bluetooth SCO if available
            if (audioManager.isBluetoothScoAvailableOffCall) {
                audioManager.startBluetoothSco()
                audioManager.isBluetoothScoOn = true
            }
        }
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            eventSink?.success(mapOf("type" to "speakerConfirmed", "speakerOn" to speakerOn))
        }
        result.success(null)
    }

    private fun handleSendDtmf(call: MethodCall, result: MethodChannel.Result) {
        val digits = call.argument<String>("digits") ?: ""
        activeCall?.sendDigits(digits)
        result.success(null)
    }

    // MARK: - Audio Mode

    private fun setAudioModeInCommunication() {
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        audioManager.isSpeakerphoneOn = false
        activity?.volumeControlStream = AudioManager.STREAM_VOICE_CALL

        // Route to Bluetooth headset if one is connected
        if (audioManager.isBluetoothScoAvailableOffCall || audioManager.isBluetoothScoOn) {
            audioManager.startBluetoothSco()
            audioManager.isBluetoothScoOn = true
        }
    }

    private fun resetAudioMode() {
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

        // Stop Bluetooth SCO if it was started
        if (audioManager.isBluetoothScoOn) {
            audioManager.stopBluetoothSco()
            audioManager.isBluetoothScoOn = false
        }

        audioManager.mode = AudioManager.MODE_NORMAL
        audioManager.isSpeakerphoneOn = false
        isSpeakerOn = false
        activity?.volumeControlStream = AudioManager.USE_DEFAULT_STREAM_TYPE
    }

    // MARK: - Event Sending

    private fun sendCallStateEvent(state: String) {
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            eventSink?.success(mapOf("type" to "callStateChanged", "state" to state))
        }
    }

    /**
     * Queue one coalesced audio batch for main-thread delivery. Hard cap on
     * queued entries (oldest dropped) so a blocked main looper delays audio
     * rather than accumulating queued work; posts at most one drainer at a
     * time. Entries carry the generation they were queued at so teardown
     * invalidates anything not yet drained.
     */
    private fun offerAudioEmission(data: ByteArray, channel: Int) {
        synchronized(audioEmitLock) {
            val entryGeneration = audioEmissionGeneration
            if (pendingAudioEmissions.size >= MAX_PENDING_AUDIO_EMISSIONS) {
                pendingAudioEmissions.removeFirst()
                Log.w(
                    TAG,
                    "dropping oldest queued audio emission; main looper stalled (queue=${pendingAudioEmissions.size})"
                )
            }
            pendingAudioEmissions.addLast(Triple(entryGeneration, data, channel))
            if (!audioDrainPosted) {
                audioDrainPosted = true
                mainHandler.post { drainAudioEmissions() }
            }
        }
    }

    /**
     * Drain queued audio emissions on the main thread. Runs at most one at a
     * time; stale-generation entries (queued before teardown) are skipped.
     */
    private fun drainAudioEmissions() {
        while (true) {
            val entry: Triple<Int, ByteArray, Int>? = synchronized(audioEmitLock) {
                // Stale (pre-teardown) entries sit at the head; skip them but
                // keep draining — current-generation entries (e.g. the flush
                // tail queued after teardown's bump) may sit behind them.
                while (pendingAudioEmissions.isNotEmpty() && pendingAudioEmissions.first().first != audioEmissionGeneration) {
                    pendingAudioEmissions.removeFirst()
                }
                if (pendingAudioEmissions.isEmpty()) {
                    audioDrainPosted = false
                    null
                } else {
                    pendingAudioEmissions.removeFirst()
                }
            }
            if (entry == null) return
            eventSink?.success(mapOf("type" to "audioData", "data" to entry.second, "channel" to entry.third))
        }
    }

    private fun sendAudioDataEvent(data: ByteArray, channel: Int) {
        // Coalesce ~100 ms per channel; per-buffer main-looper posts could not
        // keep up with 48 kHz dual-channel call audio.
        audioEventCoalescer.append(data, channel)
    }

    // MARK: - EventChannel.StreamHandler

    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
        eventSink = events
    }

    override fun onCancel(arguments: Any?) {
        eventSink = null
    }
}

/**
 * Batches 20 ms call-audio buffers into bounded events before they cross the
 * EventChannel: one main-looper post per ~100 ms per channel instead of one
 * per buffer. The hard cap is checked FIRST so it can never be shadowed by the
 * flush threshold; a saturated consumer drops the pending batch rather than
 * growing without bound. A generation counter invalidates work queued by a
 * previous call after [reset], so a new call cannot emit the old call's tail.
 */
private class AudioEventCoalescer(
    private val flushBytes: Int = 10_240,
    private val maxPendingBytes: Int = 40_960,
    private val emit: (ByteArray, Int) -> Unit
) {
    private val lock = Any()
    private val pending = HashMap<Int, java.io.ByteArrayOutputStream>()
    private var generation = 0

    fun append(data: ByteArray, channel: Int) {
        val entryGeneration = generation
        var toEmit: ByteArray? = null
        synchronized(lock) {
            val stream = pending.getOrPut(channel) { java.io.ByteArrayOutputStream() }
            stream.write(data)
            when {
                // Hard cap first: it must win when both thresholds would match.
                stream.size() > maxPendingBytes -> {
                    Log.w("AudioEventCoalescer", "dropping ${stream.size()} stalled bytes (channel $channel)")
                    pending.remove(channel)
                }
                stream.size() >= flushBytes -> {
                    toEmit = stream.toByteArray()
                    pending.remove(channel)
                }
            }
        }
        // A reset()/flush() that landed while this frame was coalescing ends the
        // previous call's emission eligibility; drop instead of crossing calls.
        if (toEmit != null && generation == entryGeneration) emit(toEmit!!, channel)
    }

    /** Emit each channel's partial buffer now (teardown must not lose the last ~100 ms),
     * then invalidate everything still associated with this call. */
    fun flush() {
        val toEmit = mutableListOf<Pair<ByteArray, Int>>()
        synchronized(lock) {
            for ((channel, stream) in pending) {
                toEmit.add(stream.toByteArray() to channel)
            }
            pending.clear()
            generation++
        }
        toEmit.forEach { (bytes, channel) -> emit(bytes, channel) }
    }

    /** Drop any partial buffer and invalidate everything still queued for this call. */
    fun reset() {
        synchronized(lock) {
            pending.clear()
            generation++
        }
    }
}

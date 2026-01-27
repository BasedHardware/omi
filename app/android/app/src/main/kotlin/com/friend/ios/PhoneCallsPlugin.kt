package com.friend.ios

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
    private val context: Context
) : MethodChannel.MethodCallHandler, EventChannel.StreamHandler {

    private var eventSink: EventChannel.EventSink? = null
    private var accessToken: String? = null
    private var activeCall: Call? = null
    private var currentCallId: String? = null
    private var isMuted: Boolean = false
    private var isSpeakerOn: Boolean = false

    companion object {
        private const val TAG = "PhoneCallsPlugin"
        private const val METHOD_CHANNEL = "com.omi/phone_calls"
        private const val EVENT_CHANNEL = "com.omi/phone_calls/events"

        fun registerWith(flutterEngine: FlutterEngine, context: Context) {
            val instance = PhoneCallsPlugin(context)

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
            sendCallStateEvent("failed")
            activeCall = null
            currentCallId = null
        }

        override fun onConnected(call: Call) {
            Log.d(TAG, "Call connected")
            activeCall = call
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
        activeCall?.disconnect()
        sendCallStateEvent("ended")
        activeCall = null
        currentCallId = null
        result.success(null)
    }

    private fun handleToggleMute(call: MethodCall, result: MethodChannel.Result) {
        val muted = call.argument<Boolean>("muted") ?: false
        isMuted = muted
        activeCall?.mute(muted)
        result.success(null)
    }

    private fun handleToggleSpeaker(call: MethodCall, result: MethodChannel.Result) {
        val speakerOn = call.argument<Boolean>("speakerOn") ?: false
        isSpeakerOn = speakerOn

        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.isSpeakerphoneOn = speakerOn
        result.success(null)
    }

    // MARK: - Event Sending

    private fun sendCallStateEvent(state: String) {
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            eventSink?.success(mapOf("type" to "callStateChanged", "state" to state))
        }
    }

    private fun sendAudioDataEvent(data: ByteArray, channel: Int) {
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            eventSink?.success(mapOf("type" to "audioData", "data" to data, "channel" to channel))
        }
    }

    // MARK: - EventChannel.StreamHandler

    override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
        eventSink = events
    }

    override fun onCancel(arguments: Any?) {
        eventSink = null
    }
}

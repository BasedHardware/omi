package com.friend.ios

import android.util.Log
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

/**
 * Singleton bridge that forwards WearOS watch audio data to Flutter
 * via an EventChannel and exposes control methods via a MethodChannel.
 *
 * Audio data arrives from [WearOsListenerService] (native) and is
 * streamed to Flutter's wearos_service.dart.
 */
object WearOsAudioBridge {

    private const val TAG = "WearOsAudioBridge"
    private const val AUDIO_CHANNEL = "com.friend.ios/wearos_audio"
    private const val CONTROL_CHANNEL = "com.friend.ios/wearos_control"

    private var eventSink: EventChannel.EventSink? = null
    private var isInitialized = false

    // Watch connection state
    var isWatchConnected: Boolean = false
        private set
    var watchNodeId: String? = null
        private set
    var watchDisplayName: String? = null
        private set

    /**
     * Initialize channels on the given FlutterEngine.
     * Called from MainActivity.configureFlutterEngine().
     */
    fun initialize(flutterEngine: FlutterEngine) {
        if (isInitialized) return

        val messenger = flutterEngine.dartExecutor.binaryMessenger

        // EventChannel for streaming audio data to Flutter
        EventChannel(messenger, AUDIO_CHANNEL).setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    Log.i(TAG, "Flutter listening for WearOS audio")
                    eventSink = events
                }

                override fun onCancel(arguments: Any?) {
                    Log.i(TAG, "Flutter stopped listening for WearOS audio")
                    eventSink = null
                }
            }
        )

        // MethodChannel for control queries from Flutter
        MethodChannel(messenger, CONTROL_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "isWatchConnected" -> {
                    result.success(isWatchConnected)
                }
                "getWatchDeviceInfo" -> {
                    result.success(
                        mapOf(
                            "deviceId" to (watchNodeId ?: "wearos-watch"),
                            "deviceModel" to (watchDisplayName ?: "WearOS Watch"),
                            "connected" to isWatchConnected
                        )
                    )
                }
                else -> {
                    result.notImplemented()
                }
            }
        }

        isInitialized = true
        Log.i(TAG, "WearOS audio bridge initialized")
    }

    /**
     * Called by [WearOsListenerService] when audio data is received from the watch.
     * Forwards the data to Flutter via the EventChannel.
     */
    fun onAudioDataReceived(
        audioData: ByteArray,
        isFinal: Boolean,
        segmentId: String,
        confidence: Double
    ) {
        val sink = eventSink
        if (sink == null) {
            Log.d(TAG, "Audio data received but no Flutter listener (${audioData.size} bytes)")
            return
        }

        try {
            val event = mapOf(
                "audioData" to audioData,
                "isFinal" to isFinal,
                "segmentId" to segmentId,
                "confidence" to confidence
            )
            sink.success(event)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send audio data to Flutter", e)
        }
    }

    /**
     * Called by [WearOsListenerService] when watch connection state changes.
     */
    fun onWatchConnectionChanged(nodeId: String?, displayName: String?, connected: Boolean) {
        watchNodeId = nodeId
        watchDisplayName = displayName
        isWatchConnected = connected
        Log.i(TAG, "Watch connection changed: connected=$connected node=$nodeId name=$displayName")

        // Notify Flutter of connection state change via event
        val sink = eventSink ?: return
        try {
            val event = mapOf(
                "connectionState" to connected,
                "nodeId" to (nodeId ?: ""),
                "displayName" to (displayName ?: "")
            )
            sink.success(event)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send connection state to Flutter", e)
        }
    }
}

package com.friend.ios

import android.content.Context
import android.content.Intent
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

object AmbientCaptureMethodChannel {
    const val CONTROL_CHANNEL = "omi/ambient_capture/control"
    const val AUDIO_CHANNEL = "omi/ambient_capture/audio"
    const val HEALTH_CHANNEL = "omi/ambient_capture/health"
    const val POLICY_CHANNEL = "omi/ambient_capture/policy"
    const val TELEMETRY_CHANNEL = "omi/ambient_capture/telemetry"

    private var audioSink: EventChannel.EventSink? = null
    private var healthSink: EventChannel.EventSink? = null
    private var policySink: EventChannel.EventSink? = null
    private var telemetrySink: EventChannel.EventSink? = null
    private var appContext: Context? = null

    fun registerWith(flutterEngine: FlutterEngine, context: Context) {
        appContext = context.applicationContext
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CONTROL_CHANNEL).setMethodCallHandler { call, result ->
            val ctx = appContext
            if (ctx == null) {
                result.error("ambient_context_missing", "Android context is not available", null)
                return@setMethodCallHandler
            }
            when (call.method) {
                "start" -> {
                    AmbientCaptureForegroundService.start(ctx)
                    result.success(true)
                }
                "stop" -> {
                    AmbientCaptureForegroundService.stop(ctx)
                    result.success(true)
                }
                "pause" -> {
                    AmbientCaptureForegroundService.command(ctx, AmbientCaptureForegroundService.ACTION_PAUSE)
                    result.success(true)
                }
                "resume" -> {
                    AmbientCaptureForegroundService.command(ctx, AmbientCaptureForegroundService.ACTION_RESUME)
                    result.success(true)
                }
                "privateMode" -> {
                    val enabled = call.argument<Boolean>("enabled") ?: true
                    val action = if (enabled) {
                        AmbientCaptureForegroundService.ACTION_PRIVATE_MODE
                    } else {
                        AmbientCaptureForegroundService.ACTION_RESUME
                    }
                    AmbientCaptureForegroundService.command(ctx, action)
                    result.success(true)
                }
                "getStatus" -> result.success(AmbientCaptureForegroundService.statusMap())
                "getHealthState" -> result.success(AmbientCaptureForegroundService.healthMap())
                "setFlutterState" -> {
                    val args = call.arguments as? Map<*, *> ?: emptyMap<String, Any>()
                    AmbientCaptureForegroundService.updateFlutterState(
                        socketConnected = args["socketConnected"] as? Boolean,
                        networkAvailable = args["networkAvailable"] as? Boolean,
                        walQueueDepth = (args["walQueueDepth"] as? Number)?.toInt(),
                    )
                    result.success(true)
                }
                "isAccessibilityEnabled" -> result.success(AmbientAccessibilityService.isEnabled)
                "openAccessibilitySettings" -> {
                    ctx.startActivity(Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    result.success(true)
                }
                else -> result.notImplemented()
            }
        }

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, POLICY_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "verifyPolicy" -> {
                    val args = call.arguments as? Map<*, *> ?: emptyMap<String, Any>()
                    result.success(AmbientPolicyVerifier.verify(args))
                }
                else -> result.notImplemented()
            }
        }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, AUDIO_CHANNEL).setStreamHandler(simpleHandler { audioSink = it })
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, HEALTH_CHANNEL).setStreamHandler(simpleHandler { healthSink = it })
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, POLICY_CHANNEL).setStreamHandler(simpleHandler { policySink = it })
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, TELEMETRY_CHANNEL).setStreamHandler(simpleHandler { telemetrySink = it })
    }

    private fun simpleHandler(setter: (EventChannel.EventSink?) -> Unit): EventChannel.StreamHandler {
        return object : EventChannel.StreamHandler {
            override fun onListen(arguments: Any?, events: EventChannel.EventSink?) = setter(events)
            override fun onCancel(arguments: Any?) = setter(null)
        }
    }

    fun emitAudio(bytes: ByteArray) {
        android.os.Handler(android.os.Looper.getMainLooper()).post { audioSink?.success(bytes) }
    }

    fun emitHealth(event: Map<String, Any?>) {
        android.os.Handler(android.os.Looper.getMainLooper()).post { healthSink?.success(event) }
    }

    fun emitPolicy(event: Map<String, Any?>) {
        android.os.Handler(android.os.Looper.getMainLooper()).post { policySink?.success(event) }
    }

    fun emitTelemetry(event: Map<String, Any?>) {
        android.os.Handler(android.os.Looper.getMainLooper()).post { telemetrySink?.success(event) }
    }
}

package com.friend.ios.sync

import android.content.Context
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Dart ↔ Android bridge for [SyncTransferForegroundService].
 *
 * Methods: `start` (optional `text`), `stop`. iOS does not register this
 * channel; Dart no-ops off Android.
 */
object SyncTransferPlugin {
    fun register(flutterEngine: FlutterEngine, context: Context) {
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            SyncTransferKeepAlivePolicy.METHOD_CHANNEL
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "start" -> {
                    val text = call.argument<String>("text")
                    result.success(SyncTransferForegroundService.start(context.applicationContext, text))
                }
                "stop" -> {
                    SyncTransferForegroundService.stop(context.applicationContext)
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }
}

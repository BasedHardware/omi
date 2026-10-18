package com.friend.ios.brain

import android.content.Context
import android.os.Handler
import android.os.Looper
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import android.util.Log
import java.util.concurrent.Executors

/**
 * MethodChannel wrapper around [IntentRouter], so Dart can call the local brain.
 *
 * Blocking work (model load, ~600 ms per route) runs on a single background
 * thread; results come back on the platform thread. One thread rather than a pool
 * because the router holds a single CompiledModel with reused tensor buffers,
 * which are not safe to share across concurrent invocations.
 */
/** Channel name, shared with the Dart side. */
object BrainChannel {
    const val CHANNEL = "com.friend.ios/local_brain"
}

class IntentRouterChannel(private val context: Context) : MethodChannel.MethodCallHandler {

    private companion object {
        const val TAG = "LocalBrainChannel"
    }

    private var channel: MethodChannel? = null
    private val worker = Executors.newSingleThreadExecutor { r ->
        Thread(r, "local-brain-router").apply { priority = Thread.NORM_PRIORITY + 1 }
    }
    private val main = Handler(Looper.getMainLooper())
    private val router = IntentRouter(context)

    fun register(messenger: BinaryMessenger) {
        // MethodChannel takes the messenger, so it is created here rather than in a
        // field: the messenger does not exist until the engine is configured.
        channel = MethodChannel(messenger, BrainChannel.CHANNEL).also {
            it.setMethodCallHandler(this)
        }
    }

    fun dispose() {
        channel?.setMethodCallHandler(null)
        channel = null
        worker.shutdown()
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "load" -> onLoad(result)
            "route" -> onRoute(call, result)
            "isReady" -> result.success(router.isReady)
            else -> result.notImplemented()
        }
    }

    private fun onLoad(result: MethodChannel.Result) {
        worker.execute {
            try {
                val started = System.nanoTime()
                router.load()
                val ms = (System.nanoTime() - started) / 1_000_000
                reply(result, mapOf("ok" to true, "loadMs" to ms))
            } catch (t: Throwable) {
                Log.w(TAG, "load failed: ${t.message}")
                reply(result, mapOf("ok" to false, "error" to (t.message ?: t.toString())))
            }
        }
    }

    private fun onRoute(call: MethodCall, result: MethodChannel.Result) {
        val text = call.argument<String>("text")
        if (text == null) {
            reply(result, mapOf("ok" to false, "error" to "missing 'text' argument"))
            return
        }
        worker.execute {
            try {
                if (!router.isReady) router.load()
                val d = router.route(text)
                reply(
                    result,
                    mapOf(
                        "ok" to true,
                        "action" to d.action,
                        "margin" to d.margin,
                        "declined" to d.declined,
                        "negated" to d.negated,
                        "runnerUp" to d.runnerUp,
                        "latencyMs" to d.latencyMs,
                        "reason" to d.reason,
                    ),
                )
            } catch (t: Throwable) {
                Log.w(TAG, "route failed: ${t.message}")
                reply(result, mapOf("ok" to false, "error" to (t.message ?: t.toString())))
            }
        }
    }

    private fun reply(result: MethodChannel.Result, payload: Map<String, Any?>) {
        main.post { result.success(payload) }
    }
}
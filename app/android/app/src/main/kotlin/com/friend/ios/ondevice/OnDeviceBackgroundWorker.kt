package com.friend.ios.ondevice

import android.content.Context
import androidx.work.*
import io.flutter.FlutterInjector
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.dart.DartExecutor
import io.flutter.plugin.common.MethodChannel
import kotlinx.coroutines.*
import java.lang.ref.WeakReference
import java.util.concurrent.TimeUnit

/** A charging-constrained worker reuses the UI isolate whenever it still exists.
 * Headless and UI WAL writers never run concurrently: UI startup waits for the
 * headless engine to stop before loading its WAL index. */
class OnDeviceBackgroundWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    companion object {
        private const val NAME = "omi-on-device-overflow"
        private const val CHANNEL = "com.omi/on_device"
        private var uiEngine = WeakReference<FlutterEngine>(null)
        private var headless: FlutterEngine? = null
        private var headlessStop = false
        private var completion: CompletableDeferred<Boolean>? = null
        private val idleReplies = mutableListOf<MethodChannel.Result>()

        fun attach(context: Context, engine: FlutterEngine) {
            uiEngine = WeakReference(engine)
            if (headless != null) headlessStop = true
            headless?.let { MethodChannel(it.dartExecutor.binaryMessenger, CHANNEL).invokeMethod("backgroundExpired", null) }
            MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
                when (call.method) {
                    "scheduleBackground" -> {
                        schedule(context.applicationContext, call.argument<Boolean>("charging") ?: true,
                            call.argument<String>("schedule") ?: "while_charging")
                        result.success(null)
                    }
                    "backgroundComplete" -> { completion?.complete(call.argument<Boolean>("success") ?: true); result.success(null) }
                    "awaitBackgroundIdle" -> if (headless == null) result.success(null) else idleReplies.add(result)
                    else -> result.notImplemented()
                }
            }
        }

        internal fun request(charging: Boolean, schedule: String): PeriodicWorkRequest {
            val minutes = if (schedule == "every_few_hours") 180L else 15L
            return PeriodicWorkRequestBuilder<OnDeviceBackgroundWorker>(minutes, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiresCharging(charging).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.MINUTES).build()
        }

        private fun enabled(context: Context): Boolean = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            .getBoolean("flutter.onDeviceOverflowConfigured", false)

        fun schedule(context: Context, charging: Boolean, schedule: String) {
            if (!enabled(context)) { WorkManager.getInstance(context).cancelUniqueWork(NAME); return }
            val request = request(charging, schedule)
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
        }
    }

    override suspend fun doWork(): Result {
        if (!enabled(applicationContext)) return Result.success()
        val done = CompletableDeferred<Boolean>()
        var engine: FlutterEngine? = null
        var finishedNormally = false
        return try {
            withContext(Dispatchers.Main) {
                completion = done
                val live = uiEngine.get()?.takeIf { it.dartExecutor.isExecutingDart }
                if (live != null) {
                    MethodChannel(live.dartExecutor.binaryMessenger, CHANNEL).invokeMethod("backgroundRun", null)
                } else {
                    val loader = FlutterInjector.instance().flutterLoader()
                    loader.startInitialization(applicationContext)
                    loader.ensureInitializationComplete(applicationContext, null)
                    engine = FlutterEngine(applicationContext)
                    headlessStop = false
                    headless = engine
                    PhoneBatteryChannel.register(applicationContext, engine!!)
                    MethodChannel(engine!!.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
                        if (call.method == "shouldStopBackground") { result.success(headlessStop) }
                        else if (call.method == "backgroundComplete") {
                            done.complete(call.argument<Boolean>("success") ?: false); result.success(null)
                        } else { result.notImplemented() }
                    }
                    engine!!.dartExecutor.executeDartEntrypoint(DartExecutor.DartEntrypoint(loader.findAppBundlePath(), "onDeviceOverflowBackground"))
                }
            }
            val success = withTimeout(8 * 60 * 1000L) { done.await() }
            finishedNormally = true
            if (success) Result.success() else Result.retry()
        } catch (_: CancellationException) {
            Result.retry()
        } catch (_: Exception) {
            Result.retry()
        } finally {
            withContext(NonCancellable + Dispatchers.Main) {
                val target = engine ?: uiEngine.get()
                if (!finishedNormally) target?.let { MethodChannel(it.dartExecutor.binaryMessenger, CHANNEL).invokeMethod("backgroundExpired", null) }
                engine?.destroy()
                headless = null
                headlessStop = false
                completion = null
                idleReplies.forEach { it.success(null) }; idleReplies.clear()
            }
        }
    }
}

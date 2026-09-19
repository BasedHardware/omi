package com.friend.ios

import android.content.Intent
import com.friend.ios.ble.BleHostApiImpl
import com.friend.ios.phonecalls.PhoneCallsPlugin
import com.friend.ios.ble.OmiBleForegroundService
import com.friend.ios.ble.OmiBleManager
import com.friend.ios.ble.OmiCompanionManager
import com.friend.ios.batch.CaptureAdmissionPolicy
import com.friend.ios.batch.OmiBackgroundAudioStreamer
import com.friend.ios.batch.CaptureAdmissionLatch
import com.friend.ios.phonemic.*
import android.os.Bundle
import androidx.annotation.NonNull
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
    private val CHANNEL = "com.friend.ios/notifyOnKill"
    private val NATIVE_BLE_TRANSCRIPT_CHANNEL = "com.friend.ios/native_ble_transcript"
    private var bleHostApiImpl: BleHostApiImpl? = null

    override fun configureFlutterEngine(@NonNull flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // Register Phone Calls Plugin
        PhoneCallsPlugin.registerWith(flutterEngine, this)

        // Register Native BLE Pigeon APIs
        OmiBleManager.initialize(application)
        getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
            .edit()
            .putBoolean("flutter.nativeBleForegroundReady", false)
            .apply()
        OmiBleManager.isFlutterAlive = true
        OmiBleManager.instance.flutterApi = BleFlutterApi(flutterEngine.dartExecutor.binaryMessenger)
        val hostApi = BleHostApiImpl { this }
        hostApi.initCompanionManager(this)
        bleHostApiImpl = hostApi
        BleHostApi.setUp(flutterEngine.dartExecutor.binaryMessenger, hostApi)

        // Register Native Phone Mic Pigeon APIs
        PhoneMicController.initialize(application)
        PhoneMicController.instance.bindFlutterApi(PhoneMicFlutterApi(flutterEngine.dartExecutor.binaryMessenger))
        PhoneMicHostApi.setUp(flutterEngine.dartExecutor.binaryMessenger, PhoneMicHostApiImpl(PhoneMicController.instance))
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, NATIVE_BLE_TRANSCRIPT_CHANNEL).setMethodCallHandler {
            call, result ->
            if (call.method == "drain") {
                result.success(OmiBackgroundAudioStreamer.drainCachedTranscriptMessages())
            } else {
                result.notImplemented()
            }
        }

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.omi/capture_policy").setMethodCallHandler {
            call, result ->
            if (call.method == "getRevision") {
                result.success(CaptureAdmissionLatch.highWaterRevision())
                return@setMethodCallHandler
            }
            if (call.method != "setMuted") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            val muted = call.argument<Boolean>("muted")
            val revision = when (val raw = call.argument<Any>("revision")) {
                is Int -> raw.toLong()
                is Long -> raw
                else -> null
            }
            if (muted == null || revision == null || revision < 0) {
                result.error("invalid_capture_policy", "muted must be bool and revision must be nonnegative", null)
                return@setMethodCallHandler
            }
            val persisted = runCatching {
                getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
                    .getString("flutter.capturePolicy", null)
            }.getOrNull()?.let(CaptureAdmissionPolicy::parse)
            if (revision < (persisted?.revision ?: 0L)) {
                result.error("stale_capture_policy", "capture policy revision is older than durable state", null)
                return@setMethodCallHandler
            }
            // Release only after the canonical unmuted revision is visible.
            // Mute does not depend on storage succeeding.
            if (!muted && (persisted == null || persisted.muted || persisted.revision != revision)) {
                result.error("capture_policy_not_durable", "unmuted policy is not durably persisted", null)
                return@setMethodCallHandler
            }
            if (!CaptureAdmissionLatch.apply(muted, revision)) {
                result.error("stale_capture_policy", "capture policy revision is older or conflicts", null)
                return@setMethodCallHandler
            }
            result.success(true)
        }

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler {
            call, result ->
            if(call.method == "setNotificationOnKillService"){
                 val title = call.argument<String>("title")
                val description = call.argument<String>("description")

                val serviceIntent = Intent(this, NotificationOnKillService::class.java)

                serviceIntent.putExtra("title", title)
                serviceIntent.putExtra("description", description)

                startService(serviceIntent)
                result.success(true)
            }else{
                result.notImplemented()
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        // Handle CompanionDeviceManager chooser result
        val address = bleHostApiImpl?.onActivityResult(requestCode, resultCode, data)
        if (address != null) {
            // Device selected — start foreground service (Dart will call manageDevice)
            OmiBleForegroundService.startService(this, address, caller = "MainActivity.onActivityResult")
        }
    }

    override fun onResume() {
        super.onResume()
        OmiBleManager.isAppForeground = true
    }

    override fun onPause() {
        OmiBleManager.isAppForeground = false
        super.onPause()
    }

    override fun onDestroy() {
        // The engine dies with the activity whether or not it is finishing, so these flags
        // must clear outside the isFinishing guard — a system-initiated destroy otherwise
        // leaves native deferring audio to an engine that is gone (issue #10847).
        // configureFlutterEngine re-arms both on the next attach.
        OmiBleManager.isFlutterAlive = false
        getSharedPreferences("FlutterSharedPreferences", MODE_PRIVATE)
            .edit()
            .putBoolean("flutter.nativeBleForegroundReady", false)
            .apply()
        if (isFinishing) {
            // Engine + main isolate die with the activity; a live capture session must not outlive its consumer.
            if (PhoneMicController.isInitialized) PhoneMicController.instance.onFlutterEngineDestroyed()
            // Background Mode and Transcribe Later both need the foreground service to keep
            // the device connected/capturing after a task close. With both off (default),
            // tear it down so the device disconnects when the app is closed.
            if (!OmiBleForegroundService.isPersistentModeEnabled(this)) {
                OmiBleForegroundService.stopService(this)
            }
        }
        super.onDestroy()
    }
}

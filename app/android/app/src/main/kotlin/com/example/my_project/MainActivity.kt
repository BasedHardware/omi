package com.friend.ios

import android.content.Intent
import android.os.Build
import androidx.annotation.NonNull
import androidx.activity.result.contract.ActivityResultContracts
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterFragmentActivity() {
    private val CHANNEL = "com.friend.ios/notifyOnKill"
    private var companionDeviceService: CompanionDeviceService? = null

    // Activity result launcher for CompanionDeviceManager association dialog
    // This must be registered before onCreate, hence lazy initialization
    private val associationLauncher = registerForActivityResult(
        ActivityResultContracts.StartIntentSenderForResult()
    ) { result ->
        companionDeviceService?.handleAssociationResult(result.resultCode, result.data)
    }

    override fun onResume() {
        super.onResume()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            CompanionDeviceBackgroundService.isAppInForeground = true
        }
    }

    override fun onPause() {
        super.onPause()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            CompanionDeviceBackgroundService.isAppInForeground = false
        }
    }

    override fun configureFlutterEngine(@NonNull flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // Initialize CompanionDeviceService for battery-efficient device presence detection
        companionDeviceService = CompanionDeviceService(this).apply {
            setAssociationLauncher(associationLauncher)
            register(flutterEngine)
        }

        // Set up presence listener to forward events to Flutter
        CompanionDevicePresenceReceiver.setPresenceListener(object : CompanionDevicePresenceReceiver.Companion.PresenceListener {
            override fun onDeviceAppeared(deviceAddress: String) {
                // This will be handled by the EventChannel in CompanionDeviceService
                // The event is sent via the broadcast receiver
            }

            override fun onDeviceDisappeared(deviceAddress: String) {
                // This will be handled by the EventChannel in CompanionDeviceService
            }
        })

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

    override fun onDestroy() {
        companionDeviceService?.dispose()
        super.onDestroy()
    }
}

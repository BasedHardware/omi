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
            // Reset notification cooldown whenever user opens the app
            CompanionDeviceBackgroundService.onAppCameToForeground(this)
        }
        // Check if launched from companion device notification
        handleCompanionDeviceIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // Handle case where app is already running and notification is tapped
        handleCompanionDeviceIntent(intent)
    }

    /**
     * When user taps the "device nearby" notification, reset the cooldown
     * so future notifications will work normally.
     */
    private fun handleCompanionDeviceIntent(intent: Intent?) {
        if (intent?.getBooleanExtra("from_companion_device", false) == true) {
            val deviceAddress = intent.getStringExtra("device_address")
            if (deviceAddress != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                CompanionDeviceBackgroundService.onUserRespondedToNotification(this, deviceAddress)
            }
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
        // This also sets up the presence listener to forward events to Flutter
        companionDeviceService = CompanionDeviceService(this).apply {
            setAssociationLauncher(associationLauncher)
            register(flutterEngine)
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

    override fun onDestroy() {
        companionDeviceService?.dispose()
        super.onDestroy()
    }
}

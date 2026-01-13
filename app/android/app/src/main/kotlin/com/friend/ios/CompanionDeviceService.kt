package com.friend.ios

import android.annotation.SuppressLint
import android.app.Activity
import android.companion.AssociationInfo
import android.companion.AssociationRequest
import android.companion.BluetoothLeDeviceFilter
import android.companion.CompanionDeviceManager
import android.content.Intent
import android.content.IntentSender
import android.os.Build
import android.os.ParcelUuid
import android.util.Log
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.IntentSenderRequest
import androidx.annotation.RequiresApi
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.UUID
import java.util.concurrent.Executor
import java.util.regex.Pattern

/**
 * Service that wraps Android's CompanionDeviceManager for device
 * presence detection and association management.
 */
class CompanionDeviceService(private val activity: Activity) {
    companion object {
        private const val TAG = "CompanionDeviceService"
        private const val METHOD_CHANNEL = "com.omi.companion_device"
        private const val EVENT_CHANNEL = "com.omi.companion_device/events"

        // Minimum API level for CompanionDeviceManager
        private const val MIN_API_LEVEL = Build.VERSION_CODES.O // API 26
        // API level for startObservingDevicePresence
        private const val PRESENCE_API_LEVEL = Build.VERSION_CODES.TIRAMISU // API 33
    }

    private var methodChannel: MethodChannel? = null
    private var eventChannel: EventChannel? = null
    private var eventSink: EventChannel.EventSink? = null

    // For launching the association dialog
    private var associationLauncher: ActivityResultLauncher<IntentSenderRequest>? = null
    private var pendingAssociationResult: MethodChannel.Result? = null

    private val companionDeviceManager: CompanionDeviceManager? by lazy {
        if (Build.VERSION.SDK_INT >= MIN_API_LEVEL) {
            activity.getSystemService(CompanionDeviceManager::class.java)
        } else {
            null
        }
    }

    /**
     * Set the activity result launcher for handling association dialog results
     */
    fun setAssociationLauncher(launcher: ActivityResultLauncher<IntentSenderRequest>) {
        associationLauncher = launcher
    }

    /**
     * Handle the result from the association dialog
     */
    fun handleAssociationResult(resultCode: Int, data: Intent?) {
        val result = pendingAssociationResult
        pendingAssociationResult = null

        if (resultCode == Activity.RESULT_OK) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val associationInfo = data?.getParcelableExtra(
                    CompanionDeviceManager.EXTRA_ASSOCIATION,
                    AssociationInfo::class.java
                )
                val address = associationInfo?.deviceMacAddress?.toString()
                Log.d(TAG, "Association dialog completed successfully: $address")
                sendEvent("associationCreated", mapOf("deviceAddress" to address))
                result?.success(mapOf("associated" to true, "deviceAddress" to address))
            } else {
                // For older APIs, try to get device from result
                @Suppress("DEPRECATION")
                val device = data?.getParcelableExtra<android.bluetooth.BluetoothDevice>(
                    CompanionDeviceManager.EXTRA_DEVICE
                )
                val address = device?.address
                Log.d(TAG, "Association dialog completed successfully (legacy): $address")
                sendEvent("associationCreated", mapOf("deviceAddress" to address))
                result?.success(mapOf("associated" to true, "deviceAddress" to address))
            }
        } else {
            Log.d(TAG, "Association dialog was cancelled or failed: $resultCode")
            result?.error("ASSOCIATION_CANCELLED", "User cancelled or association failed", null)
        }
    }

    /**
     * Register method and event channels with Flutter engine
     */
    fun register(flutterEngine: FlutterEngine) {
        methodChannel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            METHOD_CHANNEL
        ).apply {
            setMethodCallHandler { call, result -> handleMethodCall(call, result) }
        }

        eventChannel = EventChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            EVENT_CHANNEL
        ).apply {
            setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    eventSink = events
                    Log.d(TAG, "Event channel listening")
                }

                override fun onCancel(arguments: Any?) {
                    eventSink = null
                    Log.d(TAG, "Event channel cancelled")
                }
            })
        }

        // Set up presence listener to forward events from CompanionDevicePresenceReceiver to Flutter
        CompanionDevicePresenceReceiver.setPresenceListener(object : CompanionDevicePresenceReceiver.Companion.PresenceListener {
            override fun onDeviceAppeared(deviceAddress: String) {
                Log.d(TAG, "Forwarding deviceAppeared to Flutter: $deviceAddress")
                sendEvent("deviceAppeared", mapOf("deviceAddress" to deviceAddress))
            }

            override fun onDeviceDisappeared(deviceAddress: String) {
                Log.d(TAG, "Forwarding deviceDisappeared to Flutter: $deviceAddress")
                sendEvent("deviceDisappeared", mapOf("deviceAddress" to deviceAddress))
            }
        })
    }

    /**
     * Handle method calls from Flutter
     */
    private fun handleMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "isSupported" -> {
                result.success(isSupported())
            }
            "isPresenceObservingSupported" -> {
                result.success(isPresenceObservingSupported())
            }
            "getAssociatedDevices" -> {
                getAssociatedDevices(result)
            }
            "associate" -> {
                val deviceAddress = call.argument<String>("deviceAddress")
                val deviceName = call.argument<String>("deviceName")
                val serviceUuid = call.argument<String>("serviceUuid")
                associate(deviceAddress, deviceName, serviceUuid, result)
            }
            "disassociate" -> {
                val deviceAddress = call.argument<String>("deviceAddress")
                if (deviceAddress != null) {
                    disassociate(deviceAddress, result)
                } else {
                    result.error("INVALID_ARGUMENT", "deviceAddress is required", null)
                }
            }
            "startObservingDevicePresence" -> {
                val deviceAddress = call.argument<String>("deviceAddress")
                if (deviceAddress != null) {
                    startObservingDevicePresence(deviceAddress, result)
                } else {
                    result.error("INVALID_ARGUMENT", "deviceAddress is required", null)
                }
            }
            "stopObservingDevicePresence" -> {
                val deviceAddress = call.argument<String>("deviceAddress")
                if (deviceAddress != null) {
                    stopObservingDevicePresence(deviceAddress, result)
                } else {
                    result.error("INVALID_ARGUMENT", "deviceAddress is required", null)
                }
            }
            else -> {
                result.notImplemented()
            }
        }
    }

    /**
     * Check if CompanionDeviceManager is supported on this device
     */
    private fun isSupported(): Boolean {
        return Build.VERSION.SDK_INT >= MIN_API_LEVEL && companionDeviceManager != null
    }

    /**
     * Check if presence observing is supported (Android 13+)
     */
    private fun isPresenceObservingSupported(): Boolean {
        return Build.VERSION.SDK_INT >= PRESENCE_API_LEVEL && companionDeviceManager != null
    }

    /**
     * Get list of associated device addresses
     */
    @SuppressLint("MissingPermission")
    private fun getAssociatedDevices(result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < MIN_API_LEVEL || companionDeviceManager == null) {
            result.success(emptyList<String>())
            return
        }

        try {
            val associations = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                companionDeviceManager!!.myAssociations.map { it.deviceMacAddress?.toString() ?: "" }
            } else {
                @Suppress("DEPRECATION")
                companionDeviceManager!!.associations
            }
            result.success(associations.filterNotNull())
        } catch (e: Exception) {
            Log.e(TAG, "Error getting associated devices", e)
            result.error("GET_ASSOCIATIONS_FAILED", e.message, null)
        }
    }

    /**
     * Associate with a BLE device using CompanionDeviceManager
     * This shows a system dialog to the user for pairing
     */
    @RequiresApi(MIN_API_LEVEL)
    private fun associate(deviceAddress: String?, deviceName: String?, serviceUuid: String?, result: MethodChannel.Result) {
        if (companionDeviceManager == null) {
            result.error("NOT_SUPPORTED", "CompanionDeviceManager not available", null)
            return
        }

        if (associationLauncher == null) {
            result.error("NOT_INITIALIZED", "Association launcher not initialized", null)
            return
        }

        try {
            val filterBuilder = BluetoothLeDeviceFilter.Builder()

            // Add service UUID filter - this is the most reliable way to find BLE devices
            if (serviceUuid != null) {
                try {
                    val uuid = UUID.fromString(serviceUuid)
                    filterBuilder.setScanFilter(
                        android.bluetooth.le.ScanFilter.Builder()
                            .setServiceUuid(ParcelUuid(uuid))
                            .build()
                    )
                    Log.d(TAG, "Added service UUID filter: $serviceUuid")
                } catch (e: Exception) {
                    Log.e(TAG, "Invalid service UUID: $serviceUuid", e)
                }
            }

            // If we have a device name, add name filter to narrow down discovery
            if (deviceName != null) {
                filterBuilder.setNamePattern(Pattern.compile(Pattern.quote(deviceName)))
                Log.d(TAG, "Added name pattern filter: $deviceName")
            }

            val associationRequest = AssociationRequest.Builder()
                .addDeviceFilter(filterBuilder.build())
                .setSingleDevice(true) // We want a single specific device
                .build()

            // Store the result to return when dialog completes
            pendingAssociationResult = result

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val executor: Executor = activity.mainExecutor
                companionDeviceManager!!.associate(
                    associationRequest,
                    executor,
                    object : CompanionDeviceManager.Callback() {
                        override fun onAssociationPending(intentSender: IntentSender) {
                            Log.d(TAG, "Association pending, launching dialog")
                            // Launch the system dialog
                            val request = IntentSenderRequest.Builder(intentSender).build()
                            associationLauncher?.launch(request)
                        }

                        override fun onAssociationCreated(associationInfo: AssociationInfo) {
                            // This is called when association is created without user interaction
                            // (e.g., when using SingleDevice mode and device is already known)
                            val address = associationInfo.deviceMacAddress?.toString()
                            Log.d(TAG, "Association created directly: $address")
                            sendEvent("associationCreated", mapOf("deviceAddress" to address))
                            pendingAssociationResult?.success(mapOf("associated" to true, "deviceAddress" to address))
                            pendingAssociationResult = null
                        }

                        override fun onFailure(error: CharSequence?) {
                            Log.e(TAG, "Association failed: $error")
                            pendingAssociationResult?.error("ASSOCIATION_FAILED", error?.toString(), null)
                            pendingAssociationResult = null
                        }
                    }
                )
            } else {
                @Suppress("DEPRECATION")
                companionDeviceManager!!.associate(
                    associationRequest,
                    object : CompanionDeviceManager.Callback() {
                        @Deprecated("Deprecated in Java")
                        override fun onDeviceFound(chooserLauncher: IntentSender) {
                            Log.d(TAG, "Device found, launching chooser dialog")
                            // Launch the system dialog
                            val request = IntentSenderRequest.Builder(chooserLauncher).build()
                            associationLauncher?.launch(request)
                        }

                        override fun onFailure(error: CharSequence?) {
                            Log.e(TAG, "Association failed: $error")
                            pendingAssociationResult?.error("ASSOCIATION_FAILED", error?.toString(), null)
                            pendingAssociationResult = null
                        }
                    },
                    null
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error associating device", e)
            pendingAssociationResult = null
            result.error("ASSOCIATION_ERROR", e.message, null)
        }
    }

    /**
     * Remove association with a device
     */
    @SuppressLint("MissingPermission")
    private fun disassociate(deviceAddress: String, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < MIN_API_LEVEL || companionDeviceManager == null) {
            result.error("NOT_SUPPORTED", "CompanionDeviceManager not available", null)
            return
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                // Find association by MAC address (case-insensitive)
                val association = companionDeviceManager!!.myAssociations.find {
                    it.deviceMacAddress?.toString().equals(deviceAddress, ignoreCase = true)
                }
                if (association != null) {
                    companionDeviceManager!!.disassociate(association.id)
                    result.success(true)
                } else {
                    // Device not associated, that's fine
                    result.success(true)
                }
            } else {
                @Suppress("DEPRECATION")
                companionDeviceManager!!.disassociate(deviceAddress)
                result.success(true)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error disassociating device", e)
            // Don't fail, just log
            result.success(false)
        }
    }

    /**
     * Start observing device presence (Android 13+)
     * This is the key API for battery-efficient device detection
     */
    @SuppressLint("MissingPermission")
    private fun startObservingDevicePresence(deviceAddress: String, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < PRESENCE_API_LEVEL) {
            // Not supported, but don't fail - just return false
            result.success(false)
            return
        }

        if (companionDeviceManager == null) {
            result.success(false)
            return
        }

        try {
            // Find the association for this device (case-insensitive MAC address comparison)
            val association = companionDeviceManager!!.myAssociations.find {
                it.deviceMacAddress?.toString().equals(deviceAddress, ignoreCase = true)
            }

            if (association == null) {
                result.success(false)
                return
            }

            companionDeviceManager!!.startObservingDevicePresence(deviceAddress)
            Log.d(TAG, "Successfully started observing presence for $deviceAddress")
            result.success(true)
        } catch (e: Exception) {
            Log.e(TAG, "Error starting presence observation: ${e.message}", e)
            result.success(false)
        }
    }

    /**
     * Stop observing device presence
     */
    @SuppressLint("MissingPermission")
    private fun stopObservingDevicePresence(deviceAddress: String, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < PRESENCE_API_LEVEL) {
            result.success(true)
            return
        }

        if (companionDeviceManager == null) {
            result.success(true)
            return
        }

        try {
            companionDeviceManager!!.stopObservingDevicePresence(deviceAddress)
            Log.d(TAG, "Stopped observing presence for $deviceAddress")
            result.success(true)
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping presence observation", e)
            result.success(true)
        }
    }

    /**
     * Send event to Flutter via EventChannel
     */
    private fun sendEvent(eventType: String, data: Map<String, Any?>) {
        val event = mutableMapOf<String, Any?>("type" to eventType)
        event.putAll(data)
        eventSink?.success(event)
    }

    /**
     * Clean up resources
     */
    fun dispose() {
        methodChannel?.setMethodCallHandler(null)
        eventChannel?.setStreamHandler(null)
        eventSink = null
        pendingAssociationResult = null
    }
}

package com.friend.ios

import android.app.Activity
import android.bluetooth.le.ScanFilter
import android.companion.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Wraps CompanionDeviceManager for BLE device association and presence observation.
 * This enables system-level device presence detection — no polling needed.
 *
 * Handles pairing via CompanionDeviceManager and presence observation.
 */
class OmiCompanionManager(
    private val context: Context,
    private val getActivity: () -> Activity?
) {
    companion object {
        private const val TAG = "OmiBle.CompanionMgr"
        const val COMPANION_REQUEST_CODE = 42
    }

    private val companionDeviceManager =
        context.getSystemService(Context.COMPANION_DEVICE_SERVICE) as CompanionDeviceManager

    /**
     * Start association flow — scans for BLE devices and shows system chooser UI.
     * Optionally filters by a service UUID (e.g., Omi service UUID).
     */
    fun associate(deviceAddress: String? = null, serviceUuid: String? = null) {
        disassociateAll()

        val requestBuilder = AssociationRequest.Builder()
            .setSingleDevice(deviceAddress != null) // Single device if we know the address

        val filterBuilder = BluetoothLeDeviceFilter.Builder()
        val scanFilterBuilder = ScanFilter.Builder()
        var hasScanFilter = false

        if (deviceAddress != null) {
            try {
                scanFilterBuilder.setDeviceAddress(deviceAddress)
                hasScanFilter = true
            } catch (e: Exception) {
                Log.w(TAG, "Invalid device address for filter: $deviceAddress, ${e.message}")
            }
        }

        if (serviceUuid != null) {
            try {
                scanFilterBuilder.setServiceUuid(ParcelUuid.fromString(serviceUuid))
                hasScanFilter = true
            } catch (e: Exception) {
                Log.w(TAG, "Invalid service UUID for filter: $serviceUuid, ${e.message}")
            }
        }

        if (hasScanFilter) {
            filterBuilder.setScanFilter(scanFilterBuilder.build())
        }

        requestBuilder.addDeviceFilter(filterBuilder.build())

        val request = requestBuilder.build()

        Log.d(TAG, "Calling CompanionDeviceManager.associate")
        if (Build.VERSION.SDK_INT >= 33) {
            val executor = ContextCompat.getMainExecutor(context)
            companionDeviceManager.associate(request, executor, object : CompanionDeviceManager.Callback() {
                override fun onDeviceFound(chooserLauncher: android.content.IntentSender) {
                    Log.d(TAG, "onDeviceFound → launching chooser")
                    launchChooser(chooserLauncher)
                }

                override fun onFailure(error: CharSequence?) {
                    Log.e(TAG, "associate() failed: $error")
                }
            })
        } else {
            @Suppress("deprecation")
            companionDeviceManager.associate(request, object : CompanionDeviceManager.Callback() {
                override fun onDeviceFound(chooserLauncher: android.content.IntentSender) {
                    Log.d(TAG, "onDeviceFound → launching chooser")
                    launchChooser(chooserLauncher)
                }

                override fun onFailure(error: CharSequence?) {
                    Log.e(TAG, "associate() failed: $error")
                }
            }, Handler(Looper.getMainLooper()))
        }
    }

    private fun launchChooser(chooserLauncher: android.content.IntentSender) {
        val activity = getActivity()
        if (activity == null) {
            Log.e(TAG, "Cannot launch chooser: activity is null")
            return
        }
        try {
            activity.startIntentSenderForResult(
                chooserLauncher, COMPANION_REQUEST_CODE,
                null, 0, 0, 0
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start chooser", e)
        }
    }

    /**
     * Handle activity result from the chooser.
     * Returns the selected device MAC address, or null.
     */
    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): String? {
        if (requestCode != COMPANION_REQUEST_CODE) return null
        if (resultCode != Activity.RESULT_OK) return null

        @Suppress("deprecation")
        val scanResult = data?.getParcelableExtra<android.bluetooth.le.ScanResult>(
            CompanionDeviceManager.EXTRA_DEVICE
        ) ?: return null

        val address = scanResult.device.address
        Log.d(TAG, "Selected device: $address")

        startObserving()
        return address
    }

    @Suppress("deprecation")
    fun getAssociations(): List<String> = companionDeviceManager.associations

    fun getMacAddresses(): List<String> {
        return if (Build.VERSION.SDK_INT >= 33) {
            companionDeviceManager.myAssociations.mapNotNull {
                it.deviceMacAddress?.toString()
            }
        } else {
            @Suppress("deprecation")
            companionDeviceManager.associations
        }
    }

    fun disassociate(idOrAddress: String) {
        try {
            companionDeviceManager.disassociate(idOrAddress)
        } catch (e: Exception) {
            Log.w(TAG, "disassociate failed: ${e.message}")
        }
    }

    fun disassociateAll() {
        getAssociations().forEach { disassociate(it) }
    }

    /**
     * Start observing device presence for the most recent association.
     * This enables BleCompanionService to receive appear/disappear callbacks.
     * Requires API 33+ (startObservingDevicePresence). On older APIs, auto-reconnect
     * relies on autoConnect=true GATT and ForegroundService.
     */
    @Suppress("deprecation")
    fun startObserving() {
        if (Build.VERSION.SDK_INT < 33) {
            Log.d(TAG, "startObserving: skipped (API ${Build.VERSION.SDK_INT} < 33)")
            return
        }
        stopObserving()
        val associations = companionDeviceManager.myAssociations
        if (associations.isEmpty()) return

        val association = associations.last()

        if (Build.VERSION.SDK_INT >= 36) {
            try {
                val request = ObservingDevicePresenceRequest.Builder()
                    .setAssociationId(association.id)
                    .build()
                companionDeviceManager.startObservingDevicePresence(request)
                Log.d(TAG, "Observing device presence (API 36+) for association ${association.id}")
            } catch (e: Exception) {
                Log.w(TAG, "startObserving (API 36+) failed: ${e.message}")
            }
        } else {
            val mac = association.deviceMacAddress
            if (mac != null) {
                try {
                    companionDeviceManager.startObservingDevicePresence(mac.toString())
                    Log.d(TAG, "Started observing device presence for $mac")
                } catch (e: Exception) {
                    Log.w(TAG, "startObserving failed: ${e.message}")
                }
            }
        }
    }

    @Suppress("deprecation")
    fun stopObserving() {
        if (Build.VERSION.SDK_INT < 33) return
        for (association in companionDeviceManager.myAssociations) {
            try {
                if (Build.VERSION.SDK_INT >= 36) {
                    val request = ObservingDevicePresenceRequest.Builder()
                        .setAssociationId(association.id)
                        .build()
                    companionDeviceManager.stopObservingDevicePresence(request)
                } else {
                    val mac = association.deviceMacAddress
                    if (mac != null) {
                        companionDeviceManager.stopObservingDevicePresence(mac.toString())
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "stopObserving failed: ${e.message}")
            }
        }
    }
}

package com.friend.ios

import android.app.Activity
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Implements the Pigeon BleHostApi interface.
 * Connection lifecycle is routed to OmiBleForegroundService (the single owner).
 * Characteristic operations are delegated to OmiBleManager (the GATT wrapper).
 */
class BleHostApiImpl(private val getActivity: () -> Activity?) : BleHostApi {

    companion object {
        private const val TAG = "OmiBle.HostApi"
    }

    private val bleManager get() = OmiBleManager.instance

    private var companionManager: OmiCompanionManager? = null
    private var companionAssociationCallback: ((Result<String>) -> Unit)? = null

    fun initCompanionManager(activity: Activity) {
        companionManager = OmiCompanionManager(activity, getActivity)
    }

    // ── Scanning ──

    override fun startScan(timeoutSeconds: Long, serviceUuids: List<String>) {
        bleManager.startScan(timeoutSeconds.toInt(), serviceUuids)
    }

    override fun stopScan() {
        bleManager.stopScan()
    }

    // ── Connection lifecycle (routed to foreground service) ──

    override fun manageDevice(uuid: String, requiresBond: Boolean) {
        Log.i(TAG, "manageDevice: $uuid, requiresBond=$requiresBond")
        val context = getActivity()?.applicationContext ?: return
        OmiBleForegroundService.startService(context, uuid, requiresBond = requiresBond, caller = "Dart")
    }

    override fun unmanageDevice(uuid: String) {
        Log.i(TAG, "unmanageDevice: $uuid")
        OmiBleForegroundService.instance?.unmanageDevice(uuid)
            ?: bleManager.closeGatt(uuid) // Fallback if service not running
    }

    // ── Bonding ──

    override fun requestBond(uuid: String, callback: (Result<Boolean>) -> Unit) {
        bleManager.requestBond(uuid, callback)
    }

    // ── Characteristic operations (direct to GATT wrapper) ──

    override fun readCharacteristic(
        peripheralUuid: String,
        serviceUuid: String,
        characteristicUuid: String,
        callback: (Result<ByteArray>) -> Unit
    ) {
        bleManager.readCharacteristic(peripheralUuid, serviceUuid, characteristicUuid, callback)
    }

    override fun writeCharacteristic(
        peripheralUuid: String,
        serviceUuid: String,
        characteristicUuid: String,
        data: ByteArray,
        callback: (Result<Unit>) -> Unit
    ) {
        bleManager.writeCharacteristic(peripheralUuid, serviceUuid, characteristicUuid, data, callback)
    }

    override fun subscribeCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String) {
        bleManager.subscribeCharacteristic(peripheralUuid, serviceUuid, characteristicUuid)
    }

    override fun unsubscribeCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String) {
        bleManager.unsubscribeCharacteristic(peripheralUuid, serviceUuid, characteristicUuid)
    }

    // ── State ──

    override fun getBluetoothState(): String {
        return bleManager.getBluetoothState()
    }

    override fun isPeripheralConnected(uuid: String): Boolean {
        return bleManager.isPeripheralConnected(uuid)
    }

    // ── Diagnostics ──

    override fun startRssiStreaming(uuid: String) {
        bleManager.isRssiStreamingEnabled = true
    }

    override fun stopRssiStreaming(uuid: String) {
        bleManager.isRssiStreamingEnabled = false
    }

    override fun getBatteryHistory(uuid: String, callback: (Result<List<BleBatteryPoint>>) -> Unit) {
        callback(Result.success(bleManager.getBatteryHistory(uuid)))
    }

    override fun getDeviceDiagnostics(uuid: String, callback: (Result<BleDeviceDiagnostics>) -> Unit) {
        val service = OmiBleForegroundService.instance
        if (service != null) {
            callback(Result.success(service.getDeviceDiagnostics(uuid)))
        } else {
            callback(Result.success(BleDeviceDiagnostics(
                disconnectHistory = emptyList(),
                reconnectionCount = 0,
                connectedAt = 0,
                failToConnectCount = 0
            )))
        }
    }

    // ── CompanionDeviceManager ──

    override fun hasCompanionDeviceAssociation(): Boolean {
        val cm = companionManager ?: return false
        return cm.getMacAddresses().isNotEmpty()
    }

    override fun requestCompanionDeviceAssociation(deviceAddress: String, callback: (Result<String>) -> Unit) {
        Log.i(TAG, "requestCompanionDeviceAssociation: $deviceAddress")

        val cm = companionManager ?: run {
            val activity = getActivity()
            if (activity != null) {
                OmiCompanionManager(activity, getActivity).also { companionManager = it }
            } else {
                Log.w(TAG, "Cannot associate: no activity")
                callback(Result.success(""))
                return
            }
        }

        companionAssociationCallback = callback
        cm.associate(deviceAddress = deviceAddress)
    }

    /**
     * Called from MainActivity.onActivityResult to handle companion chooser result.
     */
    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): String? {
        val address = companionManager?.onActivityResult(requestCode, resultCode, data)
        val cb = companionAssociationCallback
        companionAssociationCallback = null

        if (address != null) {
            cb?.invoke(Result.success(address))
        } else {
            cb?.invoke(Result.success(""))
        }
        return address
    }
}

package com.friend.ios.ble

import com.friend.ios.BleBatteryPoint
import com.friend.ios.BleDeviceDiagnostics
import com.friend.ios.BleDisconnectEvent
import com.friend.ios.BleHostApi


import android.app.Activity
import android.content.Context
import android.bluetooth.BluetoothAdapter
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject

/**
 * Implements the Pigeon BleHostApi interface.
 * Connection lifecycle is routed to OmiBleForegroundService (the single owner).
 * Characteristic operations are delegated to OmiBleManager (the GATT wrapper).
 */
class BleHostApiImpl(private val getActivity: () -> Activity?) : BleHostApi {

    companion object {
        private const val TAG = "OmiBle.HostApi"
        private const val REQUEST_ENABLE_BT = 43
    }

    private val bleManager get() = OmiBleManager.instance

    private var companionManager: OmiCompanionManager? = null
    private var companionAssociationCallback: ((Result<String>) -> Unit)? = null
    private var enableBluetoothCallback: ((Result<Boolean>) -> Unit)? = null

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

    override fun enableBluetooth(callback: (Result<Boolean>) -> Unit) {
        if (bleManager.getBluetoothState() == "on") {
            callback(Result.success(true))
            return
        }
        if (enableBluetoothCallback != null) {
            // A system prompt is already in flight; don't overwrite the pending
            // callback (which would leave its Future hanging) or stack a second
            // dialog. Report the current (still-off) state to this caller.
            callback(Result.success(false))
            return
        }
        val activity = getActivity()
        if (activity == null) {
            Log.w(TAG, "enableBluetooth: no activity")
            callback(Result.success(false))
            return
        }
        enableBluetoothCallback = callback
        try {
            activity.startActivityForResult(Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE), REQUEST_ENABLE_BT)
        } catch (e: Exception) {
            Log.e(TAG, "enableBluetooth: failed to launch system prompt", e)
            enableBluetoothCallback = null
            callback(Result.success(false))
        }
    }

    override fun isPeripheralConnected(uuid: String): Boolean {
        return bleManager.isPeripheralConnected(uuid)
    }

    // ── Diagnostics ──

    override fun startRssiStreaming(uuid: String) {
        bleManager.isRssiStreamingEnabled = true
        bleManager.sampleRssi(uuid)
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
            val context = getActivity()?.applicationContext
            val addr = uuid.uppercase()
            val prefs = context?.getSharedPreferences("ble_diagnostics", Context.MODE_PRIVATE)
            val history = try { JSONArray(prefs?.getString("disconnect_history_$addr", "[]")) } catch (_: Exception) { JSONArray() }
            val events = (0 until history.length()).mapNotNull { i -> history.optJSONObject(i) }.map { obj ->
                BleDisconnectEvent(
                    timestamp = obj.optLong("timestamp", 0L), reason = obj.optString("reason", "unknown"),
                    reasonCode = obj.optLong("reasonCode", -1L), isManual = obj.optBoolean("isManual", false),
                    eventType = obj.optString("eventType", "disconnect"), lastRssi = obj.optLong("lastRssi", 0L),
                    connectionDurationMs = obj.optLong("connectionDurationMs", 0L), appState = obj.optString("appState", ""),
                    timeToReconnectMs = obj.optLong("timeToReconnectMs", 0L), rssiTrend = obj.optString("rssiTrend", "")
                )
            }
            callback(Result.success(BleDeviceDiagnostics(
                disconnectHistory = events,
                reconnectionCount = (prefs?.getInt("reconnect_count_$addr", 0) ?: 0).toLong(),
                connectedAt = 0,
                failToConnectCount = (prefs?.getInt("fail_to_connect_count_$addr", 0) ?: 0).toLong(),
                nativeBackgroundBytesConsumed = 0,
                nativeBackgroundPacketsConsumed = 0
            )))
        }
    }

    override fun getExtendedDeviceDiagnostics(uuid: String, callback: (Result<String>) -> Unit) {
        val service = OmiBleForegroundService.instance
        if (service != null) {
            callback(Result.success(service.getExtendedDeviceDiagnostics(uuid)))
            return
        }
        val addr = uuid.uppercase()
        val context = getActivity()?.applicationContext
        val prefs = context?.getSharedPreferences("ble_diagnostics", Context.MODE_PRIVATE)
        fun array(key: String): JSONArray = try { JSONArray(prefs?.getString(key, "[]")) } catch (_: Exception) { JSONArray() }
        val battery = context?.getSharedPreferences("battery_history", Context.MODE_PRIVATE)
        val batteryHistory = try { JSONArray(battery?.getString("battery_history_$addr", "[]")) } catch (_: Exception) { JSONArray() }
        val samples = JSONArray()
        bleManager.rssiHistory[addr]?.let { deque -> synchronized(deque) {
            deque.forEach { (ts, rssi) -> samples.put(JSONObject().put("ts", ts).put("rssi", rssi)) }
        } }
        callback(Result.success(JSONObject()
            .put("disconnect_history_v2", array("disconnect_history_$addr"))
            .put("battery_history_v2", batteryHistory)
            .put("rssi_samples", samples)
            .put("firmware_diagnostics", array("firmware_$addr"))
            .put("lifecycle_events", array("lifecycle"))
            .put("ble_log", array("log_$addr"))
            .put("counters_since", prefs?.getLong("counters_since_$addr", 0L)?.takeIf { it > 0L } ?: JSONObject.NULL)
            .toString()))
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
        if (requestCode == REQUEST_ENABLE_BT) {
            val cb = enableBluetoothCallback
            enableBluetoothCallback = null
            cb?.invoke(Result.success(resultCode == Activity.RESULT_OK))
            return null
        }

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

package com.lynxshell.modules

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.ParcelUuid
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

private const val OMI_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
private const val OMI_AUDIO_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"

class OmiBleController(context: Context) {
    private val adapter: BluetoothAdapter? =
        context.getSystemService(BluetoothAdapter::class.java)
    private val scanner get() = adapter?.bluetoothLeScanner
    private val results = ConcurrentHashMap<String, JSONObject>()
    private var scanActive = false
    private var gatt: BluetoothGatt? = null
    private var connectionState = "disconnected"
    private var lastError: String? = null
    private var audioNotifications = false
    private var lastPacketBytes = 0

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            results[device.address] = JSONObject()
                .put("id", device.address)
                .put("name", device.name ?: result.scanRecord?.deviceName ?: "Omi")
                .put("rssi", result.rssi)
                .put("source", "android-bluetooth-le")
        }

        override fun onScanFailed(errorCode: Int) {
            scanActive = false
            lastError = "BLE scan failed: $errorCode"
        }
    }

    fun capabilities(): JSONObject = JSONObject()
        .put("available", adapter != null)
        .put("enabled", adapter?.isEnabled == true)
        .put("scan", scanner != null)
        .put("connection", connectionState)
        .put("scanActive", scanActive)
        .put("lastError", lastError ?: JSONObject.NULL)
        .put("audioNotifications", audioNotifications)
        .put("lastPacketBytes", lastPacketBytes)
        .put("implementation", "android-bluetooth-le")

    @SuppressLint("MissingPermission")
    fun startScan(): JSONObject {
        val bleScanner = scanner ?: return capabilities().put("lastError", "Bluetooth LE scanner unavailable")
        results.clear()
        lastError = null
        val filter = ScanFilter.Builder()
            .setServiceUuid(ParcelUuid.fromString(OMI_SERVICE_UUID))
            .build()
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        bleScanner.startScan(listOf(filter), settings, scanCallback)
        scanActive = true
        return capabilities()
    }

    @SuppressLint("MissingPermission")
    fun stopScan(): JSONObject {
        scanner?.stopScan(scanCallback)
        scanActive = false
        return capabilities()
    }

    fun scanResults(): String = JSONArray(results.values.sortedBy { it.optString("id") }).toString()

    @SuppressLint("MissingPermission")
    fun connect(address: String): JSONObject {
        stopScan()
        gatt?.close()
        val device = adapter?.getRemoteDevice(address)
            ?: return capabilities().put("lastError", "Bluetooth device not found: $address")
        connectionState = "connecting"
        lastError = null
        gatt = device.connectGatt(null, false, object : BluetoothGattCallback() {
            override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                if (newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) {
                    connectionState = "connected"
                    g.discoverServices()
                } else {
                    connectionState = "disconnected"
                    lastError = "GATT connection failed: status=$status state=$newState"
                    g.close()
                }
            }

            override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    lastError = "GATT service discovery failed: $status"
                    return
                }
                val audio = g.getService(UUID.fromString(OMI_SERVICE_UUID))
                    ?.getCharacteristic(UUID.fromString(OMI_AUDIO_UUID))
                if (audio == null) {
                    lastError = "Omi audio characteristic not found"
                    return
                }
                audioNotifications = g.setCharacteristicNotification(audio, true)
                val descriptor = audio.descriptors.firstOrNull()
                if (descriptor != null) {
                    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    g.writeDescriptor(descriptor)
                }
            }

            override fun onCharacteristicChanged(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
                if (characteristic.uuid == UUID.fromString(OMI_AUDIO_UUID)) {
                    lastPacketBytes = characteristic.value?.size ?: 0
                }
            }
        })
        return capabilities().put("device", address)
    }

    @SuppressLint("MissingPermission")
    fun disconnect(): JSONObject {
        gatt?.disconnect()
        gatt?.close()
        gatt = null
        connectionState = "disconnected"
        return capabilities()
    }
}

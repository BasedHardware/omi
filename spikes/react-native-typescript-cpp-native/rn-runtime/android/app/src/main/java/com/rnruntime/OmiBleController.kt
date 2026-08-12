package com.rnruntime

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.ParcelUuid
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.WritableArray
import com.facebook.react.bridge.WritableMap
import java.util.concurrent.ConcurrentHashMap

private const val OMI_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"

private data class OmiDevice(val id: String, val name: String, val rssi: Int)

class OmiBleController(private val context: Context) {
  private val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
  private val scanner get() = adapter?.bluetoothLeScanner
  private val results = ConcurrentHashMap<String, OmiDevice>()
  private var connectedDeviceId: String? = null
  private var gatt: BluetoothGatt? = null
  private var connectionState = "disconnected"
  private var scanActive = false
  private var lastEvent = "Bluetooth adapter not checked"

  private val scanCallback = object : ScanCallback() {
    override fun onScanResult(callbackType: Int, result: ScanResult) {
      val device = result.device
      results[device.address] = OmiDevice(
        id = device.address,
        name = result.scanRecord?.deviceName ?: device.name ?: "Omi",
        rssi = result.rssi,
      )
      lastEvent = "Found ${results.size} Omi device${if (results.size == 1) "" else "s"}"
    }

    override fun onScanFailed(errorCode: Int) {
      scanActive = false
      lastEvent = "BLE scan failed: $errorCode"
    }
  }

  fun bluetoothState(): String = when (adapter?.state) {
    BluetoothAdapter.STATE_ON -> "poweredOn"
    BluetoothAdapter.STATE_OFF -> "poweredOff"
    else -> "unknown"
  }

  fun snapshot(): WritableMap = Arguments.createMap().apply {
    putString("bluetooth", bluetoothState())
    putArray("devices", devices())
    putString("capture", "idle")
    putString("captureMode", "stream")
    putString("microphone", permissionState(Manifest.permission.RECORD_AUDIO))
    putString("notifications", notificationPermissionState())
    putString("background", "inactive")
    putString("audioRoute", "phone-mic")
    putString("lastEvent", lastEvent)
  }

  fun permissionSnapshot(): WritableMap = Arguments.createMap().apply {
    putString("microphone", permissionState(Manifest.permission.RECORD_AUDIO))
    putString("notifications", notificationPermissionState())
  }

  fun requestedPermissions(): Array<String> = buildList {
    if (!granted(Manifest.permission.RECORD_AUDIO)) add(Manifest.permission.RECORD_AUDIO)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
      if (!granted(Manifest.permission.BLUETOOTH_SCAN)) add(Manifest.permission.BLUETOOTH_SCAN)
      if (!granted(Manifest.permission.BLUETOOTH_CONNECT)) add(Manifest.permission.BLUETOOTH_CONNECT)
    }
    if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.R && !granted(Manifest.permission.ACCESS_FINE_LOCATION)) {
      add(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU && !granted(Manifest.permission.POST_NOTIFICATIONS)) {
      add(Manifest.permission.POST_NOTIFICATIONS)
    }
  }.toTypedArray()

  @SuppressLint("MissingPermission")
  fun startScan(serviceUuids: List<String>) {
    if (!canScan()) return
    val bleScanner = scanner ?: run {
      lastEvent = "Bluetooth LE scanner is unavailable"
      return
    }
    results.clear()
    val filters = serviceUuids.ifEmpty { listOf(OMI_SERVICE_UUID) }.map {
      ScanFilter.Builder().setServiceUuid(ParcelUuid.fromString(it)).build()
    }
    bleScanner.startScan(filters, ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
    scanActive = true
    lastEvent = "Scanning for Omi devices"
  }

  @SuppressLint("MissingPermission")
  fun stopScan() {
    if (scanActive) scanner?.stopScan(scanCallback)
    scanActive = false
    lastEvent = "Omi scan stopped"
  }

  @SuppressLint("MissingPermission")
  fun connect(id: String) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !granted(Manifest.permission.BLUETOOTH_CONNECT)) {
      lastEvent = "Bluetooth connection permission is required"
      return
    }
    val device = adapter?.getRemoteDevice(id)
    if (device == null) {
      lastEvent = "Omi device is unavailable"
      return
    }
    stopScan()
    gatt?.close()
    connectionState = "connecting"
    connectedDeviceId = id
    gatt = device.connectGatt(context, false, object : android.bluetooth.BluetoothGattCallback() {
      override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
        connectionState = if (status == android.bluetooth.BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) "connected" else "disconnected"
        lastEvent = if (connectionState == "connected") "Connected to Omi" else "Omi connection failed: $status"
        if (connectionState == "disconnected") {
          gatt.close()
          if (this@OmiBleController.gatt == gatt) this@OmiBleController.gatt = null
        }
      }
    })
  }

  fun disconnect(id: String) {
    if (connectedDeviceId == id) {
      gatt?.disconnect()
      lastEvent = "Disconnecting from Omi"
    }
  }

  fun devices(): WritableArray = Arguments.createArray().apply {
    results.values.sortedBy { it.id }.forEach { device ->
      pushMap(Arguments.createMap().apply {
        putString("id", device.id)
        putString("name", device.name)
        putInt("rssi", device.rssi)
        putBoolean("connected", connectionState == "connected" && connectedDeviceId == device.id)
      })
    }
  }

  private fun canScan(): Boolean {
    if (bluetoothState() != "poweredOn") {
      lastEvent = "Bluetooth is not powered on"
      return false
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !granted(Manifest.permission.BLUETOOTH_SCAN)) {
      lastEvent = "Bluetooth permission is required"
      return false
    }
    if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.R && !granted(Manifest.permission.ACCESS_FINE_LOCATION)) {
      lastEvent = "Location permission is required for Bluetooth scanning"
      return false
    }
    return true
  }

  private fun notificationPermissionState(): String = if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) "granted" else permissionState(Manifest.permission.POST_NOTIFICATIONS)

  private fun permissionState(permission: String): String = if (granted(permission)) "granted" else "denied"

  private fun granted(permission: String) = context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
}

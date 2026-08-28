package com.rnruntime

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.util.Base64
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.WritableArray
import com.facebook.react.bridge.WritableMap
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

private const val OMI_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
private const val OMI_AUDIO_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
private const val OMI_CODEC_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"
private const val BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
private const val BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
private val CLIENT_CONFIG_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

private data class OmiDevice(val id: String, val name: String, val rssi: Int, val battery: Int? = null)

class OmiBleController(
  private val context: Context,
  private val emit: (String, WritableMap) -> Unit,
) {
  private val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
  private val scanner get() = adapter?.bluetoothLeScanner
  private val handler = Handler(Looper.getMainLooper())
  private val results = ConcurrentHashMap<String, OmiDevice>()
  private var connectedDeviceId: String? = null
  private var gatt: BluetoothGatt? = null
  private var connectionState = "disconnected"
  private var scanActive = false
  private var lastEvent = "Bluetooth adapter not checked"
  private var audioNotifying = false
  private var codec: Int? = null
  private var scanGeneration = 0
  private var pendingScan: ((WritableArray) -> Unit)? = null
  private var pendingConnect: ((Boolean, String) -> Unit)? = null

  private val scanCallback = object : ScanCallback() {
    override fun onScanResult(callbackType: Int, result: ScanResult) {
      val device = result.device
      val discovered = OmiDevice(
        id = device.address,
        name = result.scanRecord?.deviceName ?: device.name ?: "Omi",
        rssi = result.rssi,
        battery = results[device.address]?.battery,
      )
      results[device.address] = discovered
      lastEvent = "Found ${results.size} Omi device${if (results.size == 1) "" else "s"}"
      emit("discovery", Arguments.createMap().apply {
        putMap("device", deviceMap(discovered))
      })
    }

    override fun onScanFailed(errorCode: Int) {
      scanActive = false
      lastEvent = "BLE scan failed: $errorCode"
      finishScan()
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
    if (connectionState == "connected" && connectedDeviceId != null) {
      putString("connectedDeviceId", connectedDeviceId)
    } else {
      putNull("connectedDeviceId")
    }
    putString("phase", connectionState)
    putString("capture", if (audioNotifying) "recording" else "idle")
    putString("captureMode", "stream")
    putString("microphone", permissionState(Manifest.permission.RECORD_AUDIO))
    putString("notifications", notificationPermissionState())
    putString("background", "inactive")
    putString("audioRoute", "phone-mic")
    putString("lastEvent", lastEvent)
    codec?.let { putInt("codec", it) }
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
  fun startScan(timeoutSeconds: Int?, serviceUuids: List<String>, onDone: (WritableArray) -> Unit) {
    pendingScan?.invoke(devices())
    pendingScan = onDone
    if (!canScan()) {
      finishScan()
      return
    }
    val bleScanner = scanner ?: run {
      lastEvent = "Bluetooth LE scanner is unavailable"
      finishScan()
      return
    }
    results.clear()
    val filters = serviceUuids.ifEmpty { listOf(OMI_SERVICE_UUID) }.map {
      ScanFilter.Builder().setServiceUuid(ParcelUuid.fromString(it)).build()
    }
    bleScanner.startScan(filters, ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
    scanActive = true
    lastEvent = "Scanning for Omi devices"
    val generation = ++scanGeneration
    val timeout = (timeoutSeconds ?: 8).coerceAtLeast(0)
    handler.postDelayed({
      if (generation == scanGeneration) {
        stopScanInternal()
        finishScan()
      }
    }, timeout * 1000L)
  }

  @SuppressLint("MissingPermission")
  fun stopScan() {
    stopScanInternal()
    lastEvent = "Omi scan stopped"
    finishScan()
  }

  @SuppressLint("MissingPermission")
  fun connect(id: String, onDone: (Boolean, String) -> Unit) {
    pendingConnect?.invoke(false, "Omi connection was replaced")
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !granted(Manifest.permission.BLUETOOTH_CONNECT)) {
      lastEvent = "Bluetooth connection permission is required"
      onDone(false, lastEvent)
      return
    }
    val device = runCatching { adapter?.getRemoteDevice(id) }.getOrNull()
    if (device == null) {
      lastEvent = "Omi device is unavailable"
      onDone(false, lastEvent)
      return
    }
    stopScanInternal()
    gatt?.close()
    audioNotifying = false
    codec = null
    connectionState = "connecting"
    connectedDeviceId = id
    pendingConnect = onDone
    emitSnapshot()
    gatt = device.connectGatt(context, false, object : android.bluetooth.BluetoothGattCallback() {
      override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
        val connected = status == android.bluetooth.BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED
        connectionState = if (connected) "connected" else "disconnected"
        lastEvent = if (connected) "Connected to Omi" else "Omi connection failed: $status"
        if (connected) {
          gatt.discoverServices()
          finishConnect(true, lastEvent)
        } else {
          audioNotifying = false
          gatt.close()
          if (this@OmiBleController.gatt == gatt) this@OmiBleController.gatt = null
          finishConnect(false, lastEvent)
        }
        emitSnapshot()
      }

      override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
        if (status != android.bluetooth.BluetoothGatt.GATT_SUCCESS) return
        val audio = gatt.getService(UUID.fromString(OMI_SERVICE_UUID))?.getCharacteristic(UUID.fromString(OMI_AUDIO_UUID))
        val codecChar = gatt.getService(UUID.fromString(OMI_SERVICE_UUID))?.getCharacteristic(UUID.fromString(OMI_CODEC_UUID))
        val battery = gatt.getService(UUID.fromString(BATTERY_SERVICE_UUID))?.getCharacteristic(UUID.fromString(BATTERY_LEVEL_UUID))
        if (codecChar != null) gatt.readCharacteristic(codecChar)
        if (battery != null) gatt.readCharacteristic(battery)
        if (audio != null) enableNotify(gatt, audio)
      }

      override fun onCharacteristicRead(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        status: Int,
      ) {
        if (status != android.bluetooth.BluetoothGatt.GATT_SUCCESS) return
        handleValue(characteristic)
      }

      override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
        handleValue(characteristic)
      }

      override fun onDescriptorWrite(
        gatt: BluetoothGatt,
        descriptor: BluetoothGattDescriptor,
        status: Int,
      ) {
        if (status == android.bluetooth.BluetoothGatt.GATT_SUCCESS &&
          descriptor.characteristic.uuid == UUID.fromString(OMI_AUDIO_UUID)
        ) {
          audioNotifying = true
          lastEvent = "Omi audio notify is live"
          emitSnapshot()
        }
      }
    })
  }

  @SuppressLint("MissingPermission")
  fun disconnect(id: String) {
    if (connectedDeviceId == id) {
      gatt?.disconnect()
      lastEvent = "Disconnecting from Omi"
    }
  }

  fun devices(): WritableArray = Arguments.createArray().apply {
    results.values.sortedBy { it.id }.forEach { device ->
      pushMap(deviceMap(device))
    }
  }

  @SuppressLint("MissingPermission")
  private fun enableNotify(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
    gatt.setCharacteristicNotification(characteristic, true)
    val descriptor = characteristic.getDescriptor(CLIENT_CONFIG_UUID) ?: return
    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
    gatt.writeDescriptor(descriptor)
  }

  private fun handleValue(characteristic: BluetoothGattCharacteristic) {
    val value = characteristic.value ?: return
    val id = connectedDeviceId ?: return
    when (characteristic.uuid) {
      UUID.fromString(OMI_CODEC_UUID) -> if (value.isNotEmpty()) {
        codec = value[0].toInt() and 0xff
        emitSnapshot()
      }
      UUID.fromString(BATTERY_LEVEL_UUID) -> if (value.isNotEmpty()) {
        val level = value[0].toInt() and 0xff
        results[id]?.let { results[id] = it.copy(battery = level) }
        emit("battery", Arguments.createMap().apply {
          putString("deviceId", id)
          putInt("battery", level)
        })
        emitSnapshot()
      }
      UUID.fromString(OMI_AUDIO_UUID) -> codec?.let { codecId ->
        emit("audio", Arguments.createMap().apply {
          putString("deviceId", id)
          putInt("codec", codecId)
          putString("payloadBase64", Base64.encodeToString(value, Base64.NO_WRAP))
        })
      }
    }
  }

  private fun emitSnapshot() {
    emit("snapshot", Arguments.createMap().apply {
      putMap("snapshot", snapshot())
    })
  }

  @SuppressLint("MissingPermission")
  private fun stopScanInternal() {
    if (scanActive) scanner?.stopScan(scanCallback)
    scanActive = false
    scanGeneration += 1
  }

  private fun finishScan() {
    val done = pendingScan
    pendingScan = null
    done?.invoke(devices())
  }

  private fun finishConnect(ok: Boolean, message: String) {
    val done = pendingConnect
    pendingConnect = null
    done?.invoke(ok, message)
  }

  private fun deviceMap(device: OmiDevice): WritableMap = Arguments.createMap().apply {
    putString("id", device.id)
    putString("name", device.name)
    putInt("rssi", device.rssi)
    putBoolean("connected", connectionState == "connected" && connectedDeviceId == device.id)
    device.battery?.let { putInt("battery", it) }
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

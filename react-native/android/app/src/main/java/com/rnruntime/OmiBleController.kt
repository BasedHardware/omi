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
import android.content.BroadcastReceiver
import android.content.Intent
import android.content.IntentFilter
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
import java.util.ArrayDeque
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

private const val OMI_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
private const val OMI_AUDIO_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
private const val OMI_CODEC_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"
private const val BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
private const val BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
private val HAPTIC_SERVICE_UUID = UUID.fromString("cab1ab95-2ea5-4f4d-bb56-874b72cfc984")
private val HAPTIC_UUID = UUID.fromString("cab1ab96-2ea5-4f4d-bb56-874b72cfc984")
private val FEATURES_SERVICE_UUID = UUID.fromString("19b10020-e8f2-537e-4f6c-d104768a1214")
private val FEATURES_UUID = UUID.fromString("19b10021-e8f2-537e-4f6c-d104768a1214")
private val SETTINGS_SERVICE_UUID = UUID.fromString("19b10010-e8f2-537e-4f6c-d104768a1214")
private val LED_UUID = UUID.fromString("19b10011-e8f2-537e-4f6c-d104768a1214")
private val MIC_GAIN_UUID = UUID.fromString("19b10012-e8f2-537e-4f6c-d104768a1214")
private val CHARGING_UUID = UUID.fromString("19b10013-e8f2-537e-4f6c-d104768a1214")
private val CLIENT_CONFIG_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

private data class OmiDevice(val id: String, val name: String, val rssi: Int, val battery: Int? = null, val information: Map<String, String> = emptyMap(), val features: Long? = null, val ledBrightness: Int? = null, val microphoneGain: Int? = null, val charging: Boolean? = null)

private sealed class GattOp {
  data class Write(val characteristic: BluetoothGattCharacteristic, val value: Int) : GattOp()
  data class Read(val characteristic: BluetoothGattCharacteristic) : GattOp()
  data class EnableNotify(val characteristic: BluetoothGattCharacteristic) : GattOp()
}

class OmiBleController(
  private val context: Context,
  private val emit: (String, WritableMap) -> Unit,
) {
  private val adapter = context.getSystemService(BluetoothManager::class.java)?.adapter
  private val scanner get() = adapter?.bluetoothLeScanner
  private val handler = Handler(Looper.getMainLooper())
  private val results = ConcurrentHashMap<String, OmiDevice>()
  private var wearableTicket = 0L
  private var connectedDeviceId: String? = null
  private var gatt: BluetoothGatt? = null
  private var connectionState = "disconnected"
  private var scanActive = false
  private var lastEvent = "Bluetooth adapter not checked"
  private val reconnect = OmiBleLease.Reconnect()
  private var reconnectDeviceId: String? = null
  private var audioNotifying = false
  private var codec: Int? = null
  private var scanGeneration = 0
  private var pendingScan: ((WritableArray) -> Unit)? = null
  private var pendingConnect: ((Boolean, String) -> Unit)? = null
  private val gattQueue = ArrayDeque<GattOp>()
  private var gattBusy = false
  private val lease = OmiBleLease()
  private var currentGeneration = 0L
  private val findPattern = OmiDeviceControls.FindPattern()
  private var findTicket = 0L
  private var pendingSetting: String? = null
  private var pendingSettingValue: Int? = null
  private var settingWritten = false
  private var settingDone: ((Int?, String?) -> Unit)? = null

  private val radioReceiver = object : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
      if (intent.action != BluetoothAdapter.ACTION_STATE_CHANGED) return
      synchronized(this@OmiBleController) {
        if (intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR) != BluetoothAdapter.STATE_ON) {
          cancelReconnect()
          runCatching { stopScanInternal() }
          retireConnection("Bluetooth is unavailable")
          finishScan()
        } else {
          lastEvent = "Bluetooth is powered on"
          emitSnapshot()
        }
      }
    }
  }

  init {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
      context.registerReceiver(radioReceiver, IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED), Context.RECEIVER_EXPORTED)
    } else {
      context.registerReceiver(radioReceiver, IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED))
    }
  }

  @Synchronized
  fun close() {
    cancelReconnect()
    runCatching { context.unregisterReceiver(radioReceiver) }
    runCatching { stopScanInternal() }
    retireConnection("Omi Bluetooth session closed")
    finishScan()
  }

  private val scanCallback = object : ScanCallback() {
    override fun onScanResult(callbackType: Int, result: ScanResult) {
      synchronized(this@OmiBleController) {
        if (!scanActive) return
        val device = result.device
        val discovered = OmiDevice(
          id = device.address,
          name = result.scanRecord?.deviceName ?: device.name ?: "Omi",
          rssi = result.rssi,
          battery = results[device.address]?.battery,
          information = results[device.address]?.information ?: emptyMap(),
          features = results[device.address]?.features,
          ledBrightness = results[device.address]?.ledBrightness,
          microphoneGain = results[device.address]?.microphoneGain,
          charging = results[device.address]?.charging,
        )
        results[device.address] = discovered
        lastEvent = "Found ${results.size} Omi device${if (results.size == 1) "" else "s"}"
        emit("discovery", Arguments.createMap().apply {
          putMap("device", deviceMap(discovered))
        })
      }
    }

    override fun onScanFailed(errorCode: Int) {
      synchronized(this@OmiBleController) {
        if (!scanActive) return
        scanActive = false
        lastEvent = "BLE scan failed: $errorCode"
        finishScan()
      }
    }
  }

  fun bluetoothState(): String {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !granted(Manifest.permission.BLUETOOTH_CONNECT)) {
      return "unauthorized"
    }
    return when (adapter?.state) {
      BluetoothAdapter.STATE_ON -> "poweredOn"
      BluetoothAdapter.STATE_OFF -> "poweredOff"
      else -> "unknown"
    }
  }

  @Synchronized
  fun snapshot(): WritableMap = Arguments.createMap().apply {
    putString("bluetooth", bluetoothState())
    putArray("devices", devices())
    if (connectionState == "connected" && connectedDeviceId != null) {
      putString("connectedDeviceId", connectedDeviceId)
    } else {
      putNull("connectedDeviceId")
    }
    putString("phase", connectionState)
    putString("capture", if (OmiBleLease.recordingReady(connectionState == "connected", audioNotifying, codec != null)) "recording" else "idle")
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
  @Synchronized
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
    val keepId = connectedDeviceId
    val kept = if (connectionState != "disconnected" && keepId != null) results[keepId] else null
    results.clear()
    if (kept != null) {
      results[kept.id] = kept
    }
    val filters = serviceUuids.ifEmpty { listOf(OMI_SERVICE_UUID) }.map {
      ScanFilter.Builder().setServiceUuid(ParcelUuid.fromString(it)).build()
    }
    bleScanner.startScan(filters, ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
    scanActive = true
    lastEvent = "Scanning for Omi devices"
    val generation = ++scanGeneration
    val timeout = (timeoutSeconds ?: 8).coerceAtLeast(0)
    handler.postDelayed({
      synchronized(this) {
        if (generation == scanGeneration) {
          stopScanInternal()
          lastEvent = if (results.isEmpty()) "No Omi devices found" else "Found ${results.size} Omi device${if (results.size == 1) "" else "s"}"
          finishScan()
        }
      }
    }, timeout * 1000L)
  }

  @SuppressLint("MissingPermission")
  @Synchronized
  fun stopScan() {
    stopScanInternal()
    lastEvent = "Omi scan stopped"
    finishScan()
  }

  @SuppressLint("MissingPermission")
  @Synchronized
  fun connect(id: String, onDone: (Boolean, String) -> Unit) {
    cancelReconnect()
    if (gatt != null || pendingConnect != null || wearableTicket != 0L) retireConnection("Omi connection was replaced")
    wearableTicket = try {
      OmiWearableService.start(context) { ticket ->
        handler.post { synchronized(this) {
          if (wearableTicket == ticket) {
            cancelReconnect()
            retireConnection("Omi device connection was stopped")
          }
        } }
      }
    } catch (_: RuntimeException) {
      onDone(false, "Open Omi and allow Bluetooth to keep the device connected")
      return
    }
    connectAttempt(id, onDone)
  }

  @SuppressLint("MissingPermission")
  private fun connectAttempt(id: String, onDone: (Boolean, String) -> Unit) {
    if (gatt != null || pendingConnect != null) retireConnection("Omi connection was replaced")
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !granted(Manifest.permission.BLUETOOTH_CONNECT)) {
      cancelReconnect()
      retireConnection("Bluetooth connection permission is required")
      onDone(false, lastEvent)
      return
    }
    val device = runCatching { adapter?.getRemoteDevice(id) }.getOrNull()
    if (device == null) {
      cancelReconnect()
      retireConnection("Omi device is unavailable")
      onDone(false, lastEvent)
      return
    }
    stopScanInternal()
    gatt?.close()
    results[id]?.let { results[id] = it.copy(information = emptyMap(), features = null, ledBrightness = null, microphoneGain = null, charging = null) }
    clearGattQueue()
    audioNotifying = false
    codec = null
    connectionState = "connecting"
    connectedDeviceId = id
    pendingConnect = onDone
    val generation = lease.begin()
    currentGeneration = generation
    handler.postDelayed({
      synchronized(this) { if (lease.accepts(generation) && pendingConnect != null) retireConnection("Omi connection setup timed out") }
    }, 20000)
    emitSnapshot()
    gatt = runCatching { device.connectGatt(context, false, object : android.bluetooth.BluetoothGattCallback() {
      override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
        synchronized(this@OmiBleController) {
          if (!lease.accepts(generation)) return
          val connected = status == android.bluetooth.BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED
          connectionState = if (connected) "connected" else "disconnected"
          lastEvent = if (connected) "Connected to Omi" else "Omi connection failed: $status"
          if (connected) {
            val started = runCatching { gatt.discoverServices() }.getOrElse { error ->
              if (error is SecurityException) cancelReconnect()
              retireConnection("Omi service discovery failed")
              return
            }
            if (!started) retireConnection("Omi service discovery failed")
          } else {
            retireConnection(lastEvent)
          }
          emitSnapshot()
        }
      }

      override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
        synchronized(this@OmiBleController) {
          if (!lease.accepts(generation)) return
          if (status != android.bluetooth.BluetoothGatt.GATT_SUCCESS) {
            retireConnection("Omi service discovery failed: $status")
            return
          }
          val audio = gatt.getService(UUID.fromString(OMI_SERVICE_UUID))?.getCharacteristic(UUID.fromString(OMI_AUDIO_UUID))
          val codecChar = gatt.getService(UUID.fromString(OMI_SERVICE_UUID))?.getCharacteristic(UUID.fromString(OMI_CODEC_UUID))
          val battery = gatt.getService(UUID.fromString(BATTERY_SERVICE_UUID))?.getCharacteristic(UUID.fromString(BATTERY_LEVEL_UUID))
          if (audio == null || codecChar == null) {
            retireConnection("Omi audio service is incomplete")
            return
          }
          enqueueGatt(gatt, GattOp.Read(codecChar))
          if (battery != null) enqueueGatt(gatt, GattOp.Read(battery))
          if (audio != null) enqueueGatt(gatt, GattOp.EnableNotify(audio))
          gatt.getService(FEATURES_SERVICE_UUID)?.getCharacteristic(FEATURES_UUID)?.let { feature ->
            if (feature.properties and BluetoothGattCharacteristic.PROPERTY_READ != 0) enqueueGatt(gatt, GattOp.Read(feature))
          }
          val information = gatt.getService(UUID.fromString("0000180a-0000-1000-8000-00805f9b34fb"))
          OmiDeviceInformation.fields.keys.forEach { uuid ->
            information?.getCharacteristic(uuid)?.let { characteristic ->
              if (characteristic.properties and BluetoothGattCharacteristic.PROPERTY_READ != 0) enqueueGatt(gatt, GattOp.Read(characteristic))
            }
          }
        }
      }

      override fun onCharacteristicRead(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        value: ByteArray,
        status: Int,
      ) {
        synchronized(this@OmiBleController) {
          if (!lease.accepts(generation)) return
          if (characteristic.uuid == UUID.fromString(OMI_CODEC_UUID) && status != android.bluetooth.BluetoothGatt.GATT_SUCCESS) {
            retireConnection("Omi codec read failed: $status")
            return
          }
          if (status != BluetoothGatt.GATT_SUCCESS && settingWritten &&
              characteristic.uuid == settingUuid(pendingSetting)) finishSetting(null, "Device setting read-back failed")
          if (status == android.bluetooth.BluetoothGatt.GATT_SUCCESS) {
            handleValue(characteristic, value)
          }
          finishGattOp(gatt)
        }
      }

      @Deprecated("Deprecated in API 33")
      override fun onCharacteristicRead(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        status: Int,
      ) {
        synchronized(this@OmiBleController) {
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return
          }
          if (!lease.accepts(generation)) return
          if (characteristic.uuid == UUID.fromString(OMI_CODEC_UUID) && status != android.bluetooth.BluetoothGatt.GATT_SUCCESS) {
            retireConnection("Omi codec read failed: $status")
            return
          }
          if (status != BluetoothGatt.GATT_SUCCESS && settingWritten &&
              characteristic.uuid == settingUuid(pendingSetting)) finishSetting(null, "Device setting read-back failed")
          if (status == android.bluetooth.BluetoothGatt.GATT_SUCCESS) {
            handleValue(characteristic)
          }
          finishGattOp(gatt)
        }
      }

      override fun onCharacteristicChanged(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        value: ByteArray,
      ) {
        synchronized(this@OmiBleController) {
          if (!lease.accepts(generation)) return
          handleValue(characteristic, value)
        }
      }

      @Deprecated("Deprecated in API 33")
      override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
        synchronized(this@OmiBleController) {
          if (!lease.accepts(generation)) return
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return
          }
          handleValue(characteristic)
        }
      }

      override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
        synchronized(this@OmiBleController) {
          if (!lease.acceptsGatt(generation, this@OmiBleController.gatt, gatt)) return
          if (pendingSetting == "findDevice" && characteristic.uuid == HAPTIC_UUID) {
            if (status != BluetoothGatt.GATT_SUCCESS) finishSetting(null, "Find device command failed")
            else if (findPattern.acknowledge(findTicket)) {
              if (findPattern.complete()) finishSetting(3, null)
              else {
                val ticket = findTicket
                handler.postDelayed({ synchronized(this@OmiBleController) {
                  if (lease.acceptsGatt(generation, this@OmiBleController.gatt, gatt) && findPattern.send(ticket))
                    enqueueGatt(gatt, GattOp.Write(characteristic, OmiDeviceControls.FindPattern.LEVEL))
                } }, OmiDeviceControls.FindPattern.DELAY_MS.toLong())
              }
            }
            finishGattOp(gatt)
            return
          }
          if (characteristic.uuid != settingUuid(pendingSetting)) return
          if (status != BluetoothGatt.GATT_SUCCESS) {
            finishSetting(null, "Device setting write failed")
          } else if (settingDone != null) {
            settingWritten = true
            gattQueue.addFirst(GattOp.Read(characteristic))
          }
          finishGattOp(gatt)
        }
      }

      override fun onDescriptorWrite(
        gatt: BluetoothGatt,
        descriptor: BluetoothGattDescriptor,
        status: Int,
      ) {
        synchronized(this@OmiBleController) {
          if (!lease.accepts(generation)) return
          if (status != android.bluetooth.BluetoothGatt.GATT_SUCCESS) {
            if (descriptor.characteristic.uuid == UUID.fromString(OMI_AUDIO_UUID)) retireConnection("Omi notification subscription failed: $status")
            else finishGattOp(gatt)
            return
          }
          if (status == android.bluetooth.BluetoothGatt.GATT_SUCCESS &&
            descriptor.characteristic.uuid == UUID.fromString(OMI_AUDIO_UUID)
          ) {
            audioNotifying = true
            lastEvent = "Omi audio notify is live"
            reconnectDeviceId = connectedDeviceId
            reconnect.ready()
            OmiWearableService.update(wearableTicket, "Omi connected · Wearable audio available")
            finishConnect(true, lastEvent)
            emitSnapshot()
          }
          finishGattOp(gatt)
        }
      }
    }) }.getOrElse { error ->
      if (error is SecurityException) cancelReconnect()
      retireConnection("Omi connection could not start")
      null
    }
  }

  @SuppressLint("MissingPermission")
  @Synchronized
  fun disconnect(id: String) {
    if (connectedDeviceId == id || reconnectDeviceId == id) {
      cancelReconnect()
      retireConnection("Disconnected from Omi")
    }
  }

  @Synchronized
  fun devices(): WritableArray = Arguments.createArray().apply {
    results.values.sortedBy { it.id }.forEach { device ->
      pushMap(deviceMap(device))
    }
  }

  private fun enqueueGatt(gatt: BluetoothGatt, op: GattOp) {
    if (!lease.acceptsGatt(currentGeneration, this.gatt, gatt)) return
    gattQueue.addLast(op)
    pumpGatt(gatt)
  }

  private fun clearGattQueue() {
    lease.operation()
    gattQueue.clear()
    gattBusy = false
  }

  @SuppressLint("MissingPermission")
  private fun pumpGatt(gatt: BluetoothGatt) {
    if (!lease.acceptsGatt(currentGeneration, this.gatt, gatt)) return
    if (gattBusy) return
    val op = gattQueue.pollFirst() ?: return
    gattBusy = true
    val generation = currentGeneration
    val ticket = lease.operation()
    handler.postDelayed({
      synchronized(this) { if (lease.operationPending(generation, ticket)) retireConnection("Omi Bluetooth operation timed out") }
    }, 8000)
    val started = runCatching { when (op) {
      is GattOp.Write -> {
        op.characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        op.characteristic.value = byteArrayOf(op.value.toByte())
        gatt.writeCharacteristic(op.characteristic)
      }
      is GattOp.Read -> gatt.readCharacteristic(op.characteristic)
      is GattOp.EnableNotify -> writeNotifyDescriptor(gatt, op.characteristic)
    } }.getOrElse { error ->
      if (error is SecurityException) cancelReconnect()
      retireConnection("Omi Bluetooth operation could not start")
      return
    }
    if (!started) {
      if (op is GattOp.EnableNotify && op.characteristic.uuid != UUID.fromString(OMI_AUDIO_UUID)) finishGattOp(gatt)
      else retireConnection("Omi Bluetooth operation failed to start")
    }
  }

  private fun finishGattOp(gatt: BluetoothGatt) {
    if (!lease.acceptsGatt(currentGeneration, this.gatt, gatt)) return
    lease.operation()
    gattBusy = false
    pumpGatt(gatt)
  }

  @SuppressLint("MissingPermission")
  private fun writeNotifyDescriptor(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic): Boolean {
    if (!gatt.setCharacteristicNotification(characteristic, true)) return false
    val descriptor = characteristic.getDescriptor(CLIENT_CONFIG_UUID) ?: return false
    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
    return gatt.writeDescriptor(descriptor)
  }

  private fun handleValue(characteristic: BluetoothGattCharacteristic) {
    val value = characteristic.value ?: return
    handleValue(characteristic, value)
  }

  private fun handleValue(characteristic: BluetoothGattCharacteristic, value: ByteArray) {
    val id = connectedDeviceId ?: return
    OmiDeviceInformation.decode(characteristic.uuid, value)?.let { (field, decoded) ->
      results[id]?.let { results[id] = it.copy(information = it.information + (field to decoded)) }
      emitSnapshot()
      return
    }
    when (characteristic.uuid) {
      FEATURES_UUID -> {
        val features = OmiDeviceControls.features(value) ?: return
        results[id]?.let { results[id] = it.copy(features = features) }
        val current = gatt ?: return
        listOf("ledBrightness", "microphoneGain").forEach { setting ->
          if (OmiDeviceControls.supports(features, setting)) {
            current.getService(SETTINGS_SERVICE_UUID)?.getCharacteristic(settingUuid(setting))?.let { settingChar ->
              if (settingChar.properties and BluetoothGattCharacteristic.PROPERTY_READ != 0) enqueueGatt(current, GattOp.Read(settingChar))
            }
          }
        }
        current.getService(SETTINGS_SERVICE_UUID)?.getCharacteristic(CHARGING_UUID)?.let { charging ->
          if (charging.properties and BluetoothGattCharacteristic.PROPERTY_READ != 0) enqueueGatt(current, GattOp.Read(charging))
          if (charging.properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY != 0) enqueueGatt(current, GattOp.EnableNotify(charging))
        }
        emitSnapshot()
      }
      LED_UUID, MIC_GAIN_UUID -> {
        val setting = if (characteristic.uuid == LED_UUID) "ledBrightness" else "microphoneGain"
        val device = results[id] ?: return
        if (!OmiDeviceControls.supports(device.features, setting)) return
        val decoded = OmiDeviceControls.value(setting, value)
        results[id] = if (setting == "ledBrightness") device.copy(ledBrightness = decoded) else device.copy(microphoneGain = decoded)
        if (settingWritten && pendingSetting == setting) {
          if (decoded == pendingSettingValue) finishSetting(decoded, null) else finishSetting(null, "Device did not confirm the requested setting")
        }
        emitSnapshot()
      }
      CHARGING_UUID -> {
        if (value.size != 1 || value[0].toInt() !in 0..1) return
        results[id]?.let { if (it.features != null) results[id] = it.copy(charging = value[0].toInt() == 1) }
        emitSnapshot()
      }
      UUID.fromString(OMI_CODEC_UUID) -> if (value.isNotEmpty()) {
        codec = value[0].toInt() and 0xff
        emitSnapshot()
      } else retireConnection("Omi codec response was empty")
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
        if (!OmiBleLease.recordingReady(connectionState == "connected", audioNotifying, true)) return
        emit("audio", Arguments.createMap().apply {
          putString("deviceId", id)
          putInt("codec", codecId)
          putString("payloadBase64", Base64.encodeToString(value, Base64.NO_WRAP))
        })
      }
    }
  }

  @SuppressLint("MissingPermission")
  @Synchronized
  private fun retireConnection(message: String) {
    lease.retire()
    finishSetting(null, message)
    val previous = gatt
    gatt = null
    clearGattQueue()
    audioNotifying = false
    codec = null
    connectedDeviceId = null
    connectionState = "disconnected"
    lastEvent = message
    runCatching { previous?.disconnect() }
    runCatching { previous?.close() }
    finishConnect(false, message)
    emitSnapshot()
    val target = reconnectDeviceId
    val delay = reconnect.nextDelayMillis()
    if (target != null && delay >= 0) {
      connectedDeviceId = target
      connectionState = "connecting"
      lastEvent = "Reconnecting to Omi (${reconnect.attempts()}/3)"
      OmiWearableService.update(wearableTicket, lastEvent)
      val token = reconnect.token()
      emitSnapshot()
      handler.postDelayed({
        synchronized(this) {
          if (reconnect.accepts(token) && reconnectDeviceId == target) {
            connectAttempt(target) { _, _ -> }
          }
        }
      }, delay)
    } else {
      OmiWearableService.stop(wearableTicket)
      wearableTicket = 0L
      reconnectDeviceId = null
      if (target != null) {
        lastEvent = "Omi reconnect failed. Connect your device to try again."
        emitSnapshot()
      }
    }
  }

  private fun cancelReconnect() {
    reconnect.cancel()
    reconnectDeviceId = null
  }

  private fun settingUuid(setting: String?): UUID? = when (setting) {
    "ledBrightness" -> LED_UUID
    "microphoneGain" -> MIC_GAIN_UUID
    else -> null
  }

  @Synchronized
  fun setDeviceSetting(id: String, setting: String, value: Double, done: (Int?, String?) -> Unit) {
    val device = results[id]
    val current = gatt
    val uuid = settingUuid(setting)
    val characteristic = if (uuid == null) null else current?.getService(SETTINGS_SERVICE_UUID)?.getCharacteristic(uuid)
    val observed = if (setting == "ledBrightness") device?.ledBrightness else device?.microphoneGain
    if (id != connectedDeviceId || connectionState != "connected" || current == null || device == null ||
        settingDone != null || observed == null || !OmiDeviceControls.validWrite(device.features, setting, value) || characteristic == null ||
        characteristic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE == 0 ||
        characteristic.properties and BluetoothGattCharacteristic.PROPERTY_READ == 0) {
      done(null, "Device setting is unavailable")
      return
    }
    pendingSetting = setting
    pendingSettingValue = value.toInt()
    settingWritten = false
    settingDone = done
    enqueueGatt(current, GattOp.Write(characteristic, value.toInt()))
  }

  @Synchronized
  fun findDevice(id: String, done: (Int?, String?) -> Unit) {
    val current = gatt
    val characteristic = current?.getService(HAPTIC_SERVICE_UUID)?.getCharacteristic(HAPTIC_UUID)
    if (id != connectedDeviceId || connectionState != "connected" || current == null ||
        settingDone != null || characteristic == null ||
        characteristic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE == 0) {
      done(null, "Find device is unavailable")
      return
    }
    pendingSetting = "findDevice"
    settingDone = done
    findTicket = findPattern.begin()
    if (findPattern.send(findTicket)) enqueueGatt(current, GattOp.Write(characteristic, OmiDeviceControls.FindPattern.LEVEL))
  }

  private fun finishSetting(value: Int?, error: String?) {
    findPattern.cancel()
    val done = settingDone
    settingDone = null
    pendingSetting = null
    pendingSettingValue = null
    settingWritten = false
    done?.invoke(value, error)
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
    val haptic = if (connectionState == "connected" && connectedDeviceId == device.id) gatt?.getService(HAPTIC_SERVICE_UUID)?.getCharacteristic(HAPTIC_UUID) else null
    putBoolean("findDeviceSupported", haptic != null && haptic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE != 0)
    device.battery?.let { putInt("battery", it) }
    device.features?.let { putDouble("features", it.toDouble()) }
    device.ledBrightness?.let { putInt("ledBrightness", it) }
    device.microphoneGain?.let { putInt("microphoneGain", it) }
    device.charging?.let { putBoolean("charging", it) }
    if (device.information.isNotEmpty()) putMap("information", Arguments.createMap().apply {
      device.information.forEach { (field, value) -> putString(field, value) }
    })
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

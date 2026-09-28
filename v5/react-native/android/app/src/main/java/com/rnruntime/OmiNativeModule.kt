package com.rnruntime

import android.app.Activity
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray
import com.facebook.react.bridge.WritableMap
import com.facebook.react.modules.core.DeviceEventManagerModule

class OmiNativeModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  private val ble = OmiBleController(context, ::emit)

  override fun invalidate() {
    ble.close()
    super.invalidate()
  }

  override fun getName() = "OmiNative"

  @ReactMethod
  fun addListener(eventName: String) {}

  @ReactMethod
  fun removeListeners(count: Int) {}

  private fun remembered(action: String, promise: Promise) {
    val snapshot = ble.snapshot()
    val id = snapshot.getString("connectedDeviceId")
    val connection = if (snapshot.hasKey("connectionId")) snapshot.getString("connectionId") else null
    if (action == "save" && (id == null || snapshot.getString("capture") != "recording")) {
      promise.reject("OMI_REMEMBERED_DEVICE", "Connect your Omi before remembering it")
      return
    }
    val devices = snapshot.getArray("devices")
    var name: String? = null
    if (devices != null) for (index in 0 until devices.size()) devices.getMap(index)?.let { if (it.getString("id") == id) name = it.getString("name") }
    val backend = context.getNativeModule(OmiBackendModule::class.java)
    if (backend == null) { promise.reject("OMI_REMEMBERED_DEVICE", "Remembered device storage is unavailable"); return }
    backend.rememberedDevice(action, id, name, {
      val now = ble.snapshot()
      action != "save" || (now.hasKey("connectionId") && now.getString("connectionId") == connection && now.getString("connectedDeviceId") == id && now.getString("capture") == "recording")
    }, promise)
  }

  @ReactMethod fun getRememberedDevice(promise: Promise) = remembered("get", promise)
  @ReactMethod fun rememberConnectedDevice(promise: Promise) = remembered("save", promise)
  @ReactMethod fun forgetRememberedDevice(promise: Promise) = remembered("forget", promise)

  @ReactMethod
  fun getSnapshot(promise: Promise) = promise.resolve(ble.snapshot())

  @ReactMethod
  fun getBluetoothState(promise: Promise) = promise.resolve(ble.bluetoothState())

  @ReactMethod
  fun requestPermissions(promise: Promise) {
    val activity: Activity = currentActivity ?: run {
      promise.reject("ACTIVITY_UNAVAILABLE", "A foreground activity is required to request permissions")
      return
    }
    val permissions = ble.requestedPermissions()
    if (permissions.isNotEmpty()) activity.requestPermissions(permissions, 4821)
    promise.resolve(ble.permissionSnapshot())
  }

  @ReactMethod
  fun startScan(timeoutSeconds: Int?, serviceUuids: ReadableArray?, promise: Promise) {
    val uuids = buildList { serviceUuids?.let { values -> for (index in 0 until values.size()) values.getString(index)?.let(::add) } }
    ble.startScan(timeoutSeconds, uuids, promise::resolve) { promise.reject("OMI_SCAN_FAILED", "Bluetooth scan failed") }
  }

  @ReactMethod
  fun stopScan(promise: Promise) {
    if (ble.stopScan()) promise.resolve(null)
    else promise.reject("OMI_SCAN_FAILED", "Bluetooth scan could not be stopped")
  }

  @ReactMethod
  fun connectDevice(id: String, promise: Promise) {
    if (context.lifecycleState != com.facebook.react.common.LifecycleState.RESUMED) {
      promise.reject("ACTIVITY_UNAVAILABLE", "Open Omi to connect your device")
      return
    }
    ble.connect(id) { ok, message ->
      if (ok) promise.resolve(null) else promise.reject("OMI_DEVICE_UNAVAILABLE", message)
    }
  }

  @ReactMethod
  fun disconnectDevice(id: String, promise: Promise) {
    ble.disconnect(id)
    promise.resolve(null)
  }

  @ReactMethod
  fun readStorageStatus(id: String, promise: Promise) {
    ble.readStorageStatus(id) { status, error ->
      if (status != null) promise.resolve(status) else promise.reject("OMI_STORAGE_STATUS_FAILED", error ?: "Storage status failed")
    }
  }

  @ReactMethod
  fun findDevice(id: String, promise: Promise) {
    ble.findDevice(id) { confirmed, error ->
      if (confirmed != null) promise.resolve(null) else promise.reject("OMI_FIND_DEVICE_FAILED", error ?: "Find device failed")
    }
  }

  @ReactMethod
  fun setDeviceSetting(id: String, setting: String, value: Double, promise: Promise) {
    ble.setDeviceSetting(id, setting, value) { confirmed, error ->
      if (confirmed != null) promise.resolve(confirmed) else promise.reject("OMI_DEVICE_SETTING_FAILED", error ?: "Device setting failed")
    }
  }

  @ReactMethod
  fun getCppCapabilities(promise: Promise) = promise.resolve(nativeCapabilities())

  @ReactMethod
  fun normalizePacket(raw: ReadableArray, promise: Promise) {
    val bytes = ByteArray(raw.size()) { raw.getInt(it).toByte() }
    val normalized = nativeNormalizePacket(bytes)
    if (normalized == null) promise.reject("INVALID_PACKET", "C++ boundary rejected the packet")
    else promise.resolve(Arguments.fromList(normalized.map { it.toInt() and 0xff }))
  }

  private fun emit(type: String, body: WritableMap) {
    body.putString("type", type)
    if (context.hasActiveReactInstance()) {
      context
        .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
        .emit("omiNativeEvent", body)
    }
  }

  private external fun nativeCapabilities(): String
  private external fun nativeNormalizePacket(raw: ByteArray): ByteArray?

  companion object {
    init { System.loadLibrary("omi_native") }
  }
}

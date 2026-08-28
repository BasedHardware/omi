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

  override fun getName() = "OmiNative"

  @ReactMethod
  fun addListener(eventName: String) {}

  @ReactMethod
  fun removeListeners(count: Int) {}

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
    ble.startScan(timeoutSeconds, uuids, promise::resolve)
  }

  @ReactMethod
  fun stopScan(promise: Promise) {
    ble.stopScan()
    promise.resolve(null)
  }

  @ReactMethod
  fun connectDevice(id: String, promise: Promise) {
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

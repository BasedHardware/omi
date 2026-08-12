package com.rnruntime

import android.app.Activity
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray

class OmiNativeModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  private val ble = OmiBleController(context)

  override fun getName() = "OmiNative"

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
    val uuids = buildList { serviceUuids?.let { values -> for (index in 0 until values.size()) add(values.getString(index)) } }
    ble.startScan(uuids)
    promise.resolve(ble.devices())
  }

  @ReactMethod
  fun stopScan(promise: Promise) {
    ble.stopScan()
    promise.resolve(null)
  }

  @ReactMethod
  fun connectDevice(id: String, promise: Promise) {
    ble.connect(id)
    promise.resolve(null)
  }

  @ReactMethod
  fun disconnectDevice(id: String, promise: Promise) {
    ble.disconnect(id)
    promise.resolve(null)
  }

  @ReactMethod fun readCharacteristic(deviceId: String, serviceUuid: String, characteristicUuid: String, promise: Promise) = unsupported(promise, "GATT read")
  @ReactMethod fun writeCharacteristic(deviceId: String, serviceUuid: String, characteristicUuid: String, data: ReadableArray, promise: Promise) = unsupported(promise, "GATT write")
  @ReactMethod fun subscribeCharacteristic(deviceId: String, serviceUuid: String, characteristicUuid: String, promise: Promise) = unsupported(promise, "GATT subscribe")
  @ReactMethod fun unsubscribeCharacteristic(deviceId: String, serviceUuid: String, characteristicUuid: String, promise: Promise) = unsupported(promise, "GATT unsubscribe")
  @ReactMethod fun startRssiStreaming(deviceId: String, promise: Promise) = unsupported(promise, "RSSI streaming")
  @ReactMethod fun stopRssiStreaming(deviceId: String, promise: Promise) = promise.resolve(null)
  @ReactMethod fun getDeviceDiagnostics(deviceId: String, promise: Promise) = unsupported(promise, "device diagnostics")
  @ReactMethod fun getBatteryHistory(deviceId: String, promise: Promise) = promise.resolve(Arguments.createArray())
  @ReactMethod fun startCapture(mode: String, promise: Promise) = unsupported(promise, "audio capture")
  @ReactMethod fun stopCapture(promise: Promise) = promise.resolve(null)
  @ReactMethod fun getAudioRoute(promise: Promise) = promise.resolve("phone-mic")
  @ReactMethod fun startPhoneCall(phoneNumber: String, promise: Promise) = unsupported(promise, "phone call")
  @ReactMethod fun endPhoneCall(promise: Promise) = promise.resolve(null)
  @ReactMethod fun setPhoneCallAudio(muted: Boolean, speakerOn: Boolean, promise: Promise) = unsupported(promise, "call audio")
  @ReactMethod fun setNotificationOnKillService(title: String, description: String, promise: Promise) = unsupported(promise, "kill-service notification")
  @ReactMethod fun getWifiNetwork(promise: Promise) = unsupported(promise, "Wi-Fi")
  @ReactMethod fun setBackgroundMode(active: Boolean, promise: Promise) = unsupported(promise, "background mode")
  @ReactMethod fun getWatchStatus(promise: Promise) = unsupported(promise, "watch status")
  @ReactMethod fun getCameraStatus(promise: Promise) = unsupported(promise, "camera status")
  @ReactMethod fun capturePhoto(promise: Promise) = unsupported(promise, "camera capture")

  @ReactMethod
  fun getCppCapabilities(promise: Promise) = promise.resolve(nativeCapabilities())

  @ReactMethod
  fun normalizePacket(raw: ReadableArray, promise: Promise) {
    val bytes = ByteArray(raw.size()) { raw.getInt(it).toByte() }
    val normalized = nativeNormalizePacket(bytes)
    if (normalized == null) promise.reject("INVALID_PACKET", "C++ boundary rejected the packet")
    else promise.resolve(Arguments.fromList(normalized.map { it.toInt() and 0xff }))
  }

  private fun unsupported(promise: Promise, capability: String) = promise.reject("NATIVE_ADAPTER_UNAVAILABLE", "$capability requires a platform adapter")

  private external fun nativeCapabilities(): String
  private external fun nativeNormalizePacket(raw: ByteArray): ByteArray?

  companion object {
    init { System.loadLibrary("omi_native") }
  }
}

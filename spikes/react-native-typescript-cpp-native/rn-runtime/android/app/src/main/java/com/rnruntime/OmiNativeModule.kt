package com.rnruntime

import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.bridge.ReadableArray
import com.facebook.react.bridge.WritableMap

class OmiNativeModule(context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  override fun getName() = "OmiNative"

  @ReactMethod
  fun getSnapshot(promise: Promise) {
    promise.resolve(snapshot("JNI C++ boundary loaded; platform capture adapters pending"))
  }

  @ReactMethod
  fun getBluetoothState(promise: Promise) = promise.resolve("poweredOn")

  @ReactMethod
  fun requestPermissions(promise: Promise) {
    val result = Arguments.createMap()
    result.putString("microphone", "denied")
    result.putString("notifications", "denied")
    promise.resolve(result)
  }

  @ReactMethod
  fun startScan(timeoutSeconds: Int?, serviceUuids: ReadableArray?, promise: Promise) {
    promise.resolve(Arguments.createArray())
  }

  @ReactMethod fun stopScan(promise: Promise) = promise.resolve(null)
  @ReactMethod fun connectDevice(id: String, promise: Promise) = unsupported(promise, "BLE connect")
  @ReactMethod fun disconnectDevice(id: String, promise: Promise) = unsupported(promise, "BLE disconnect")
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

  private fun snapshot(event: String): WritableMap {
    val value = Arguments.createMap()
    value.putString("bluetooth", "poweredOn")
    value.putArray("devices", Arguments.createArray())
    value.putString("capture", "idle")
    value.putString("captureMode", "stream")
    value.putString("microphone", "denied")
    value.putString("notifications", "denied")
    value.putString("background", "inactive")
    value.putString("audioRoute", "phone-mic")
    value.putString("lastEvent", event)
    return value
  }

  private fun unsupported(promise: Promise, capability: String) = promise.reject("NATIVE_ADAPTER_UNAVAILABLE", "$capability requires a platform adapter")

  private external fun nativeCapabilities(): String
  private external fun nativeNormalizePacket(raw: ByteArray): ByteArray?

  companion object {
    init { System.loadLibrary("omi_native") }
  }
}

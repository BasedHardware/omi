package com.lynxshell.modules

import android.content.Context
import android.util.Base64
import com.lynx.jsbridge.LynxMethod
import com.lynx.jsbridge.LynxModule
import org.json.JSONObject

/**
 * Minimal Lynx-to-native seam for the Omi spike.
 * The module loads the shared Omi C++ boundary through a small JNI adapter.
 */
class OmiNativeModule(context: Context) : LynxModule(context) {
    private val ble = OmiBleController(context)
    companion object {
        init {
            System.loadLibrary("omi_lynx_native")
        }
    }

    private external fun nativeCapabilities(): String
    private external fun nativeNormalizePacket(raw: ByteArray): String

    @LynxMethod
    fun getNativeCapabilities(): String = JSONObject(nativeCapabilities())
        .put("framework", "lynx")
        .put("platform", "android")
        .put("bridge", "lynx-native-module")
        .put("cppBoundary", "linked")
        .put("contract", "omi-relay-contract:v1")
        .toString()

    @LynxMethod
    fun normalizePacket(rawBase64: String): String {
        val raw = Base64.decode(rawBase64, Base64.DEFAULT)
        return nativeNormalizePacket(raw)
    }

    @LynxMethod
    fun getBluetoothState(): String = ble.capabilities().toString()

    @LynxMethod
    fun startOmiScan(): String = ble.startScan().toString()

    @LynxMethod
    fun stopOmiScan(): String = ble.stopScan().toString()

    @LynxMethod
    fun getOmiScanResults(): String = ble.scanResults()

    @LynxMethod
    fun connectOmi(address: String): String = ble.connect(address).toString()

    @LynxMethod
    fun disconnectOmi(): String = ble.disconnect().toString()
}

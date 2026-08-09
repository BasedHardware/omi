package com.lynxshell.modules

import android.content.Context
import com.lynx.jsbridge.LynxMethod
import com.lynx.jsbridge.LynxModule
import org.json.JSONObject

/**
 * Minimal Lynx-to-native seam for the Omi spike.
 * The module intentionally returns explicit capability state until the shared
 * C++ boundary is linked into the Android host.
 */
class OmiNativeModule(context: Context) : LynxModule(context) {
    @LynxMethod
    fun getNativeCapabilities(): String = JSONObject()
        .put("framework", "lynx")
        .put("platform", "android")
        .put("bridge", "lynx-native-module")
        .put("cppBoundary", "NATIVE_ADAPTER_UNAVAILABLE")
        .put("contract", "omi-relay-contract:v1")
        .toString()

    @LynxMethod
    fun normalizePacket(raw: String): String = JSONObject()
        .put("status", "NATIVE_ADAPTER_UNAVAILABLE")
        .put("reason", "shared C++ boundary not linked in this host yet")
        .put("rawLength", raw.length)
        .toString()
}

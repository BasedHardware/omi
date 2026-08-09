package com.lynxshell.modules

import android.content.Context
import com.lynx.jsbridge.LynxMethod
import com.lynx.jsbridge.LynxModule
import org.json.JSONObject

/**
 * Minimal Lynx-to-native seam for the Omi spike.
 * The module loads the shared Omi C++ boundary through a small JNI adapter.
 */
class OmiNativeModule(context: Context) : LynxModule(context) {
    companion object {
        init {
            System.loadLibrary("omi_lynx_native")
        }
    }

    private external fun nativeCapabilities(): String
    private external fun nativeNormalizePacket(raw: String): String

    @LynxMethod
    fun getNativeCapabilities(): String = JSONObject(nativeCapabilities())
        .put("framework", "lynx")
        .put("platform", "android")
        .put("bridge", "lynx-native-module")
        .put("cppBoundary", "linked")
        .put("contract", "omi-relay-contract:v1")
        .toString()

    @LynxMethod
    fun normalizePacket(raw: String): String = nativeNormalizePacket(raw)
}

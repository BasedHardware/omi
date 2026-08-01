package com.friend.ios.batch

import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

internal const val NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX = ".geolocation.json"
internal const val NATIVE_BATCH_GEOLOCATION_MAX_BYTES = 4096

/** Copy one validated, bounded private snapshot beside a native batch file. */
internal fun persistNativeBatchGeolocationSidecar(audioFile: File, rawGeolocation: String, tag: String) {
    if (rawGeolocation.isBlank() || rawGeolocation.toByteArray(Charsets.UTF_8).size > NATIVE_BATCH_GEOLOCATION_MAX_BYTES) {
        return
    }
    try {
        JSONObject(rawGeolocation)
        val sidecar = File(audioFile.path + NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX)
        val pending = File(sidecar.path + ".part")
        FileOutputStream(pending).use { output ->
            output.write(rawGeolocation.toByteArray(Charsets.UTF_8))
            output.fd.sync()
        }
        if (sidecar.exists()) sidecar.delete()
        if (!pending.renameTo(sidecar)) pending.delete()
    } catch (error: Exception) {
        // Location is optional: never interrupt or discard audio capture.
        runCatching { Log.w(tag, "failed to persist bounded recording location sidecar: ${error.javaClass.simpleName}") }
    }
}

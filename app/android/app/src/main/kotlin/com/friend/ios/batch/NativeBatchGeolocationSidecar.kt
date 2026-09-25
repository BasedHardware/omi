package com.friend.ios.batch

import android.util.Log
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream

internal const val NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX = ".geolocation.json"
internal const val NATIVE_BATCH_GEOLOCATION_MAX_BYTES = 4096
private val nativeBatchGeolocationSidecarLock = Any()

/** Copy one validated, bounded private snapshot beside a native batch file. */
internal fun persistNativeBatchGeolocationSidecar(audioFile: File, rawGeolocation: String, tag: String) {
    val sidecar = File(audioFile.path + NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX)
    val pending = File(sidecar.path + ".part")
    val geolocationBytes = rawGeolocation.toByteArray(Charsets.UTF_8)
    synchronized(nativeBatchGeolocationSidecarLock) {
        if (rawGeolocation.isBlank() ||
            geolocationBytes.size > NATIVE_BATCH_GEOLOCATION_MAX_BYTES
        ) {
            pending.delete()
            return
        }
        try {
            JSONObject(rawGeolocation)
            // A same-name part file can be reopened after a native restart. Its
            // location belongs to that recording, so never replace an existing
            // snapshot with the next session's config.
            if (sidecar.exists()) {
                pending.delete()
                return
            }
            FileOutputStream(pending).use { output ->
                output.write(geolocationBytes)
                output.fd.sync()
            }
            // Re-check after the durable pending write. The destination wins if
            // another opener published the recording while this one was writing.
            if (sidecar.exists() || !pending.renameTo(sidecar)) pending.delete()
        } catch (error: Exception) {
            pending.delete()
            // Location is optional: never interrupt or discard audio capture.
            runCatching {
                Log.w(tag, "failed to persist bounded recording location sidecar: ${error.javaClass.simpleName}")
            }
        }
    }
}

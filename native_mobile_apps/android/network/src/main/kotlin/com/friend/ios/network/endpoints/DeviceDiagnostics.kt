package com.friend.ios.network.endpoints

import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.Base64

/** Port of `APIClient+DeviceDiagnostics.swift`. */
interface DeviceDiagnosticsAPI {
    /**
     * `POST v1/mobile/device-diagnostics` with `{"bundle_base64": ...}` (Flutter `_sendToSupport`).
     * The backend answers 201 with a 12-character ticket support looks the bundle up by.
     */
    suspend fun uploadDeviceDiagnostics(bundle: ByteArray): String
}

internal class DeviceDiagnosticsEndpoints(private val http: HttpCore) : DeviceDiagnosticsAPI {
    override suspend fun uploadDeviceDiagnostics(bundle: ByteArray): String {
        val body = buildJsonObject { put("bundle_base64", Base64.getEncoder().encodeToString(bundle)) }
        val text = http.data(Method.POST, "v1/mobile/device-diagnostics", body = Body.Json(body.toString()))
        return diagnosticsTicket(text)
    }

    companion object {
        fun diagnosticsTicket(text: String): String =
            JsonAccess.obj(text).string("ticket")?.takeIf { it.isNotEmpty() } ?: throw APIError.Decoding("device-diagnostics: no ticket")
    }
}

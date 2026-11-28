package com.friend.ios.network.endpoints

import com.friend.ios.core.models.FirmwareRelease
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Port of `APIClient+Firmware.swift` (contract: `backend/routers/firmware.py`). */
interface FirmwareAPI {
    /**
     * `GET v2/firmware/latest`. The backend answers 404 when there is nothing newer for this
     * device, which is `null` here, not an error.
     */
    suspend fun latestFirmware(model: String, firmware: String, hardware: String?, manufacturer: String?): FirmwareRelease?
}

internal class FirmwareEndpoints(private val http: HttpCore) : FirmwareAPI {
    override suspend fun latestFirmware(model: String, firmware: String, hardware: String?, manufacturer: String?): FirmwareRelease? {
        val query = listOf(
            "device_model" to model,
            "firmware_revision" to firmware,
            // Required by the endpoint, unused by it; the Flutter app sends "Unknown" too.
            "hardware_revision" to (hardware ?: "Unknown"),
            "manufacturer_name" to (manufacturer ?: "Unknown"),
        )
        val text = try {
            http.data(Method.GET, "v2/firmware/latest", query = query)
        } catch (e: APIError.Http) {
            if (e.status == 404) return null
            throw e
        }
        return FirmwareReleaseMapper.release(JsonAccess.obj(text))
    }
}

/** The wire shape of `FirmwareVersionResponse`. */
internal object FirmwareReleaseMapper {
    /** `null` for a draft or a response without a version or download. */
    fun release(dto: JsonObject): FirmwareRelease? {
        if (dto.bool("draft") == true) return null
        val version = dto.string("version")?.takeIf { it.isNotEmpty() } ?: return null
        val zip = dto.string("zip_url")?.takeIf { it.isNotEmpty() } ?: return null
        return FirmwareRelease(
            version = version,
            minVersion = dto.string("min_version"),
            zipURL = zip,
            // The backend defaults to true; only an explicit false means MCUboot over SMP.
            isLegacySecureDFU = dto.bool("is_legacy_secure_dfu") ?: true,
            notes = notes(dto["changelog"]),
        )
    }

    private fun notes(changelog: Any?): String? {
        val lines = when (changelog) {
            is JsonArray -> changelog.mapNotNull { (it as? JsonPrimitive)?.content }
            is JsonPrimitive -> if (changelog.isString) changelog.content.lines() else emptyList()
            else -> emptyList()
        }
        val first = lines.map { it.trim(' ', '\t', '-', '*', '•') }.firstOrNull { it.isNotEmpty() } ?: return null
        return first.take(1).uppercase() + first.drop(1)
    }
}

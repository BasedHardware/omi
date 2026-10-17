package com.friend.ios.device

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Port of `PairedDevice.swift`: the paired wearable, encoded exactly like the Flutter app's
 * `btDevice` preference (`app/lib/backend/schema/bt_device/bt_device.dart:724-739`) so pairing
 * survives the update. On Android `id` is the Omi's Bluetooth address (uppercase), as Flutter
 * stored it.
 */
@Serializable
data class PairedDevice(
    val id: String,
    val name: String,
    val type: String = "omi",
    val rssi: Int = 0,
    val modelNumber: String? = null,
    val firmwareRevision: String? = null,
    val hardwareRevision: String? = null,
    val manufacturerName: String? = null,
    /** The per-unit id from Device Information (CV1 and later), when the firmware reports one. */
    val serialNumber: String? = null,
) {
    val encoded: String
        get() = buildJsonObject {
            put("name", name)
            put("id", id)
            put("type", type)
            put("rssi", rssi)
            modelNumber?.let { put("modelNumber", it) }
            firmwareRevision?.let { put("firmwareRevision", it) }
            hardwareRevision?.let { put("hardwareRevision", it) }
            manufacturerName?.let { put("manufacturerName", it) }
            serialNumber?.let { put("serialNumber", it) }
        }.toString()

    companion object {
        /**
         * Mistyped values never throw (Flutter `BtDevice.fromJson`): an `rssi` stored as a string
         * or a legacy integer `type` still decode.
         */
        fun decode(json: String?): PairedDevice? {
            if (json.isNullOrEmpty()) return null
            val obj = runCatching { Json.parseToJsonElement(json).jsonObject }.getOrNull() ?: return null
            fun text(key: String): String? = (obj[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
            val id = text("id")?.takeIf { it.isNotEmpty() } ?: return null
            val rawRssi = obj["rssi"] as? JsonPrimitive
            val rssi = rawRssi?.intOrNull ?: rawRssi?.content?.toDoubleOrNull()?.toInt() ?: 0
            val type = (obj["type"] as? JsonPrimitive)?.let { if (it.isString) it.content else null } ?: "omi"
            return PairedDevice(
                id = id,
                name = text("name").orEmpty(),
                type = type,
                rssi = rssi,
                modelNumber = text("modelNumber"),
                firmwareRevision = text("firmwareRevision"),
                hardwareRevision = text("hardwareRevision"),
                manufacturerName = text("manufacturerName"),
                serialNumber = text("serialNumber"),
            )
        }
    }
}

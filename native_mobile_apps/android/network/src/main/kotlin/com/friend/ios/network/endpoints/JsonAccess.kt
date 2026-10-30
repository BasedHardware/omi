package com.friend.ios.network.endpoints

import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull

/**
 * The `JSONSerialization` + `as? [String: Any]` reads of the hand-written Swift endpoints, for
 * payloads that have no generated DTO: tolerant, a missing or mistyped value reads as null.
 */
internal object JsonAccess {
    fun parse(text: String): JsonElement? = runCatching { Json.parseToJsonElement(text) }.getOrNull()

    fun obj(text: String): JsonObject = parse(text) as? JsonObject ?: JsonObject(emptyMap())

    fun array(text: String): JsonArray = parse(text) as? JsonArray ?: JsonArray(emptyList())
}

internal fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

internal fun JsonObject.array(key: String): JsonArray? = this[key] as? JsonArray

internal fun JsonObject.objects(key: String): List<JsonObject> = array(key)?.mapNotNull { it as? JsonObject }.orEmpty()

internal fun JsonObject.string(key: String): String? = (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content

internal fun JsonObject.strings(key: String): List<String> = array(key)?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }.orEmpty()

internal fun JsonObject.bool(key: String): Boolean? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull

/** `as? Int`, also a whole JSON number written as a double. */
internal fun JsonObject.int(key: String): Int? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.let { it.longOrNull?.toInt() ?: it.doubleOrNull?.toInt() }

internal fun JsonObject.double(key: String): Double? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull

/** The key is present and not null (`item["verified_at"] != nil`). */
internal fun JsonObject.has(key: String): Boolean = this[key] != null && this[key] !is JsonNull

/** `object(_:_:query:json:)` of the Swift endpoint files: the call, its body read as an object. */
internal suspend fun HttpCore.jsonObject(
    method: Method,
    path: String,
    query: List<Pair<String, String>> = emptyList(),
    json: JsonObject? = null,
): JsonObject {
    val text = data(method, path, query = query, body = json?.let { Body.Json(it.toString()) } ?: Body.None)
    return JsonAccess.obj(text)
}

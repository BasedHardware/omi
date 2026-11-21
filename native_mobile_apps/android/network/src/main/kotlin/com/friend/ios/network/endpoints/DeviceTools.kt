package com.friend.ios.network.endpoints

import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.core.models.DeviceToolResult
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.util.Base64

/**
 * Port of `DeviceToolFrame` (`APIClient+DeviceTools.swift`). Device tools on the chat stream
 * (backend `utils/device_tools.py`, `routers/chat.py`): the request declares what this phone can
 * run, a `tool:` frame (base64 JSON `{call_id, tool, arguments}`) asks for one, and the result
 * goes to `POST v2/messages/device-tool/{call_id}/result`.
 */
object DeviceToolFrame {
    /**
     * A frame that will not decode is dropped; one whose call id survived comes back with an
     * empty tool name, so the app can answer "malformed" instead of leaving the agent waiting.
     */
    fun parse(encoded: String): DeviceToolRequest? {
        val data = runCatching { Base64.getDecoder().decode(encoded.trim()) }.getOrNull() ?: return null
        val obj = JsonAccess.parse(String(data, Charsets.UTF_8)) as? JsonObject ?: return null
        val callID = obj.string("call_id")?.takeIf { it.isNotEmpty() } ?: return null
        val tool = obj.string("tool")?.takeIf { it.isNotEmpty() } ?: return DeviceToolRequest(id = callID, toolName = "")
        val arguments = obj.obj("arguments") ?: JsonObject(emptyMap())
        val recipients = when {
            arguments.array("to") != null -> arguments.strings("to").filter { it.isNotEmpty() }
            !arguments.string("to").isNullOrEmpty() -> listOf(arguments.string("to")!!)
            else -> emptyList()
        }
        return DeviceToolRequest(
            id = callID,
            toolName = tool,
            recipients = recipients,
            text = arguments.string("text") ?: "",
            subject = arguments.string("subject")?.takeIf { it.isNotEmpty() },
            query = arguments.string("query")?.trim() ?: "",
            limit = (arguments.int("limit") ?: 10).coerceIn(1, 50),
            permission = arguments.string("type")?.trim() ?: "",
        )
    }

    /** The result object, in the shape the Flutter and desktop clients send. */
    fun payload(result: DeviceToolResult): JsonObject = buildJsonObject {
        put("ok", result.ok)
        result.status?.let { put("status", it) }
        result.reason?.let { put("reason", it) }
        result.error?.let { put("error", it) }
        result.query?.let { put("query", it) }
        result.contacts?.let { contacts ->
            put("count", contacts.size)
            putJsonArray("contacts") {
                contacts.forEach { contact ->
                    addJsonObject {
                        put("id", contact.id)
                        put("name", contact.name)
                        putJsonArray("phone_numbers") {
                            contact.phoneNumbers.forEach { addJsonObject { put("label", it.label); put("value", it.value) } }
                        }
                        putJsonArray("email_addresses") {
                            contact.emailAddresses.forEach { addJsonObject { put("label", it.label); put("value", it.value) } }
                        }
                        put("preferred_messaging_handle", contact.preferredHandle)
                    }
                }
            }
        }
    }

    /** For tests: a frame as the backend writes it. */
    internal fun encode(callID: String, tool: String, arguments: Map<String, Any>): String {
        val obj = buildJsonObject {
            put("call_id", callID)
            put("tool", tool)
            put("arguments", buildJsonObject {
                arguments.forEach { (key, value) ->
                    when (value) {
                        is String -> put(key, value)
                        is Number -> put(key, JsonPrimitive(value))
                        is List<*> -> putJsonArray(key) { value.forEach { add(JsonPrimitive(it as String)) } }
                    }
                }
            })
        }
        return Base64.getEncoder().encodeToString(obj.toString().toByteArray())
    }
}

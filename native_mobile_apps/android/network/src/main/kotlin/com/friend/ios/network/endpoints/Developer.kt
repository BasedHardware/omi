package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.DeveloperKey
import com.friend.ios.core.models.DeveloperWebhook
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Port of `APIClient+Developer.swift`: webhooks and developer / MCP keys. */
interface DeveloperAPI {
    /** `GET v1/users/developer/webhooks/status`: which webhooks are on. */
    suspend fun webhookStatus(): Map<DeveloperWebhook, Boolean>
    /** `GET v1/users/developer/webhook/{type}` → the stored URL ("" when none). */
    suspend fun webhookURL(hook: DeveloperWebhook): String
    /** `POST v1/users/developer/webhook/{type}`. An empty URL also turns it off, any other turns it on; a private address is refused (400). */
    suspend fun setWebhookURL(hook: DeveloperWebhook, url: String)
    /** `POST v1/users/developer/webhook/{type}/enable|disable`. */
    suspend fun setWebhook(hook: DeveloperWebhook, enabled: Boolean)
    /** `GET v1/dev/keys` or `v1/mcp/keys`. */
    suspend fun developerKeys(kind: DeveloperKey.Kind): List<DeveloperKey>
    /** `POST v1/dev/keys` / `v1/mcp/keys` with a name; the answer carries the secret once. */
    suspend fun createDeveloperKey(kind: DeveloperKey.Kind, name: String, scopes: List<String>?): DeveloperKey
    /** `DELETE v1/dev/keys/{id}` / `v1/mcp/keys/{id}` (204). */
    suspend fun revokeDeveloperKey(kind: DeveloperKey.Kind, id: String)
}

internal class DeveloperEndpoints(private val http: HttpCore) : DeveloperAPI {
    override suspend fun webhookStatus(): Map<DeveloperWebhook, Boolean> {
        val o = http.jsonObject(Method.GET, "v1/users/developer/webhooks/status")
        return DeveloperWebhook.entries.associateWith { o.bool(it.rawValue) ?: false }
    }

    override suspend fun webhookURL(hook: DeveloperWebhook): String = http.jsonObject(Method.GET, "v1/users/developer/webhook/${hook.rawValue}").string("url").orEmpty()

    override suspend fun setWebhookURL(hook: DeveloperWebhook, url: String) {
        http.data(Method.POST, "v1/users/developer/webhook/${hook.rawValue}", body = Body.Json(buildJsonObject { put("url", url) }.toString()))
    }

    override suspend fun setWebhook(hook: DeveloperWebhook, enabled: Boolean) {
        http.data(Method.POST, "v1/users/developer/webhook/${hook.rawValue}/${if (enabled) "enable" else "disable"}")
    }

    override suspend fun developerKeys(kind: DeveloperKey.Kind): List<DeveloperKey> =
        JsonAccess.array(http.data(Method.GET, "v1/${kind.rawValue}/keys")).mapNotNull { (it as? JsonObject)?.let(DeveloperMapper::key) }

    override suspend fun createDeveloperKey(kind: DeveloperKey.Kind, name: String, scopes: List<String>?): DeveloperKey {
        val fields = mutableMapOf<String, kotlinx.serialization.json.JsonElement>("name" to JsonPrimitive(name))
        if (scopes != null) fields["scopes"] = JsonArray(scopes.map(::JsonPrimitive))
        val text = http.data(Method.POST, "v1/${kind.rawValue}/keys", body = Body.Json(JsonObject(fields).toString()))
        return DeveloperMapper.key(JsonAccess.obj(text)) ?: throw APIError.Decoding("key without id")
    }

    override suspend fun revokeDeveloperKey(kind: DeveloperKey.Kind, id: String) {
        http.data(Method.DELETE, "v1/${kind.rawValue}/keys/$id")
    }
}

/** `DeveloperKey.from`. */
object DeveloperMapper {
    fun key(o: JsonObject): DeveloperKey? {
        val id = o.string("id") ?: return null
        return DeveloperKey(
            id = id, name = o.string("name").orEmpty(), prefix = o.string("key_prefix").orEmpty(),
            createdAt = BackendDate.parse(o.string("created_at")), lastUsedAt = BackendDate.parse(o.string("last_used_at")),
            scopes = o.strings("scopes"), secret = o.string("key"),
        )
    }
}

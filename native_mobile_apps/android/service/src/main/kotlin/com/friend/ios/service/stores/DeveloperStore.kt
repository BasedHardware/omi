package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.DeveloperKey
import com.friend.ios.core.models.DeveloperWebhook
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.CancellationException
import java.net.URI

/**
 * Port of `DeveloperStore.swift`: Settings > Developer (Flutter `pages/settings/developer.dart`):
 * webhooks, API and MCP keys, the MCP config, debug logs and the experimental switches the
 * backend honours.
 */
class DeveloperStore(
    internal val api: APIClientProtocol,
    private val preferences: Preferences,
    apiBaseURL: String,
) {
    data class Webhook(
        /** What is typed (not saved yet). */
        val url: String = "",
        /** Audio bytes only: seconds of audio per call. */
        val seconds: Int = DeveloperWebhook.DEFAULT_AUDIO_INTERVAL,
        val isEnabled: Boolean = false,
        /** What the backend has, to tell unsaved edits apart. */
        val savedURL: String = "",
        val savedSeconds: Int = DeveloperWebhook.DEFAULT_AUDIO_INTERVAL,
    ) {
        val hasChanges: Boolean get() = url.trim() != savedURL || (url.isNotEmpty() && seconds != savedSeconds)
    }

    sealed interface Failure {
        /** Not a public http(s) address (checked here, and by the backend). */
        data class InvalidURL(val hook: DeveloperWebhook) : Failure
        data object CouldNotSave : Failure
        data object CouldNotLoad : Failure
    }

    var webhooks: Map<DeveloperWebhook, Webhook> by mutableStateOf(DeveloperWebhook.entries.associateWith { Webhook() })
        internal set
    var apiKeys: List<DeveloperKey> by mutableStateOf(emptyList())
        private set
    var mcpKeys: List<DeveloperKey> by mutableStateOf(emptyList())
        private set
    /** A key just created: its secret is shown once, then only its prefix. */
    var createdKey: DeveloperKey? by mutableStateOf(null)
    /** Which list [createdKey] belongs to. */
    var createdKeyKind: DeveloperKey.Kind? by mutableStateOf(null)
        private set
    var isLoading: Boolean by mutableStateOf(false)
        private set
    var isSaving: Boolean by mutableStateOf(false)
        private set
    var failure: Failure? by mutableStateOf(null)

    /** `https://api.../v1/mcp` (Flutter `mcp_config.dart`). */
    val mcpServerURL: String = apiBaseURL.trimEnd('/') + "/v1/mcp"

    private var modeState by mutableStateOf(preferences.bool(NativeKey.DeveloperMode, false))
    private var conversationTools by mutableStateOf(preferences.bool(Key.DevModeEnabled))
    private var vadGateEnabled by mutableStateOf(preferences.bool(Key.VadGateEnabled))

    /** Settings shows the Developer row (switched in Help). */
    var isDeveloperMode: Boolean
        get() = modeState
        set(value) {
            modeState = value
            preferences.set(NativeKey.DeveloperMode, value)
        }

    /** Conversation developer tools: Copy ID in a conversation's menu (Flutter `devModeEnabled`). */
    var showsConversationTools: Boolean
        get() = conversationTools
        set(value) {
            conversationTools = value
            preferences.set(Key.DevModeEnabled, value)
        }

    /** `vad_gate=enabled` on the next recording: the backend sends only speech to transcription. */
    var vadGate: Boolean
        get() = vadGateEnabled
        set(value) {
            vadGateEnabled = value
            preferences.set(Key.VadGateEnabled, value)
        }

    suspend fun load() {
        isLoading = true
        try {
            val status = api.webhookStatus()
            val loaded = DeveloperWebhook.entries.associateWith { hook ->
                val stored = api.webhookURL(hook)
                if (hook == DeveloperWebhook.AudioBytes) {
                    val (url, seconds) = DeveloperWebhook.splitAudio(stored)
                    Webhook(url, seconds, status[hook] ?: false, url, seconds)
                } else {
                    Webhook(url = stored, isEnabled = status[hook] ?: false, savedURL = stored)
                }
            }
            webhooks = loaded
            apiKeys = api.developerKeys(DeveloperKey.Kind.Api)
            mcpKeys = api.developerKeys(DeveloperKey.Kind.Mcp)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            failure = Failure.CouldNotLoad
        } finally {
            isLoading = false
        }
    }

    // MARK: Webhooks

    fun edit(hook: DeveloperWebhook, url: String? = null, seconds: Int? = null) {
        val current = webhooks[hook] ?: return
        webhooks = webhooks + (hook to current.copy(url = url ?: current.url, seconds = seconds?.let { maxOf(1, it) } ?: current.seconds))
    }

    /** Back to what the backend has. */
    fun discardWebhookEdits() {
        webhooks = webhooks.mapValues { (_, hook) -> hook.copy(url = hook.savedURL, seconds = hook.savedSeconds) }
    }

    val hasUnsavedWebhooks: Boolean get() = webhooks.values.any { it.hasChanges }

    /** Saves every changed URL. An empty URL turns its webhook off, a new one turns it on (backend). */
    suspend fun saveWebhooks(): Boolean {
        failure = null
        val changed = DeveloperWebhook.entries.filter { webhooks[it]?.hasChanges == true }
        changed.firstOrNull { !isValidWebhook(webhooks[it]?.url.orEmpty()) }?.let {
            failure = Failure.InvalidURL(it)
            return false
        }
        isSaving = true
        try {
            for (hook in changed) {
                val webhook = webhooks[hook] ?: continue
                val url = webhook.url.trim()
                val stored = if (hook == DeveloperWebhook.AudioBytes) DeveloperWebhook.joinAudio(url, webhook.seconds) else url
                try {
                    api.setWebhookURL(hook, stored)
                    webhooks = webhooks + (hook to Webhook(url, webhook.seconds, url.isNotEmpty(), url, webhook.seconds))
                } catch (e: CancellationException) {
                    throw e
                } catch (e: APIError.Http) {
                    failure = if (e.status == 400 || e.status == 422) Failure.InvalidURL(hook) else Failure.CouldNotSave
                    return false
                } catch (e: Exception) {
                    failure = Failure.CouldNotSave
                    return false
                }
            }
            return true
        } finally {
            isSaving = false
        }
    }

    /** The switch beside a saved URL; taken back if the backend refuses. */
    suspend fun setEnabled(hook: DeveloperWebhook, enabled: Boolean) {
        val current = webhooks[hook] ?: return
        if (current.isEnabled == enabled) return
        webhooks = webhooks + (hook to current.copy(isEnabled = enabled))
        try {
            api.setWebhook(hook, enabled)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            webhooks[hook]?.let { webhooks = webhooks + (hook to it.copy(isEnabled = !enabled)) }
            failure = Failure.CouldNotSave
        }
    }

    // MARK: Keys

    /** Creates a key; the secret lands in [createdKey]. API keys are read-only unless [fullAccess]. */
    suspend fun createKey(kind: DeveloperKey.Kind, name: String, fullAccess: Boolean = false): Boolean {
        val trimmed = name.trim()
        if (trimmed.isEmpty()) return false
        failure = null
        val scopes = if (kind == DeveloperKey.Kind.Api && fullAccess) fullAccessScopes else null
        return try {
            val key = api.createDeveloperKey(kind, trimmed, scopes)
            createdKey = key
            createdKeyKind = kind
            val listed = key.copy(secret = null)
            if (kind == DeveloperKey.Kind.Api) apiKeys = listOf(listed) + apiKeys else mcpKeys = listOf(listed) + mcpKeys
            true
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            failure = Failure.CouldNotSave
            false
        }
    }

    suspend fun revoke(kind: DeveloperKey.Kind, id: String) {
        val previous = apiKeys to mcpKeys
        if (kind == DeveloperKey.Kind.Api) apiKeys = apiKeys.filter { it.id != id } else mcpKeys = mcpKeys.filter { it.id != id }
        try {
            api.revokeDeveloperKey(kind, id)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            apiKeys = previous.first
            mcpKeys = previous.second
            failure = Failure.CouldNotSave
        }
    }

    /** The Claude Code / Cursor `mcpServers` entry for [key] (Flutter `mcp_config.dart`). */
    fun mcpConfig(key: String): String = """
        {
          "mcpServers": {
            "omi": {
              "type": "http",
              "url": "$mcpServerURL",
              "headers": {
                "Authorization": "Bearer $key"
              }
            }
          }
        }
    """.trimIndent()

    companion object {
        /** Every API scope (backend `utils/scopes.py`). */
        val fullAccessScopes: List<String> = listOf("conversations", "memories", "action_items", "goals").flatMap { listOf("$it:read", "$it:write") }

        /** Empty (clears it) or an http(s) URL with a host; the backend also refuses private addresses. */
        fun isValidWebhook(text: String): Boolean {
            val trimmed = text.trim()
            if (trimmed.isEmpty()) return true
            if (trimmed.contains(" ")) return false
            val uri = runCatching { URI(trimmed) }.getOrNull() ?: return false
            val scheme = uri.scheme?.lowercase() ?: return false
            if (scheme !in setOf("http", "https")) return false
            val host = uri.host ?: return false
            return host.contains(".") || host == "localhost"
        }
    }
}

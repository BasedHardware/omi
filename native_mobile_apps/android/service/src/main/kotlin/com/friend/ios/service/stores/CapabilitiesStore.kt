package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.Integration
import com.friend.ios.core.models.OmiApp
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import kotlinx.coroutines.CancellationException

/**
 * Port of `CapabilitiesStore.swift`: what Omi can use on the user's behalf: calendar, mail,
 * health and every task app in one list, instead of split across Settings and the Tasks tab.
 */
class CapabilitiesStore(private val api: APIClientProtocol) {
    /** Why connecting an app did not work, so its row can say so instead of doing nothing. */
    enum class ConnectFailure {
        /** This server has no login set up for the app (the backend lacks its OAuth client). */
        NotConfigured,
        /** Omi could not be reached. */
        Offline,
        /** The person closed the login page. */
        Cancelled,
        /** The login page or the server reported an error. */
        Failed,
    }

    var integrations: List<Integration> by mutableStateOf(catalog)
        private set
    var isLoading: Boolean by mutableStateOf(false)
        private set
    var connecting: String? by mutableStateOf(null)
        private set
    /** The last failed connect per app id; cleared when the app is tried again or connects. */
    var failures: Map<String, ConnectFailure> by mutableStateOf(emptyMap())
        private set

    val connectedCount: Int get() = integrations.count { it.isConnected }

    suspend fun load() {
        isLoading = true
        try {
            val taskApps = attempt { api.connectedTaskApps() } ?: emptySet()
            val updated = integrations.map { integration ->
                when (integration.kind) {
                    Integration.Kind.TaskApp -> integration.copy(isConnected = integration.id in taskApps)
                    Integration.Kind.Integration -> integration.copy(isConnected = attempt { api.integrationConnected(integration.id) } ?: false)
                }
            }
            integrations = updated
            failures = failures - updated.filter { it.isConnected }.map { it.id }.toSet()
        } finally {
            isLoading = false
        }
    }

    /**
     * The URL to open for connecting; the caller presents it and calls [load] when it returns.
     * null with `failures[id]` set when there is none.
     */
    suspend fun authorizationURL(integration: Integration): String? {
        connecting = integration.id
        failures = failures - integration.id
        return try {
            api.integrationOAuthURL(integration)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            failures = failures + (integration.id to failure(e))
            null
        } finally {
            connecting = null
        }
    }

    /** The login page closed without connecting: `cancelled` when the person closed it. */
    fun loginEnded(integration: Integration, cancelled: Boolean) {
        failures = failures + (integration.id to if (cancelled) ConnectFailure.Cancelled else ConnectFailure.Failed)
    }

    // MARK: Apps

    var installedApps: List<OmiApp> by mutableStateOf(emptyList())
        private set
    var discoveredApps: List<OmiApp> by mutableStateOf(emptyList())
        private set

    suspend fun loadApps(query: String = "") {
        installedApps = attempt { api.searchApps("", installedOnly = true, offset = 0) } ?: emptyList()
        discoveredApps = attempt { api.searchApps(query, installedOnly = false, offset = 0) } ?: emptyList()
    }

    /** Optimistic install / uninstall. */
    suspend fun setApp(app: OmiApp, enabled: Boolean) {
        fun apply(value: Boolean) {
            discoveredApps = discoveredApps.map { if (it.id == app.id) it.copy(isEnabled = value) else it }
            installedApps = if (value) {
                if (installedApps.any { it.id == app.id }) installedApps else installedApps + app.copy(isEnabled = true)
            } else {
                installedApps.filter { it.id != app.id }
            }
        }
        apply(enabled)
        try {
            api.setApp(app.id, enabled)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            apply(!enabled)
        }
    }

    suspend fun disconnect(integration: Integration) {
        attempt { api.disconnectIntegration(integration) }
        load()
    }

    private suspend fun <T> attempt(block: suspend () -> T): T? = try {
        block()
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        null
    }

    companion object {
        /** Order shown; ids are the backend keys. */
        val catalog = listOf(
            Integration("google_calendar", Integration.Kind.Integration, false),
            Integration("gmail", Integration.Kind.Integration, false),
            Integration("todoist", Integration.Kind.TaskApp, false),
            Integration("asana", Integration.Kind.TaskApp, false),
            Integration("clickup", Integration.Kind.TaskApp, false),
            Integration("google_tasks", Integration.Kind.TaskApp, false),
        )

        fun failure(error: Throwable): ConnectFailure = when (error) {
            // "Google Calendar not configured - GOOGLE_CLIENT_ID missing", "Todoist not configured".
            is APIError.Http -> if (error.body.contains("not configured", ignoreCase = true)) ConnectFailure.NotConfigured else ConnectFailure.Failed
            is APIError.Transport -> ConnectFailure.Offline
            is java.io.IOException -> ConnectFailure.Offline
            else -> ConnectFailure.Failed
        }
    }
}

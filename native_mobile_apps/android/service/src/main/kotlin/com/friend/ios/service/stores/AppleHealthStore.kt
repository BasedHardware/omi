package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.HealthSummary
import com.friend.ios.core.models.Integration
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.NativeKey
import java.time.Duration
import java.time.Instant

/** The health store, read only (behind a seam: Health Connect in the app, a fake in tests). */
interface HealthDataReading {
    val isAvailable: Boolean

    /** Shows the permission screen; true when something may be read afterwards. */
    suspend fun requestAuthorization(): Boolean

    /**
     * Read access is there (iOS: any sample readable in the last 90 days, the only way HealthKit
     * tells; Health Connect says which read permissions are granted).
     */
    suspend fun probeAccess(): Boolean

    suspend fun summary(days: Int): HealthSummary?
}

/**
 * Port of `AppleHealthStore.swift`, on Health Connect. Settings > Capabilities > Health Connect
 * (Flutter `apple_health_detail_page`, `apple_health_service.dart`): connect asks for read access,
 * checks it, syncs the last 7 days to `PUT v1/integrations/apple-health/sync` and marks the
 * integration connected. While connected, the summary is synced again when the app comes back
 * (Flutter syncs when the chat opens). The backend key stays `apple_health` for both platforms.
 */
class AppleHealthStore(
    private val api: APIClientProtocol,
    private val reader: HealthDataReading,
    private val preferences: Preferences,
    private val now: () -> Instant = Instant::now,
) {
    enum class Phase { Idle, Connecting, Disconnecting }

    enum class Notice { Connected, Denied, Unavailable, Failed, Disconnected, DisconnectFailed }

    var isConnected: Boolean by mutableStateOf(false)
        private set
    var lastSync: Instant? by mutableStateOf(preferences.string(NativeKey.HealthLastSync)?.toDoubleOrNull()?.let { Instant.ofEpochMilli((it * 1000).toLong()) })
        private set
    var phase: Phase by mutableStateOf(Phase.Idle)
        private set
    /** What the last connect / disconnect came to; the screen shows it once. */
    var notice: Notice? by mutableStateOf(null)

    /** When `syncIfConnected` last asked the backend. */
    private var lastCheck: Instant? = null

    val isAvailable: Boolean get() = reader.isAvailable

    private val integration: Integration get() = Integration(KEY, Integration.Kind.Integration, isConnected)

    /** `GET v1/integrations/apple_health`. */
    suspend fun load() {
        runCatching { api.integrationConnected(KEY) }.onSuccess { isConnected = it }
    }

    suspend fun connect() {
        if (phase != Phase.Idle) return
        if (!reader.isAvailable) {
            notice = Notice.Unavailable
            return
        }
        phase = Phase.Connecting
        try {
            if (!reader.requestAuthorization() || !reader.probeAccess()) {
                notice = Notice.Denied
                return
            }
            // The connection stands even when the first sync fails (Flutter logs and carries on).
            sync()
            try {
                api.markAppleHealthConnected()
                isConnected = true
                notice = Notice.Connected
            } catch (error: Exception) {
                notice = Notice.Failed
            }
        } finally {
            phase = Phase.Idle
        }
    }

    suspend fun disconnect() {
        if (phase != Phase.Idle) return
        phase = Phase.Disconnecting
        try {
            api.disconnectIntegration(integration)
            isConnected = false
            notice = Notice.Disconnected
        } catch (error: Exception) {
            notice = Notice.DisconnectFailed
        } finally {
            phase = Phase.Idle
        }
    }

    /** The last 7 days to the backend; false when nothing was readable or the upload failed. */
    suspend fun sync(): Boolean {
        val summary = reader.summary(PERIOD_DAYS)?.takeIf { it.hasData } ?: return false
        val date = try {
            api.syncAppleHealth(summary) ?: now()
        } catch (error: Exception) {
            return false
        }
        lastSync = date
        preferences.set(NativeKey.HealthLastSync, (date.toEpochMilli() / 1000.0).toString())
        return true
    }

    /** Back in the app: a fresh summary while connected, at most once an hour. */
    suspend fun syncIfConnected() {
        if (!reader.isAvailable || phase != Phase.Idle) return
        val recent = listOfNotNull(lastSync, lastCheck).maxOrNull()
        if (recent != null && Duration.between(recent, now()) < AUTO_SYNC_INTERVAL) return
        lastCheck = now()
        load()
        if (!isConnected) return
        sync()
    }

    companion object {
        const val KEY = "apple_health"
        internal const val PERIOD_DAYS = 7
        /** At most one automatic sync per this interval. */
        internal val AUTO_SYNC_INTERVAL: Duration = Duration.ofHours(1)
    }
}

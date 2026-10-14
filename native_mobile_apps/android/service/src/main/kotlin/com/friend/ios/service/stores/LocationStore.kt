package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.GeolocationSnapshot
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant

/** Location access as the app shows it (while in use only; Omi never asks for background access). */
enum class LocationAccess { NotDetermined, Allowed, Denied }

/** The device's location, behind a seam so the store's rules test without the platform. */
interface LocationProviding {
    val access: LocationAccess

    /** Shows the system prompt (while in use) and returns the answer. */
    suspend fun requestAccess(): LocationAccess

    /** The OS's last fix, if any (instant). */
    suspend fun lastKnown(): GeolocationSnapshot?

    /** A fresh fix, or null after [timeoutMillis]. */
    suspend fun currentFix(timeoutMillis: Long): GeolocationSnapshot?
}

/**
 * Port of `LocationStore.swift`. Where a recording starts (Flutter `ConversationLocationCapture`):
 * the position travels with the conversation (`X-Omi-Conversation-Geolocation`) and, best effort,
 * to the user-location cache. Location is metadata: it never holds up recording for long and every
 * failure just means "no place".
 */
class LocationStore(
    private val provider: LocationProviding,
    private val api: APIClientProtocol,
    private val scope: CoroutineScope,
    private val now: () -> Instant = Instant::now,
) {
    var access: LocationAccess by mutableStateOf(provider.access)
        private set

    /** The system may have changed it (system settings, "Only this time" expiring). */
    fun refresh() {
        access = provider.access
    }

    /** Onboarding and Settings > Data & Privacy. */
    suspend fun requestAccess() {
        access = provider.requestAccess()
    }

    /**
     * The recording's location. Never asked here: the permission is asked in onboarding's
     * permissions step or Settings > Privacy, never as a surprise prompt mid-flow (a recording runs
     * during onboarding too). Without access the recording simply goes without a place.
     */
    suspend fun snapshotForRecording(): GeolocationSnapshot? {
        refresh()
        if (access != LocationAccess.Allowed) return null
        val last = runCatching { provider.lastKnown() }.getOrNull()
        val snapshot = if (last != null && isFresh(last)) last else runCatching { provider.currentFix(FIX_TIMEOUT_MILLIS) }.getOrNull()
        if (snapshot != null) scope.launch { runCatching { api.updateUserGeolocation(snapshot) } }
        return snapshot
    }

    private fun isFresh(snapshot: GeolocationSnapshot): Boolean {
        val age = Duration.between(snapshot.capturedAt, now())
        return !age.isNegative && age <= LAST_KNOWN_MAX_AGE
    }

    companion object {
        /** A last-known fix up to this old is used instead of waiting for a fresh one. */
        val LAST_KNOWN_MAX_AGE: Duration = Duration.ofMinutes(5)
        const val FIX_TIMEOUT_MILLIS = 2_000L
    }
}

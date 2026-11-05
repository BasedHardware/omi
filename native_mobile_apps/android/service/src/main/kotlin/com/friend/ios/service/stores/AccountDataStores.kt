package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.AppDataAccess
import com.friend.ios.core.models.FairUseStatus
import com.friend.ios.core.models.UsageStats
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File
import java.util.TimeZone

/**
 * Port of `AccountDataStores.swift`. Plan & usage beyond the quota (Flutter `usage_page`,
 * `fair_use_page`): words, insights and memories per period, and the fair-use standing.
 */
class UsageStore(private val api: APIClientProtocol, private val timeZone: String = TimeZone.getDefault().id) {
    var period: UsageStats.Period by mutableStateOf(UsageStats.Period.Monthly)
    var stats: Map<UsageStats.Period, UsageStats> by mutableStateOf(emptyMap())
        private set
    var fairUse: FairUseStatus? by mutableStateOf(null)
        private set
    var failedPeriods: Set<UsageStats.Period> by mutableStateOf(emptySet())
        private set
    var fairUseFailed: Boolean by mutableStateOf(false)
        private set

    val current: UsageStats? get() = stats[period]

    suspend fun load(period: UsageStats.Period? = null) {
        val target = period ?: this.period
        try {
            stats = stats + (target to api.usage(target, timeZone))
            failedPeriods = failedPeriods - target
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            failedPeriods = failedPeriods + target
        }
    }

    suspend fun loadFairUse() {
        try {
            fairUse = api.fairUseStatus()
            fairUseFailed = false
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            fairUseFailed = true
        }
    }
}

/**
 * Profile and data: invite link, apps that read your data, export, cancel subscription, and
 * keeping audio on the phone (Flutter `profile`, `data_privacy_page`, `data_export`,
 * `cancel_subscription_sheet`, `local_storage_page`).
 */
class ProfileStore(
    private val api: APIClientProtocol,
    private val preferences: Preferences,
    private val scope: CoroutineScope,
    /** Where exports are written (the app's cache directory; shared through a FileProvider). */
    private val exportDirectory: File,
) {
    sealed interface ExportPhase {
        data object Idle : ExportPhase
        data object Exporting : ExportPhase
        data class Ready(val file: File) : ExportPhase
        data object Failed : ExportPhase
    }

    var referralURL: String? by mutableStateOf(null)
        private set
    var referralFailed: Boolean by mutableStateOf(false)
        private set
    var appsWithAccess: List<AppDataAccess>? by mutableStateOf(null)
        private set
    var exportPhase: ExportPhase by mutableStateOf(ExportPhase.Idle)
        private set
    var lastError: String? by mutableStateOf(null)
        private set
    private var exportJob: Job? = null

    private var audioOnPhone by mutableStateOf(preferences.bool(Key.UnlimitedLocalStorageEnabled))

    /** Keep every recording on this phone, not only the ones that have not reached the cloud yet (Flutter's key). */
    var storesAudioOnPhone: Boolean
        get() = audioOnPhone
        set(value) {
            audioOnPhone = value
            preferences.set(Key.UnlimitedLocalStorageEnabled, value)
        }

    suspend fun loadReferral() {
        try {
            referralURL = api.referralURL()
            referralFailed = referralURL == null
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            referralFailed = true
        }
    }

    suspend fun loadAppsWithAccess() {
        appsWithAccess = runCatching { api.appsWithDataAccess() }.getOrNull() ?: appsWithAccess ?: emptyList()
    }

    /** Downloads everything Omi stores; [cancelExport] stops it. */
    fun export() {
        exportJob?.cancel()
        exportPhase = ExportPhase.Exporting
        exportJob = scope.launch {
            val result = runCatching { api.exportAllData(exportDirectory) }.getOrNull()
            if (!isActive) {
                result?.parentFile?.deleteRecursively()
                return@launch
            }
            exportPhase = result?.let { ExportPhase.Ready(it) } ?: ExportPhase.Failed
        }
    }

    fun cancelExport() {
        exportJob?.cancel()
        exportJob = null
        exportPhase = ExportPhase.Idle
    }

    /** The share sheet closed: the temporary copy goes. */
    fun finishExport() {
        (exportPhase as? ExportPhase.Ready)?.file?.parentFile?.deleteRecursively()
        exportPhase = ExportPhase.Idle
    }

    /** Stripe cancels at the end of the billing period. Returns whether the backend took it. */
    suspend fun cancelSubscription(reason: String?, details: String?): Boolean {
        lastError = null
        return try {
            api.cancelSubscription(reason, details?.trim())
            true
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            lastError = e.toString()
            false
        }
    }
}

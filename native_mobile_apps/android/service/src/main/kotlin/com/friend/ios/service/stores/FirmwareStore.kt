package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.FirmwareRelease
import com.friend.ios.core.models.FirmwareVersion
import com.friend.ios.device.FirmwareUpdating
import com.friend.ios.device.PairedDevice
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.persistence.Preferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

/** What the firmware update needs from the device side (real: `DeviceStore`; tests: a fake). */
interface FirmwareDeviceHost {
    val paired: PairedDevice?
    val connection: DeviceStore.Connection
    val battery: Int?

    /** The firmware revision read on the current connection. */
    val liveFirmware: String?
    fun suspendForFirmwareUpdate()
    fun resumeAfterFirmwareUpdate()
}

/**
 * Port of `FirmwareStore.swift`: Omi firmware updates, kept to one row in My Devices. Checks the
 * backend when the Omi connects (at most once a day), and on the user's confirmation downloads,
 * flashes and waits for the Omi to come back on the new version. No rollback, no channels.
 */
class FirmwareStore(
    private val api: APIClientProtocol,
    private val devices: FirmwareDeviceHost,
    private val updater: FirmwareUpdating,
    private val preferences: Preferences,
    private val scope: CoroutineScope,
    private val download: suspend (String) -> File,
    private val now: () -> Long = System::currentTimeMillis,
    private val handOverDelayMillis: Long = 2_000,
) {
    sealed interface Phase {
        data object Idle : Phase
        data object Downloading : Phase

        /** Upload progress, 0...1. */
        data class Installing(val progress: Double) : Phase

        /** Flashed; the Omi restarts and reconnects on its own. */
        data object Restarting : Phase
        data class Finished(val version: String) : Phase
        data class Failed(val failure: Failure) : Phase
    }

    enum class Failure { LowBattery, NotConnected, Download, Install }

    /** The update on offer for the paired Omi, if any. */
    var available: FirmwareRelease? by mutableStateOf(null)
        private set
    var phase: Phase by mutableStateOf(Phase.Idle)
        private set

    /** The last check, persisted so a relaunch does not ask again the same day. */
    @Serializable
    internal data class Check(val deviceID: String, val firmware: String, val checkedAt: Long, val release: FirmwareRelease?)

    private var checking = false
    private var lastFailedCheck: Long? = null
    private var target: FirmwareVersion? = null

    val isBusy: Boolean
        get() = when (phase) {
            Phase.Downloading, is Phase.Installing, Phase.Restarting -> true
            else -> false
        }

    /** Device info arrived (wired to `DeviceStore.onDeviceInfo`): finishes a pending update or checks for one. */
    fun deviceInfoChanged() {
        val firmware = devices.liveFirmware ?: return
        val pending = target
        if (phase == Phase.Restarting && pending != null) {
            // MCUboot keeps the old image when the new one does not boot.
            val running = FirmwareVersion.parse(firmware)
            if (running != null && running >= pending) {
                phase = Phase.Finished(firmware)
                available = null
            } else {
                phase = Phase.Failed(Failure.Install)
            }
            target = null
            return
        }
        scope.launch { checkIfDue() }
    }

    /** Asks the backend for a newer firmware unless it was asked for this device and version within the last day. */
    suspend fun checkIfDue() {
        if (checking || isBusy) return
        val device = devices.paired ?: return
        val model = device.modelNumber ?: return
        val firmware = devices.liveFirmware ?: return
        if (FirmwareVersion.parse(firmware) == null) return
        cachedCheck()?.let { cached ->
            if (cached.deviceID == device.id && cached.firmware == firmware && now() - cached.checkedAt < CHECK_INTERVAL_MS) {
                available = cached.release?.takeIf { it.isUpdate(firmware) }
                return
            }
        }
        lastFailedCheck?.let { if (now() - it < RETRY_INTERVAL_MS) return }
        checking = true
        try {
            val release = api.latestFirmware(model, firmware, device.hardwareRevision, device.manufacturerName)
            lastFailedCheck = null
            val check = Check(device.id, firmware, now(), release)
            preferences.set(Preferences.NativeKey.FirmwareCheck, json.encodeToString(Check.serializer(), check))
            available = release?.takeIf { it.isUpdate(firmware) }
        } catch (e: Exception) {
            lastFailedCheck = now()
        } finally {
            checking = false
        }
    }

    /**
     * Runs the update. Only ever called from the confirmation the user tapped; refuses below
     * [MINIMUM_BATTERY] or without a connected Omi.
     */
    suspend fun install() {
        if (isBusy) return
        val release = available ?: return
        val id = devices.paired?.id ?: return
        if (devices.connection != DeviceStore.Connection.Connected) {
            phase = Phase.Failed(Failure.NotConnected)
            return
        }
        val battery = devices.battery
        if (battery == null || battery < MINIMUM_BATTERY) {
            phase = Phase.Failed(Failure.LowBattery)
            return
        }
        phase = Phase.Downloading
        val firmwarePackage = try {
            download(release.zipURL)
        } catch (e: Exception) {
            phase = Phase.Failed(Failure.Download)
            return
        }
        devices.suspendForFirmwareUpdate()
        delay(handOverDelayMillis)
        phase = Phase.Installing(0.0)
        try {
            updater.update(id, firmwarePackage).collect { phase = Phase.Installing(it) }
        } catch (e: Exception) {
            firmwarePackage.delete()
            devices.resumeAfterFirmwareUpdate()
            phase = Phase.Failed(Failure.Install)
            return
        }
        firmwarePackage.delete()
        target = FirmwareVersion.parse(release.version)
        preferences.set(Preferences.NativeKey.FirmwareCheck, null)
        phase = Phase.Restarting
        devices.resumeAfterFirmwareUpdate()
    }

    /** Back to the update row after a failure or a finished update. */
    fun dismissResult() {
        if (isBusy) return
        phase = Phase.Idle
    }

    private fun cachedCheck(): Check? = preferences.string(Preferences.NativeKey.FirmwareCheck)
        ?.let { runCatching { json.decodeFromString(Check.serializer(), it) }.getOrNull() }

    companion object {
        /** An update may only start at this battery level or above. */
        const val MINIMUM_BATTERY = 20
        const val CHECK_INTERVAL_MS = 24L * 60 * 60 * 1000

        /** A failed check (offline, backend down) is retried on a later connect, not on every read. */
        const val RETRY_INTERVAL_MS = 10L * 60 * 1000
        private val json = Json { ignoreUnknownKeys = true }

        /** Downloads the OTA package into `directory`, keeping the `.zip` extension the DFU reader looks at. */
        fun downloadPackage(directory: File): suspend (String) -> File = { url ->
            withContext(Dispatchers.IO) {
                val connection = URL(url).openConnection() as HttpURLConnection
                try {
                    if (connection.responseCode !in 200..299) throw APIError.Http(connection.responseCode, "")
                    val ext = url.substringBefore('?').substringAfterLast('/').substringAfterLast('.', "zip").ifEmpty { "zip" }
                    val file = File(directory, "omi-firmware-${UUID.randomUUID()}.$ext")
                    file.outputStream().use { out -> connection.inputStream.use { it.copyTo(out) } }
                    file
                } finally {
                    connection.disconnect()
                }
            }
        }
    }
}

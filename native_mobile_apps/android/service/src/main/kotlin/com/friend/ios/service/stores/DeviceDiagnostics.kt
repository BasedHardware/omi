package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.device.PairedDevice
import com.friend.ios.persistence.Preferences
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.TimeZone
import kotlin.math.roundToInt

/** One link event of the Omi, as My Devices › Diagnostics lists it (Flutter `BleDisconnectEvent`). Times in epoch ms. */
@Serializable
data class DiagnosticsEvent(
    val kind: Kind,
    val at: Long,
    /** The Bluetooth stack's wording, when it gave one. */
    val reason: String? = null,
    /** The app let go itself (firmware update, Bluetooth off, forget): not a drop. */
    val manual: Boolean = false,
    /** How long the link had been up (disconnects), seconds. */
    val connectedFor: Double? = null,
    /** Seconds until the Omi was back; null while it is still away, and for failed connects. */
    val reconnectedAfter: Double? = null,
    /** The last signal strength read before it happened. */
    val lastRSSI: Int? = null,
) {
    @Serializable
    enum class Kind(val rawValue: String) {
        /** The link was up and dropped. */
        @SerialName("disconnect")
        Disconnect("disconnect"),

        /** A connect attempt that never established (`fail_to_connect` in Flutter's bundle). */
        @SerialName("fail_to_connect")
        FailedConnect("fail_to_connect"),
    }
}

@Serializable
data class BatteryReading(val at: Long, val level: Int, val charging: Boolean? = null)

data class SignalReading(val at: Long, val rssi: Int)

/** Signal bands of the diagnostics page (Flutter `diagnosticsSignalFor`). */
enum class SignalQuality {
    Excellent, Good, Fair, Weak;

    companion object {
        fun of(rssi: Int): SignalQuality = when {
            rssi >= -60 -> Excellent
            rssi >= -75 -> Good
            rssi >= -85 -> Fair
            else -> Weak
        }
    }
}

/** The "Last 7 days" numbers and verdict (Flutter `summarizeDiagnostics`). Durations in seconds. */
data class DiagnosticsSummary(
    /** Drops that came back on their own. */
    val drops: Int,
    val failed: Int,
    val failedLast24h: Int,
    val medianReconnect: Double?,
    val longestGap: Double?,
    /** Average drops an hour, rounded; null under an hour of history or when it rounds to zero. */
    val dropsPerHour: Int?,
) {
    /** Long gaps are fine (the Omi keeps recording and syncs later); only recent failed connects are trouble. */
    val hasTrouble: Boolean get() = failedLast24h > 0

    companion object {
        fun make(events: List<DiagnosticsEvent>, now: Long, since: Long): DiagnosticsSummary {
            val start = maxOf(since, now - DeviceDiagnosticsLog.RETENTION_MS)
            val window = events.filter { it.at >= start }
            val gaps = window.mapNotNull { if (it.kind == DiagnosticsEvent.Kind.Disconnect && !it.manual) it.reconnectedAfter else null }.sorted()
            val median = if (gaps.isEmpty()) {
                null
            } else {
                val mid = gaps.size / 2
                if (gaps.size % 2 == 0) (gaps[mid - 1] + gaps[mid]) / 2 else gaps[mid]
            }
            val hours = (now - start) / 3_600_000.0
            val perHour = if (hours >= 1 && gaps.isNotEmpty()) (gaps.size / hours).roundToInt() else 0
            val failed = window.filter { it.kind == DiagnosticsEvent.Kind.FailedConnect }
            return DiagnosticsSummary(
                drops = gaps.size,
                failed = failed.size,
                failedLast24h = failed.count { it.at >= now - 24 * 3_600_000L },
                medianReconnect = median,
                longestGap = gaps.lastOrNull(),
                dropsPerHour = perHour.takeIf { it > 0 },
            )
        }
    }
}

/**
 * Port of `DeviceDiagnostics.swift`: what the Omi's link did lately (drops, failed connects,
 * battery and signal). Flutter read these from its native BLE layer; here `DeviceStore` records
 * them as events arrive. Kept for 7 days (signal only while the app runs), cleared when the Omi is
 * forgotten.
 */
class DeviceDiagnosticsLog(private val preferences: Preferences, private val now: () -> Long = System::currentTimeMillis) {
    var connectedAt: Long? by mutableStateOf(null)
        private set
    var events: List<DiagnosticsEvent> by mutableStateOf(emptyList())
        private set
    var battery: List<BatteryReading> by mutableStateOf(emptyList())
        private set
    var signal: List<SignalReading> by mutableStateOf(emptyList())
        private set

    /** When counting started (first record after pairing). */
    var since: Long by mutableStateOf(0L)
        private set

    @Serializable
    private data class Stored(val since: Long, val events: List<DiagnosticsEvent>, val battery: List<BatteryReading>)

    init {
        val stored = preferences.string(Preferences.NativeKey.DeviceDiagnostics)
            ?.let { runCatching { json.decodeFromString(Stored.serializer(), it) }.getOrNull() }
        since = stored?.since ?: now()
        events = stored?.events.orEmpty()
        battery = stored?.battery.orEmpty()
        prune()
    }

    val summary: DiagnosticsSummary get() = DiagnosticsSummary.make(events, now(), since)

    /** The disconnects and failed connects worth showing, newest first. */
    val recent: List<DiagnosticsEvent> get() = events.reversed().take(20)

    val latestSignal: Int? get() = signal.lastOrNull()?.rssi

    internal fun connected() {
        val date = now()
        connectedAt = date
        val index = events.indexOfLast { it.kind == DiagnosticsEvent.Kind.Disconnect }
        if (index >= 0 && events[index].reconnectedAfter == null && !events[index].manual) {
            events = events.toMutableList().also { it[index] = it[index].copy(reconnectedAfter = (date - it[index].at) / 1000.0) }
        }
        save()
    }

    /** [wasConnected] false when the attempt itself failed. */
    internal fun disconnected(reason: String?, wasConnected: Boolean, manual: Boolean = false) {
        val date = now()
        events = events + if (wasConnected) {
            DiagnosticsEvent(
                kind = DiagnosticsEvent.Kind.Disconnect, at = date, reason = reason, manual = manual,
                connectedFor = connectedAt?.let { (date - it) / 1000.0 }, lastRSSI = latestSignal,
            )
        } else {
            DiagnosticsEvent(kind = DiagnosticsEvent.Kind.FailedConnect, at = date, reason = reason, manual = manual, lastRSSI = latestSignal)
        }
        connectedAt = null
        prune()
        save()
    }

    internal fun batteryRead(level: Int, charging: Boolean?) {
        val date = now()
        val last = battery.lastOrNull()
        if (last != null && last.level == level && last.charging == charging && date - last.at < BATTERY_EVERY_MS) return
        battery = battery + BatteryReading(date, level, charging)
        prune()
        save()
    }

    internal fun signalRead(rssi: Int) {
        signal = (signal + SignalReading(now(), rssi)).takeLast(MAX_SIGNAL)
    }

    /** Forgetting the Omi starts the history over. */
    internal fun reset() {
        events = emptyList()
        battery = emptyList()
        signal = emptyList()
        connectedAt = null
        since = now()
        preferences.set(Preferences.NativeKey.DeviceDiagnostics, null)
    }

    private fun prune() {
        val cutoff = now() - RETENTION_MS
        events = events.filter { it.at >= cutoff }.takeLast(MAX_EVENTS)
        battery = battery.filter { it.at >= cutoff }
    }

    private fun save() {
        preferences.set(Preferences.NativeKey.DeviceDiagnostics, json.encodeToString(Stored.serializer(), Stored(since, events, battery)))
    }

    // MARK: Support bundle

    /** What the phone and app are, for the bundle. */
    data class Environment(val appVersion: String, val appBuild: String, val osVersion: String, val phoneModel: String)

    /**
     * The JSON Flutter's "Share" and "Send to support" produce (schema 2, the backend checks it).
     * Firmware diagnostics and BLE logs came from Flutter's native layer and stay empty here.
     */
    fun bundle(device: PairedDevice?, battery: Int?, charging: Boolean?, environment: Environment): ByteArray {
        val date = now()
        val windowStart = maxOf(since, date - RETENTION_MS)
        val window = events.filter { it.at >= windowStart }
        fun n(value: Number?): JsonElement = value?.let { JsonPrimitive(it) } ?: JsonNull
        fun s(value: String?): JsonElement = value?.let { JsonPrimitive(it) } ?: JsonNull
        fun b(value: Boolean?): JsonElement = value?.let { JsonPrimitive(it) } ?: JsonNull
        val reconnections = events.count { it.kind == DiagnosticsEvent.Kind.Disconnect && it.reconnectedAfter != null }
        val fields = sortedMapOf<String, JsonElement>(
            "schema_version" to JsonPrimitive(2),
            "device_id" to JsonPrimitive(device?.id ?: ""),
            "exported_at" to JsonPrimitive(DateTimeFormatter.ISO_INSTANT.format(Instant.ofEpochMilli(date).atOffset(ZoneOffset.UTC).withNano(0))),
            "app_version" to JsonPrimitive(environment.appVersion),
            "app_build" to JsonPrimitive(environment.appBuild),
            "platform" to JsonPrimitive("android"),
            "os_version" to JsonPrimitive(environment.osVersion),
            "phone_model" to JsonPrimitive(environment.phoneModel),
            "timezone_offset_minutes" to JsonPrimitive(TimeZone.getDefault().getOffset(date) / 60_000),
            "connected_at" to JsonPrimitive(connectedAt ?: 0),
            "reconnection_count" to JsonPrimitive(reconnections),
            "fail_to_connect_count" to JsonPrimitive(events.count { it.kind == DiagnosticsEvent.Kind.FailedConnect }),
            "counters_since" to JsonObject(sortedMapOf("fail_to_connect_count" to JsonPrimitive(since), "reconnection_count" to JsonPrimitive(since))),
            "reconnection_count_window" to JsonPrimitive(window.count { it.kind == DiagnosticsEvent.Kind.Disconnect && (it.reconnectedAfter ?: 0.0) > 0 }),
            "fail_to_connect_count_window" to JsonPrimitive(window.count { it.kind == DiagnosticsEvent.Kind.FailedConnect }),
            "rssi_samples" to JsonArray(signal.map { JsonObject(sortedMapOf("rssi" to JsonPrimitive(it.rssi), "ts" to JsonPrimitive(it.at))) }),
            "battery_history" to JsonArray(
                this.battery.map { JsonObject(sortedMapOf("charging" to b(it.charging), "level" to JsonPrimitive(it.level), "ts" to JsonPrimitive(it.at))) },
            ),
            "disconnect_history" to JsonArray(
                events.map { event ->
                    JsonObject(
                        sortedMapOf(
                            "ts" to JsonPrimitive(event.at),
                            "reason" to s(event.reason),
                            "code" to JsonNull,
                            "manual" to JsonPrimitive(event.manual),
                            "event_type" to JsonPrimitive(event.kind.rawValue),
                            "last_rssi" to n(event.lastRSSI),
                            "connection_duration_ms" to n(event.connectedFor?.let { (it * 1000).toLong() }),
                            "time_to_reconnect_ms" to JsonPrimitive(event.reconnectedAfter?.let { (it * 1000).toLong() } ?: 0),
                        ),
                    )
                },
            ),
            "firmware_diagnostics" to JsonArray(emptyList()),
            "lifecycle_events" to JsonArray(emptyList()),
            "ble_log" to JsonArray(emptyList()),
            "device_model" to s(device?.modelNumber),
            "hardware_revision" to s(device?.hardwareRevision),
            "firmware" to s(device?.firmwareRevision),
            "battery" to n(battery),
            "charging" to b(charging),
        )
        return prettyJson.encodeToString(JsonObject.serializer(), JsonObject(fields)).toByteArray()
    }

    companion object {
        const val RETENTION_MS = 7L * 24 * 3_600_000
        const val MAX_EVENTS = 300
        const val MAX_SIGNAL = 120

        /** One battery reading a quarter hour unless the level or charging changes. */
        const val BATTERY_EVERY_MS = 15L * 60_000
        private val json = Json { ignoreUnknownKeys = true }
        private val prettyJson = Json { prettyPrint = true }
    }
}

package com.friend.ios.service

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.persistence.Preferences
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.UUID

/**
 * Port of `DebugLog.swift`: what capture, transcription and sync did, for Settings > Developer and
 * the transcription log. The last entries stay in memory; with [writesToFile] they also go to a
 * daily JSON-lines file (`omi_debug_YYYYMMDD.log`, Flutter's `debug_log_manager.dart` format) that
 * can be shared. On Android the files live in the app's own files directory.
 */
class DebugLog(
    private val preferences: Preferences?,
    private val directory: File,
    private val capacity: Int = 300,
    private val clock: () -> Instant = Instant::now,
    private val zone: ZoneId = ZoneId.systemDefault(),
) {
    data class Entry(
        val id: String,
        val date: Instant,
        val level: Level,
        /** `stt` (the transcription socket), `capture`, `sync` ... */
        val source: String,
        val message: String,
    ) {
        enum class Level(val rawValue: String) { Info("INFO"), Warning("WARN"), Error("ERROR") }
    }

    /** Newest last, at most [capacity]. */
    var entries: List<Entry> by mutableStateOf(emptyList())
        private set

    private var toFile by mutableStateOf(preferences?.bool(Preferences.Key.DevLogsToFileEnabled, false) ?: false)

    /** Kept in `devLogsToFileEnabled`, which survives sign-out (as in Flutter). */
    var writesToFile: Boolean
        get() = toFile
        set(value) {
            toFile = value
            preferences?.set(Preferences.Key.DevLogsToFileEnabled, value)
            filesChanged++
        }

    /** Bumped when files appear or go, so [files] is read again by the screens. */
    private var filesChanged by mutableStateOf(0)

    init {
        directory.mkdirs()
        removeOldFiles()
    }

    /** Files older than three days go (Flutter keeps the same). */
    private fun removeOldFiles() {
        val cutoff = clock().minusSeconds(3 * 86_400L).toEpochMilli()
        for (file in files) {
            if (file.lastModified() < cutoff) file.delete()
        }
    }

    fun add(level: Entry.Level = Entry.Level.Info, source: String, message: String) {
        val entry = Entry(UUID.randomUUID().toString(), clock(), level, source, message)
        entries = (entries + entry).takeLast(capacity)
        if (writesToFile) append(entry)
    }

    fun entries(source: String): List<Entry> = entries.filter { it.source == source }

    /** Log files on disk, newest first (only while writing to a file is or was on). */
    val files: List<File>
        get() {
            @Suppress("UNUSED_VARIABLE") val observed = filesChanged
            val names = directory.list()?.toList().orEmpty()
            return names.filter { it.startsWith("omi_debug_") && it.endsWith(".log") }.sortedDescending().map { File(directory, it) }
        }

    /** Empties the memory and deletes the files. */
    fun clear() {
        entries = emptyList()
        for (file in files) file.delete()
        filesChanged++
    }

    private fun append(entry: Entry) {
        val day = DateTimeFormatter.ofPattern("yyyyMMdd").withZone(zone).format(entry.date)
        val file = File(directory, "omi_debug_$day.log")
        val existed = file.exists()
        val line = buildJsonObject {
            put("level", JsonPrimitive(entry.level.rawValue))
            put("message", JsonPrimitive("[${entry.source}] ${entry.message}"))
            put("ts", JsonPrimitive(DateTimeFormatter.ISO_INSTANT.format(entry.date.truncatedTo(ChronoUnit.SECONDS))))
        }
        if (file.length() > MAX_FILE_BYTES) file.delete()
        runCatching { file.appendText("$line\n") }
        if (!existed) filesChanged++
    }

    companion object {
        const val MAX_FILE_BYTES = 5_000_000L

        /** One line per entry, oldest first: `[LEVEL] HH:mm:ss [source] message` (Flutter's copy format). */
        fun text(entries: List<Entry>, zone: ZoneId = ZoneId.systemDefault()): String {
            val time = DateTimeFormatter.ofPattern("HH:mm:ss").withZone(zone)
            return entries.joinToString("\n") { "[${it.level.rawValue}] ${time.format(it.date)} [${it.source}] ${it.message}" }
        }

        /** `Documents` on iOS: the app's own files directory, where the share sheet can reach it. */
        fun defaultDirectory(filesDir: File): File = File(filesDir, "logs")
    }
}

/** `@Environment(DebugLog.self)`: provided once by the app's `AppEnvironment`. */
val LocalDebugLog = androidx.compose.runtime.staticCompositionLocalOf<DebugLog> { error("DebugLog not provided") }

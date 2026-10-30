package com.friend.ios.service

import com.friend.ios.persistence.Preferences
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files
import java.time.Instant
import java.time.ZoneOffset

/** `DeveloperStoreTests.logKeepsTheNewestEntriesAndFormatsThem` and the file format. */
class DebugLogTest {
    @Test fun logKeepsTheNewestEntriesAndFormatsThem() {
        val directory = Files.createTempDirectory("log").toFile()
        val prefs = freshPreferences()
        val log = DebugLog(prefs, directory, capacity = 3)
        log.writesToFile = true
        for (index in 1..5) {
            log.add(DebugLog.Entry.Level.Info, if (index % 2 == 0) "stt" else "sync", "event $index")
        }
        assertEquals(listOf("event 3", "event 4", "event 5"), log.entries.map { it.message })
        assertEquals(listOf("event 4"), log.entries("stt").map { it.message })
        assertTrue(DebugLog.text(log.entries("stt")).contains("[INFO]"))
        assertEquals(1, log.files.size)
        assertTrue(prefs.bool(Preferences.Key.DevLogsToFileEnabled))
        log.clear()
        assertTrue(log.files.isEmpty() && log.entries.isEmpty())
    }

    @Test fun writesFlutterJsonLinesPerDay() {
        val directory = Files.createTempDirectory("log").toFile()
        val log = DebugLog(null, directory, clock = { Instant.parse("2026-10-14T08:30:05.250Z") }, zone = ZoneOffset.UTC)
        log.add(DebugLog.Entry.Level.Info, "stt", "not on file")
        log.writesToFile = true
        log.add(DebugLog.Entry.Level.Warning, "stt", "say \"hi\"")
        val file = log.files.single()
        assertEquals("omi_debug_20261014.log", file.name)
        assertEquals("{\"level\":\"WARN\",\"message\":\"[stt] say \\\"hi\\\"\",\"ts\":\"2026-10-14T08:30:05Z\"}\n", file.readText())
        assertEquals("[WARN] 08:30:05 [stt] say \"hi\"", DebugLog.text(log.entries.takeLast(1), ZoneOffset.UTC))
    }
}

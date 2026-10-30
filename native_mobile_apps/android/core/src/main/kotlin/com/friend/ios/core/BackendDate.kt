package com.friend.ios.core

import java.time.Instant
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter

/**
 * Port of `BackendDate.swift`: parses the backend's ISO-8601 timestamps. Python emits
 * microseconds and sometimes no zone (`2026-07-18T20:30:00.123456`); those are read as UTC.
 */
object BackendDate {
    fun parse(value: String?): Instant? {
        if (value.isNullOrEmpty()) return null
        for (candidate in listOf(value, value + "Z")) {
            runCatching { return OffsetDateTime.parse(candidate, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant() }
        }
        return null
    }

    /** `distantPast`. */
    val distantPast: Instant = Instant.parse("0001-01-01T00:00:00Z")
}

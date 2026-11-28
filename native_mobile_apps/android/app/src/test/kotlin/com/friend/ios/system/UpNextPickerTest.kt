package com.friend.ios.system

import com.friend.ios.system.widgets.UpNextPicker
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant

/** `UpNextPickerTests.swift`: dated tasks soonest first, then undated ones, open ones only. */
class UpNextPickerTest {
    @Test fun picksDatedSoonestFirstThenUndated() {
        val now = Instant.parse("2026-10-08T10:00:00Z")
        val snapshot = UpNextPicker.snapshot(
            listOf(
                UpNextPicker.Candidate("a", "Later", now.plusSeconds(7200), true),
                UpNextPicker.Candidate("b", "No date", null, true),
                UpNextPicker.Candidate("c", "Overdue", now.minusSeconds(60), true),
                UpNextPicker.Candidate("d", "Done", now, false),
                UpNextPicker.Candidate("e", "  ", null, true),
                UpNextPicker.Candidate("f", " Second undated ", null, true),
            ),
        )
        assertEquals(listOf("c", "a", "b"), snapshot.tasks.map { it.id })
        assertEquals(4, snapshot.open)
        assertEquals("Overdue", snapshot.tasks.first().title)
    }
}

package com.friend.ios.system

import com.friend.ios.system.LiveActivity.CaptureStatus
import com.friend.ios.system.LiveActivity.Phase
import com.friend.ios.system.LiveActivity.Source
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** `OmiExtrasTests.swift` (the Live Activity part): the clock, the throttle, routine changes. */
class LiveActivityTest {
    private val start = 1_790_000_000_000L

    private fun run(step: String, phase: Phase = Phase.Working) =
        LiveActivity.Run.of("run", phase, start, "Find a dentist", step, others = 0, nowMillis = start)

    @Test fun onlyNewStepsWaitForTheThrottle() {
        assertTrue(run("Searching the web").isRoutineChange(run("Reading results")))
        assertFalse(run("Done", Phase.Finished).isRoutineChange(run("Reading results")))
        assertFalse(run("Same").isRoutineChange(run("Same")))
    }

    @Test fun stoppedRecordingsFreezeTheirClock() {
        assertNull(LiveActivity.Capture.of("rec", start, Source.Omi, CaptureStatus.Listening, elapsedSeconds = 12).elapsedSeconds)
        assertEquals(75, LiveActivity.Capture.of("rec", start, Source.Omi, CaptureStatus.Paused, elapsedSeconds = 75).elapsedSeconds)
        assertEquals(0, LiveActivity.Capture.of("rec", start, Source.Omi, CaptureStatus.Paused, elapsedSeconds = null).elapsedSeconds)
        // A finished run's clock stops at the end.
        assertEquals(9, LiveActivity.Run.of("run", Phase.Finished, start, "t", "", 0, nowMillis = start + 9_000).elapsedSeconds)
        assertNull(LiveActivity.Run.of("run", Phase.Working, start, "t", "", 0, nowMillis = start + 9_000).elapsedSeconds)
    }

    @Test fun theWatchCannotPause() {
        assertTrue(LiveActivity.Capture.of("rec", start, Source.Omi, CaptureStatus.Listening, null).canPause)
        assertTrue(LiveActivity.Capture.of("rec", start, Source.Phone, CaptureStatus.Listening, null).canPause)
        assertFalse(LiveActivity.Capture.of("rec", start, Source.Watch, CaptureStatus.Listening, null).canPause)
    }

    @Test fun pausedTimeIsLeftOffTheClock() {
        val clock = CapturePauseClock()
        assertEquals(start to null, clock.observe(since = start, paused = false, now = start + 10_000))
        val stopped = clock.observe(since = start, paused = true, now = start + 60_000)
        assertEquals(start to 60, stopped)
        // Still stopped later: the frozen value holds.
        assertEquals(60, clock.observe(since = start, paused = true, now = start + 90_000).second)
        val resumed = clock.observe(since = start, paused = false, now = start + 100_000)
        assertEquals(start + 40_000 to null, resumed)
        // A new recording starts over.
        val next = start + 1_000_000
        assertEquals(next to null, clock.observe(since = next, paused = false, now = next))
    }

    @Test fun throttleSpacesRoutineUpdates() {
        val throttle = ActivityUpdateThrottle(intervalMillis = 4_000, floorMillis = 1_000)
        assertNull(throttle.decide(urgent = false, atMillis = start))
        throttle.didSend(start)
        assertEquals(2_500L, throttle.decide(urgent = false, atMillis = start + 1_500))
        assertNull(throttle.decide(urgent = false, atMillis = start + 4_000))
    }

    @Test fun urgentUpdatesOnlyMergeBursts() {
        val throttle = ActivityUpdateThrottle(intervalMillis = 4_000, floorMillis = 1_000)
        throttle.didSend(start)
        assertEquals(750L, throttle.decide(urgent = true, atMillis = start + 250))
        assertNull(throttle.decide(urgent = true, atMillis = start + 1_000))
        throttle.reset()
        assertNull(throttle.decide(urgent = false, atMillis = start))
    }

    @Test fun theCardKeepsToItsSize() {
        val long = LiveActivity.Run.of("run", Phase.Working, start, "t".repeat(300), "s".repeat(300), others = -2, nowMillis = start)
        assertEquals(120, long.title.length)
        assertEquals(80, long.step.length)
        assertEquals(0, long.otherRuns)
    }
}

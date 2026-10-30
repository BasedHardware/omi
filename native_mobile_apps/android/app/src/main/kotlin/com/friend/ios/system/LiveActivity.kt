package com.friend.ios.system

/**
 * Port of `OmiActivity.swift` (OmiExtras) for Android's ongoing notifications, which stand in for
 * the iOS Live Activities: what a recording's card and a run's card show, the paused time a
 * recording's clock leaves off, and the update budget. Times are epoch milliseconds.
 */
object LiveActivity {
    /** What the recording does with its audio (Flutter's `status`). */
    enum class CaptureStatus {
        /** Streamed and transcribed live. */
        Listening,
        /** Saved on the phone and transcribed later (Transcribe later, or the connection dropped). */
        Recording,
        /** Stopped by the user; the conversation stays open until Start or End. */
        Paused,
    }

    enum class Source { Omi, Phone, Watch }

    /** A run's card: Omi works on a task, finished it, or could not. */
    enum class Phase { Working, Finished, Failed }

    /**
     * A recording's card. [isStale]: the recording needs the app in front to carry on (iOS: the
     * card Omi stopped refreshing); it says so and drops its buttons.
     */
    data class Capture(
        val id: String,
        val startedAtMillis: Long,
        val elapsedSeconds: Int?,
        val source: Source,
        val status: CaptureStatus,
        val canPause: Boolean,
        val isStale: Boolean = false,
    ) {
        companion object {
            /** `ContentState.capture`: the clock freezes while stopped. */
            fun of(id: String, startedAtMillis: Long, source: Source, status: CaptureStatus, elapsedSeconds: Int?, isStale: Boolean = false) =
                Capture(
                    id = id, startedAtMillis = startedAtMillis,
                    elapsedSeconds = if (status == CaptureStatus.Paused) maxOf(0, elapsedSeconds ?: 0) else null,
                    source = source, status = status, canPause = source != Source.Watch, isStale = isStale,
                )
        }
    }

    /** A run's card: the task's title and the agent's current step ("Searching the web"). */
    data class Run(
        val id: String,
        val phase: Phase,
        val startedAtMillis: Long,
        /** The clock's frozen value once the run ended; null while it works. */
        val elapsedSeconds: Int?,
        val title: String,
        val step: String,
        /** Other runs still going besides the one shown. */
        val otherRuns: Int,
    ) {
        /**
         * Only the agent's step moved on: such updates wait for the throttle; everything else (a
         * phase, the title) goes out at once.
         */
        fun isRoutineChange(old: Run): Boolean = old.copy(step = step) == this && step != old.step

        companion object {
            /** `ExtrasBridge.state(for:phase:others:)`: the title and step are cut to the card's size. */
            fun of(id: String, phase: Phase, startedAtMillis: Long, title: String, step: String, others: Int, nowMillis: Long) = Run(
                id = id, phase = phase, startedAtMillis = startedAtMillis,
                // A finished run's clock stops at the end.
                elapsedSeconds = if (phase == Phase.Working) null else maxOf(0, ((nowMillis - startedAtMillis) / 1000).toInt()),
                title = title.take(120), step = step.take(80), otherRuns = maxOf(0, others),
            )
        }
    }

    /** How long a finished run stays on the lock screen. */
    const val FINISHED_LINGER_MILLIS = 5 * 60 * 1000L
}

/**
 * Port of `ActivityUpdateThrottle`: routine changes (an agent's step) go out at most every
 * [intervalMillis]; urgent ones (a phase) after a short [floorMillis] that only merges bursts.
 * The caller sends on `null` and asks again after the returned wait.
 */
class ActivityUpdateThrottle(val intervalMillis: Long = 4_000, val floorMillis: Long = 1_000) {
    var lastSentMillis: Long? = null
        private set

    /** Null: send now. Otherwise the milliseconds to wait. */
    fun decide(urgent: Boolean, atMillis: Long): Long? {
        val last = lastSentMillis ?: return null
        val elapsed = atMillis - last
        val required = if (urgent) floorMillis else intervalMillis
        return if (elapsed >= required) null else required - elapsed
    }

    fun didSend(atMillis: Long) {
        lastSentMillis = atMillis
    }

    fun reset() {
        lastSentMillis = null
    }
}

/**
 * Port of `CapturePauseClock`: the paused time a recording has built up, so its clock skips it
 * (Flutter shifts `startedAt` by the stopped time). Feed it every observed state; it starts over
 * for a new recording.
 */
class CapturePauseClock {
    private var recording: Long? = null
    private var pausedTotal = 0L
    private var pausedAt: Long? = null

    /** The recording's clock start ([since] moved on by the time stopped) and, while stopped, its frozen seconds. */
    fun observe(since: Long, paused: Boolean, now: Long): Pair<Long, Int?> {
        if (recording != since) {
            recording = since
            pausedTotal = 0
            pausedAt = null
        }
        if (paused && pausedAt == null) pausedAt = now
        val stoppedAt = pausedAt
        if (!paused && stoppedAt != null) {
            pausedTotal += maxOf(0, now - stoppedAt)
            pausedAt = null
        }
        val start = since + pausedTotal
        val frozen = pausedAt ?: return start to null
        return start to maxOf(0, ((frozen - start) / 1000).toInt())
    }
}

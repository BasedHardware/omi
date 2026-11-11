package com.friend.ios.batch

/**
 * Process-local emergency deny/allow latch for the short window around a
 * Flutter preference write. It lets a mute take effect before the asynchronous
 * SharedPreferences persistence completes, while revisions prevent an older
 * callback from reopening capture.
 */
internal object CaptureAdmissionLatch {
    internal data class State(val muted: Boolean, val revision: Long)

    private val lock = Any()
    private var state: State? = null

    /** Apply a monotonic revision; the bridge validates durable authorization before release. */
    fun apply(muted: Boolean, revision: Long): Boolean {
        if (revision < 0) return false
        synchronized(lock) {
            val previous = state
            if (previous != null) {
                if (revision < previous.revision) return false
            }
            state = State(muted = muted, revision = revision)
            return true
        }
    }

    fun snapshot(): State? = synchronized(lock) { state }

    /** High-water revision for Dart initialization after a failed native write. */
    fun highWaterRevision(): Long = synchronized(lock) { state?.revision ?: 0L }

    /** Test-only reset; production callers never clear the process latch. */
    internal fun resetForTest() = synchronized(lock) { state = null }
}

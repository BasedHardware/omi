package com.friend.ios.batch

import org.json.JSONObject

/**
 * Persistent authorization for native capture sinks.
 *
 * Flutter writes this as a small, versioned JSON value so native capture can
 * make the same admission decision while the Flutter engine is suspended or
 * gone. A revision is stamped on work admitted by a callback and checked again
 * at the sink boundary; this retires work queued before a policy change.
 */
data class CaptureAdmissionPolicy(
    val muted: Boolean,
    val revision: Long,
) {
    /** Whether work admitted under [admittedRevision] may cross a native sink. */
    fun permits(admittedRevision: Long): Boolean = !muted && revision == admittedRevision

    companion object {
        private const val VERSION = 1L

        /** Read the canonical policy, falling back only when it is absent. */
        fun load(prefs: NativeBlePreferences): CaptureAdmissionPolicy {
            val raw = prefs.string("capturePolicy")
            // A present-but-empty value is canonical input too. Malformed
            // canonical input must not reopen capture through legacy booleans.
            val persisted = if (!prefs.contains("capturePolicy") && raw.isEmpty()) {
                fromLegacy(prefs.boolean("deviceMuted") || prefs.boolean("batchMuted"))
            } else {
                parse(raw) ?: denied()
            }
            val latched = CaptureAdmissionLatch.snapshot()
            // The process latch is a deny-only fast path. An unmuted latch never
            // authorizes bytes beyond durable preferences. A deny stays active until
            // the explicit release command, including while a newer unmute is saving.
            return if (latched?.muted == true) {
                CaptureAdmissionPolicy(muted = true, revision = maxOf(latched.revision, persisted.revision))
            } else {
                persisted
            }
        }

        /** Parse strict wire types. Invalid/unsupported canonical values deny audio. */
        fun parse(raw: String): CaptureAdmissionPolicy? {
            return try {
                val json = JSONObject(raw)
                if (json.length() != 3) return null
                val version = strictLong(json.opt("version")) ?: return null
                val revision = strictLong(json.opt("revision")) ?: return null
                val muted = json.opt("muted") as? Boolean ?: return null
                if (version != VERSION || revision < 0) return null
                CaptureAdmissionPolicy(muted = muted, revision = revision)
            } catch (_: Exception) {
                null
            }
        }

        fun fromLegacy(muted: Boolean): CaptureAdmissionPolicy =
            CaptureAdmissionPolicy(muted = muted, revision = 0)

        fun denied(): CaptureAdmissionPolicy = CaptureAdmissionPolicy(muted = true, revision = 0)

        private fun strictLong(value: Any?): Long? = when (value) {
            is Int -> value.toLong()
            is Long -> value
            else -> null
        }
    }
}

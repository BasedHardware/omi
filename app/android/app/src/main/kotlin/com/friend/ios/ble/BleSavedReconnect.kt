package com.friend.ios.ble

/** Scoped to explicitly saved pairings; scan results never authorize retries. */
internal class BleSavedReconnect {
    private val blocked = mutableSetOf<String>()
    private val enabled = mutableSetOf<String>()
    private val attempts = mutableMapOf<String, Long>()
    private val reported = mutableMapOf<String, MutableSet<String>>()
    private val outages = mutableMapOf<String, Long>()

    @Synchronized fun allow(address: String) { blocked.remove(address.uppercase()) }
    @Synchronized fun block(address: String) {
        setEnabled(address, false)
        blocked.add(address.uppercase())
    }
    @Synchronized fun isBlocked(address: String): Boolean = address.uppercase() in blocked

    @Synchronized fun isEnabled(address: String): Boolean = address.uppercase() in enabled

    @Synchronized fun setEnabled(address: String, value: Boolean) {
        val key = address.uppercase()
        if (value) enabled.add(key) else {
            enabled.remove(key)
            blocked.remove(key)
            reported.remove(key)
            attempts.remove(key)
            outages.remove(key)
        }
    }

    @Synchronized fun event(address: String, result: String, now: Long): Triple<Long, String, Long>? {
        val key = address.uppercase()
        if (key !in enabled || (result != "attempted" && key !in attempts)) return null
        if (result == "attempted") attempts[key] = (attempts[key] ?: 0) + 1
        val start = outages.getOrPut(key) { now }
        val seen = reported.getOrPut(key) { mutableSetOf() }
        if (result in seen || (seen.size >= 7 && result != "connected")) return null
        seen.add(result)
        val event = Triple(attempts[key] ?: 0, result, (now - start).coerceAtLeast(0))
        if (result == "connected") {
            attempts.remove(key)
            outages.remove(key)
            reported.remove(key)
        }
        return event
    }
}

/** Companion callbacks for a superseded association must not revive its old link. */
internal fun matchesManagedDevice(address: String, saved: String?): Boolean =
    saved == null || saved.substringBefore("|").equals(address, ignoreCase = true)

package com.friend.ios.ble

/** Scoped to explicitly saved pairings; scan results never authorize retries. */
internal class BleSavedReconnect {
    private val blocked = mutableSetOf<String>()
    private val enabled = mutableSetOf<String>()
    private val attempts = mutableMapOf<String, Long>()
    private val outages = mutableMapOf<String, Long>()

    @Synchronized fun allow(address: String) { blocked.remove(address.uppercase()) }
    @Synchronized fun block(address: String) {
        blocked.add(address.uppercase())
        setEnabled(address, false)
    }
    @Synchronized fun isBlocked(address: String): Boolean = address.uppercase() in blocked

    @Synchronized fun setEnabled(address: String, value: Boolean) {
        val key = address.uppercase()
        if (value) enabled.add(key) else {
            enabled.remove(key)
            attempts.remove(key)
            outages.remove(key)
        }
    }

    @Synchronized fun event(address: String, result: String, now: Long): Triple<Long, String, Long>? {
        val key = address.uppercase()
        if (key !in enabled || (result != "attempted" && key !in attempts)) return null
        if (result == "attempted") attempts[key] = (attempts[key] ?: 0) + 1
        val start = outages.getOrPut(key) { now }
        val event = Triple(attempts[key] ?: 0, result, (now - start).coerceAtLeast(0))
        if (result == "connected") {
            attempts.remove(key)
            outages.remove(key)
        }
        return event
    }
}

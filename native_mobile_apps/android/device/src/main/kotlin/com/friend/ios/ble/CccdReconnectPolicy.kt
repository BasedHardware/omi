package com.friend.ios.ble

/** Per-device budget; connecting or rebuilding the service does not replenish it. */
internal class CccdReconnectPolicy(
    private val budget: Int,
    private val loadTimeouts: (String) -> Int,
    private val saveTimeouts: (String, Int) -> Boolean,
) {
    private val timeouts = mutableMapOf<String, Int>()

    private fun count(address: String): Int = timeouts.getOrPut(address.uppercase()) {
        val stored = try { loadTimeouts(address.uppercase()) } catch (_: Exception) { budget + 1 }
        if (stored in 0..budget + 1) stored else budget + 1
    }

    fun isExhausted(address: String): Boolean = count(address) > budget

    private fun persist(address: String, count: Int): Boolean =
        try { saveTimeouts(address, count) } catch (_: Exception) { false }

    fun reconnectDelay(address: String, cccdTimeout: Boolean, ordinaryDelayMs: Long): Long? {
        if (!cccdTimeout) return ordinaryDelayMs
        val key = address.uppercase()
        val next = (count(key) + 1).coerceAtMost(budget + 1)
        timeouts[key] = next
        // Spend durably before scheduling radio work. A failed write stops recovery.
        if (!persist(key, next)) {
            timeouts[key] = budget + 1
            return null
        }
        return if (next <= budget) ordinaryDelayMs * (1L shl (next - 1)) else null
    }

    fun onAcknowledged(address: String): Boolean {
        val key = address.uppercase()
        val hadTimeout = count(key) > 0
        if (hadTimeout) {
            timeouts[key] = 0
            persist(key, 0)
        }
        return hadTimeout
    }
}

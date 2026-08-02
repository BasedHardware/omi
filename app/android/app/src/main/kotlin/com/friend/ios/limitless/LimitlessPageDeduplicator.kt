package com.friend.ios.limitless

/**
 * Persists the highest durable page for one device/session. Callers supply the
 * storage seam so the production writer can use synchronous SharedPreferences
 * commits while JVM tests use an in-memory store.
 */
internal class LimitlessPageDeduplicator(
    private val readWatermark: (String) -> Int,
    private val writeWatermark: (String, Int) -> Boolean,
) {
    fun isDurable(identity: String, pageIndex: Int): Boolean = readWatermark(identity) >= pageIndex

    fun appendOnce(
        identity: String,
        pageIndex: Int,
        appendDurably: () -> Boolean,
        rollback: () -> Unit,
    ): Boolean {
        if (isDurable(identity, pageIndex)) return true
        if (!appendDurably()) {
            rollback()
            return false
        }
        if (writeWatermark(identity, pageIndex)) return true
        rollback()
        return false
    }
}

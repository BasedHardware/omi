package com.friend.ios.limitless

/**
 * Owns the cumulative pendant-deletion watermark while a BLE ACK is in flight.
 * A requested page becomes acknowledged only after the transport callback succeeds.
 */
internal class LimitlessAckCommitGate(initialPageIndex: Int) {
    enum class RequestResult { NOOP, STARTED, PENDING, BLOCKED }

    var lastAckedPageIndex: Int = initialPageIndex
        private set
    var inFlight: Boolean = false
        private set
    var blocked: Boolean = false
        private set

    fun request(
        pageIndex: Int,
        durableBarrier: () -> Boolean,
        transmit: (Int, (Boolean) -> Unit) -> Unit,
        settled: (Boolean, Int) -> Unit,
    ): RequestResult {
        if (blocked) return RequestResult.BLOCKED
        if (inFlight) return RequestResult.PENDING
        if (pageIndex <= lastAckedPageIndex) return RequestResult.NOOP
        if (!durableBarrier()) {
            blocked = true
            return RequestResult.BLOCKED
        }

        inFlight = true
        transmit(pageIndex) { success ->
            inFlight = false
            if (success) {
                lastAckedPageIndex = pageIndex
            } else {
                blocked = true
            }
            settled(success, pageIndex)
        }
        return RequestResult.STARTED
    }
}

package com.friend.ios.limitless

/**
 * Orders a Limitless flash drain and exposes only its contiguous, appended
 * prefix as ACK-eligible.
 *
 * The pendant's ACK is cumulative: ACKing page N deletes every page through N.
 * A later page must therefore never move the watermark across a missing page.
 */
internal class ContiguousFlashPageLedger(
    oldestPageIndex: Int,
    val newestPageIndex: Int,
    private val appendPage: (LimitlessProtocol.FlashPage) -> Boolean,
) {
    enum class OfferResult {
        NO_PROGRESS,
        PROGRESSED,
        APPEND_FAILED,
        BUFFER_LIMIT_REACHED,
    }

    companion object {
        private const val MAX_PENDING_PAGES = 64
    }

    private val pendingPages = mutableMapOf<Int, LimitlessProtocol.FlashPage>()
    private var nextPageIndex = oldestPageIndex

    var lastAppendedPageIndex: Int = oldestPageIndex - 1
        private set

    var pagesSinceAck: Int = 0
        private set

    val isComplete: Boolean
        get() = nextPageIndex > newestPageIndex

    internal val pendingPageCount: Int
        get() = pendingPages.size

    fun offer(page: LimitlessProtocol.FlashPage): OfferResult {
        val index = page.index ?: return OfferResult.NO_PROGRESS
        if (index < nextPageIndex || index > newestPageIndex) return OfferResult.NO_PROGRESS

        pendingPages.putIfAbsent(index, page)
        if (pendingPages.size > MAX_PENDING_PAGES) return OfferResult.BUFFER_LIMIT_REACHED

        var progressed = false
        while (true) {
            val nextPage = pendingPages[nextPageIndex] ?: break
            if (!appendPage(nextPage)) return OfferResult.APPEND_FAILED

            pendingPages.remove(nextPageIndex)
            lastAppendedPageIndex = nextPageIndex
            nextPageIndex++
            pagesSinceAck++
            progressed = true
        }

        return if (progressed) OfferResult.PROGRESSED else OfferResult.NO_PROGRESS
    }

    fun markAcked() {
        pagesSinceAck = 0
    }
}

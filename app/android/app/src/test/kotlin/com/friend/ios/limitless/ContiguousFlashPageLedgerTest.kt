package com.friend.ios.limitless

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ContiguousFlashPageLedgerTest {

    private fun page(index: Int) =
        LimitlessProtocol.FlashPage(
            index = index,
            session = 1,
            timestampMs = index.toLong(),
            opusFrames = listOf(byteArrayOf(index.toByte())),
        )

    @Test
    fun laterPageCannotAdvanceAckWatermarkAcrossHole() {
        val appended = mutableListOf<Int>()
        val ledger = ContiguousFlashPageLedger(100, 102) {
            appended += it.index!!
            true
        }

        assertEquals(ContiguousFlashPageLedger.OfferResult.PROGRESSED, ledger.offer(page(100)))
        assertEquals(ContiguousFlashPageLedger.OfferResult.NO_PROGRESS, ledger.offer(page(102)))
        assertEquals(listOf(100), appended)
        assertEquals(100, ledger.lastAppendedPageIndex)
        assertFalse(ledger.isComplete)

        assertEquals(ContiguousFlashPageLedger.OfferResult.PROGRESSED, ledger.offer(page(101)))
        assertEquals(listOf(100, 101, 102), appended)
        assertEquals(102, ledger.lastAppendedPageIndex)
        assertEquals(3, ledger.pagesSinceAck)
        assertTrue(ledger.isComplete)
    }

    @Test
    fun failedAppendDoesNotMakePageAckEligible() {
        val ledger = ContiguousFlashPageLedger(7, 8) { it.index != 8 }

        assertEquals(ContiguousFlashPageLedger.OfferResult.PROGRESSED, ledger.offer(page(7)))
        assertEquals(ContiguousFlashPageLedger.OfferResult.APPEND_FAILED, ledger.offer(page(8)))
        assertEquals(7, ledger.lastAppendedPageIndex)
        assertFalse(ledger.isComplete)
    }

    @Test
    fun duplicatePageIsNotAppendedTwice() {
        val appended = mutableListOf<Int>()
        val ledger = ContiguousFlashPageLedger(4, 5) {
            appended += it.index!!
            true
        }

        ledger.offer(page(4))
        ledger.offer(page(4))

        assertEquals(listOf(4), appended)
        assertEquals(4, ledger.lastAppendedPageIndex)
    }

    @Test
    fun gapBufferIsBounded() {
        val ledger = ContiguousFlashPageLedger(100, 200) { true }

        for (index in 101..164) {
            assertEquals(ContiguousFlashPageLedger.OfferResult.NO_PROGRESS, ledger.offer(page(index)))
        }

        assertEquals(ContiguousFlashPageLedger.OfferResult.BUFFER_LIMIT_REACHED, ledger.offer(page(165)))
        assertEquals(65, ledger.pendingPageCount)
        assertEquals(99, ledger.lastAppendedPageIndex)
    }
}

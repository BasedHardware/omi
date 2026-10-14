package com.friend.ios.service.stores

import com.friend.ios.core.models.ChatMessage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

/**
 * The thread's layout rules: split answers, grouped bubbles, extras, stacks, the bottom, the
 * header. Port of `ChatLayoutTests.swift`.
 */
class ChatBubbleSplitTest {
    @Test
    fun shortAnswersStayOneBubble() {
        assertEquals(listOf("Lunch with Anna at 1."), ChatBubbleSplit.split("Lunch with Anna at 1."))
        assertTrue(ChatBubbleSplit.split("  \n ").isEmpty())
    }

    @Test
    fun paragraphsBecomeBubbles() {
        val text = "First **thing**.\n\nSecond, with a [link](https://omi.me).\n\n\nThird."
        assertEquals(listOf("First **thing**.", "Second, with a [link](https://omi.me).", "Third."), ChatBubbleSplit.split(text))
    }

    @Test
    fun listsTablesAndQuotesStayTogether() {
        val list = "- one\n\n- two\n\n- three"
        assertEquals(listOf("- one\n\n- two\n\n- three"), ChatBubbleSplit.split(list))
        val table = "| a | b |\n|---|---|\n\n| 1 | 2 |"
        assertEquals(1, ChatBubbleSplit.split(table).size)
        val quote = "> Hi Anna,\n\n> see you Thursday."
        assertEquals(1, ChatBubbleSplit.split(quote).size)
    }

    @Test
    fun headingsAndIntrosStayWithWhatFollows() {
        val text = "## Plan\n\nWe start Monday.\n\nHere is what I found:\n\n1. The deck\n2. The notes"
        assertEquals(listOf("## Plan\n\nWe start Monday.", "Here is what I found:\n\n1. The deck\n2. The notes"), ChatBubbleSplit.split(text))
    }

    @Test
    fun codeIsNeverCut() {
        val text = "Run this:\n\n```\nmake build\n\nmake test\n```\n\nDone."
        assertEquals(listOf("Run this:\n\n```\nmake build\n\nmake test\n```", "Done."), ChatBubbleSplit.split(text))
    }

    @Test
    fun atMostFourBubbles() {
        val text = (1..6).joinToString("\n\n") { "Part $it." }
        val parts = ChatBubbleSplit.split(text)
        assertEquals(ChatBubbleSplit.MAX_BUBBLES, parts.size)
        assertEquals("Part 4.\n\nPart 5.\n\nPart 6.", parts.last())
    }

    /** While an answer streams, finished paragraphs keep their bubbles; only the end changes. */
    @Test
    fun streamingOnlyChangesTheEnd() {
        val full = "One.\n\nTwo.\n\nThree is longer."
        val final = ChatBubbleSplit.split(full)
        assertEquals(listOf("One.", "Two.", "Three is longer."), final)
        for (end in full.indices) {
            val parts = ChatBubbleSplit.split(full.substring(0, end + 1))
            assertEquals(final.take(maxOf(0, parts.size - 1)), parts.dropLast(1))
        }
        // A loose list joins its items as they arrive (the bubble before the end grows).
        assertEquals(listOf("One.", "- a\n\n- b"), ChatBubbleSplit.split("One.\n\n- a\n\n- b"))
    }
}

class ChatGroupingTest {
    private val now = Instant.ofEpochSecond(1_000_000)
    private val user = ChatMessage.Sender.User
    private val omi = ChatMessage.Sender.Omi
    private fun at(seconds: Long) = now.plusSeconds(seconds)

    @Test
    fun sameSenderInARowIsOneGroup() {
        val positions = ChatGrouping.positions(
            listOf(
                ChatGrouping.Item("day", null),
                ChatGrouping.Item("q1", user, now),
                ChatGrouping.Item("q2", user, at(30)),
                ChatGrouping.Item("a1", omi, at(40)),
                ChatGrouping.Item("a2", omi, at(50)),
                ChatGrouping.Item("a3", omi, at(60)),
            ),
        )
        assertNull(positions["day"])
        assertEquals(ChatGrouping.Position(isFirst = true, isLast = false), positions["q1"])
        assertEquals(ChatGrouping.Position(isFirst = false, isLast = true), positions["q2"])
        assertEquals(ChatGrouping.Position(isFirst = true, isLast = false), positions["a1"])
        assertEquals(ChatGrouping.Position(isFirst = false, isLast = false), positions["a2"])
        assertEquals(ChatGrouping.Position(isFirst = false, isLast = true), positions["a3"])
    }

    @Test
    fun dayLinesRunsGapsAndExtrasEndAGroup() {
        val gap = ChatGrouping.maxGap.seconds
        val positions = ChatGrouping.positions(
            listOf(
                ChatGrouping.Item("q1", user, now),
                ChatGrouping.Item("run", null),
                ChatGrouping.Item("q2", user, at(10)),
                ChatGrouping.Item("q3", user, at(gap + 60)),
                ChatGrouping.Item("a1", omi, at(gap + 70), endsWithExtras = true),
                ChatGrouping.Item("a2", omi, at(gap + 80)),
                ChatGrouping.Item("a3", omi, at(gap + 90), leadsWithExtras = true),
            ),
        )
        for (id in listOf("q1", "q2", "q3", "a1", "a2", "a3")) {
            assertEquals(id, ChatGrouping.Position.alone, positions[id])
        }
    }
}

class ChatAnswerExtrasTest {
    @Test
    fun theLatestAnswerKeepsItsChipsAndFollowUp() {
        val shown = ChatAnswerExtras.shown(ChatAnswerExtras.Answer(isLatest = true, citations = 2, hasFollowUp = true), draftIsEmpty = true, isSpeaking = false)
        assertEquals(ChatAnswerExtras.Shown(ChatAnswerExtras.Sources.Chips, followUp = true, stopReading = false), shown)
    }

    @Test
    fun olderAnswersFoldTheirSources() {
        val answer = ChatAnswerExtras.Answer(isLatest = false, citations = 2, hasFollowUp = true)
        val older = ChatAnswerExtras.shown(answer, draftIsEmpty = true, isSpeaking = false)
        assertEquals(ChatAnswerExtras.Shown(ChatAnswerExtras.Sources.Collapsed(2), followUp = false, stopReading = false), older)
        val opened = ChatAnswerExtras.shown(answer, draftIsEmpty = true, isSpeaking = false, sourcesExpanded = true)
        assertEquals(ChatAnswerExtras.Sources.Chips, opened.sources)
    }

    @Test
    fun theFollowUpWaitsForTheAnswerAndAnEmptyComposer() {
        fun followUp(streaming: Boolean = false, failed: Boolean = false, draftIsEmpty: Boolean = true): Boolean {
            val answer = ChatAnswerExtras.Answer(isLatest = true, isStreaming = streaming, failed = failed, hasFollowUp = true)
            return ChatAnswerExtras.shown(answer, draftIsEmpty = draftIsEmpty, isSpeaking = false).followUp
        }
        assertTrue(followUp())
        assertFalse(followUp(streaming = true))
        assertFalse(followUp(failed = true))
        assertFalse(followUp(draftIsEmpty = false))
    }

    @Test
    fun stopReadingOnlyWhileSpeaking() {
        val older = ChatAnswerExtras.Answer(isLatest = false)
        assertTrue(ChatAnswerExtras.shown(older, draftIsEmpty = true, isSpeaking = false).isEmpty)
        assertTrue(ChatAnswerExtras.shown(older, draftIsEmpty = true, isSpeaking = true).stopReading)
        val failed = ChatAnswerExtras.Answer(isLatest = true, failed = true, citations = 3, hasFollowUp = true)
        assertEquals(ChatAnswerExtras.Sources.None, ChatAnswerExtras.shown(failed, draftIsEmpty = true, isSpeaking = false).sources)
    }
}

class ChatStackingTest {
    @Test
    fun cardsOfAKindInARowStack() {
        val cards = listOf(
            ChatCard.Connect("gmail"), ChatCard.Connect("google_calendar"),
            ChatCard.TaskAdded("1", "A"), ChatCard.TaskAdded("2", "B"), ChatCard.TaskAdded("3", "C"),
            ChatCard.TaskCompleted("4", "D"), ChatCard.TaskAdded("5", "E"),
        )
        val stacks = ChatStacking.stacks(cards) { it.kind }
        assertEquals(listOf(2, 3, 1, 1), stacks.map { it.size })
        assertTrue(ChatStacking.stacks(emptyList<Int>()) { it.toString() }.isEmpty())
    }
}

class ChatBottomTrackerTest {
    @Test
    fun atTheBottomWithinTheThreshold() {
        // 1000 pt of content in a 600 pt list with a 100 pt composer: the end is at offset 500.
        assertTrue(ChatBottomTracker.isAtBottom(offsetY = 500.0, containerHeight = 600.0, bottomInset = 100.0, contentHeight = 1000.0))
        assertTrue(ChatBottomTracker.isAtBottom(offsetY = 421.0, containerHeight = 600.0, bottomInset = 100.0, contentHeight = 1000.0))
        assertFalse(ChatBottomTracker.isAtBottom(offsetY = 419.0, containerHeight = 600.0, bottomInset = 100.0, contentHeight = 1000.0))
        // A fling that bounces past the end still counts.
        assertTrue(ChatBottomTracker.isAtBottom(offsetY = 540.0, containerHeight = 600.0, bottomInset = 100.0, contentHeight = 1000.0))
    }

    @Test
    fun onlyTheUsersScrollLeavesTheBottom() {
        val tracker = ChatBottomTracker()
        // A growing answer (no scrolling) pushes the end away: still following.
        tracker.geometryChanged(atBottom = false)
        assertTrue(tracker.isAtBottom)
        // The user drags up: no longer at the bottom.
        tracker.phaseChanged(isIdle = false)
        tracker.geometryChanged(atBottom = false)
        tracker.phaseChanged(isIdle = true)
        assertFalse(tracker.isAtBottom)
    }

    /** The bug the arrow had: scrolled back down by hand, it stayed. Coming to rest at the end clears it. */
    @Test
    fun scrollingBackDownClearsTheArrow() {
        val tracker = ChatBottomTracker()
        tracker.phaseChanged(isIdle = false)
        tracker.geometryChanged(atBottom = false)
        tracker.phaseChanged(isIdle = true)
        assertFalse(tracker.isAtBottom)
        // Back down: the last geometry update during the drag may still say "not yet"; it ends at the bottom.
        tracker.phaseChanged(isIdle = false)
        tracker.geometryChanged(atBottom = false)
        tracker.geometryChanged(atBottom = true)
        assertTrue(tracker.isAtBottom)
        tracker.phaseChanged(isIdle = true)
        assertTrue(tracker.isAtBottom)
    }

    /** A fling that ends at the end while the geometry settles after the phase: resting there counts. */
    @Test
    fun reachingTheEndWhileIdleCounts() {
        val tracker = ChatBottomTracker()
        tracker.phaseChanged(isIdle = false)
        tracker.geometryChanged(atBottom = false)
        tracker.phaseChanged(isIdle = true)
        tracker.geometryChanged(atBottom = true)
        assertTrue(tracker.isAtBottom)
    }

    @Test
    fun jumpingGoesBackToFollowing() {
        val tracker = ChatBottomTracker()
        tracker.phaseChanged(isIdle = false)
        tracker.geometryChanged(atBottom = false)
        tracker.phaseChanged(isIdle = true)
        tracker.jumpedToBottom()
        assertTrue(tracker.isAtBottom)
        // The answer growing right after the jump does not bring the arrow back.
        tracker.geometryChanged(atBottom = false)
        assertTrue(tracker.isAtBottom)
    }
}

package com.friend.ios.service.stores

import com.friend.ios.core.models.ChatBlock
import com.friend.ios.core.models.ChatMemoryReview
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.ChatQuestion
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

/**
 * How a turn's blocks sit against its body. Fixtures only: the cards themselves are proved on
 * screen, these are the rules underneath them. Port of `ChatBlockLayoutTests.swift`.
 */
class ChatBlockLayoutTest {
    private fun message(
        text: String,
        blocks: List<ChatBlock>,
        kind: ChatMessage.Kind = ChatMessage.Kind.Text,
    ) = ChatMessage(
        id = "m1", text = text, sender = ChatMessage.Sender.Omi, createdAt = Instant.now(),
        blocks = blocks, kind = kind,
    )

    @Test
    fun aCardPerActableKind() {
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.Task("t")))
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.Goal("g", "s")))
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.Memory("m", "s")))
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.Conversation("c", "s", emptyList(), isCapture = false)))
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.Discovery("t", "s", "f")))
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.Question(ChatQuestion("q", "?", emptyList(), null))))
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.AgentRun("t", "d", ChatBlock.AgentRunStatus.Running)))
        assertTrue(ChatBlockLayout.isRenderable(ChatBlock.Kind.MemoryReview(ChatMemoryReview("s", "2026-10-12", emptyList()))))
        // A type this client does not draw is not a card, and neither is a plain text block.
        assertFalse(ChatBlockLayout.isRenderable(ChatBlock.Kind.Text("hello")))
        assertFalse(ChatBlockLayout.isRenderable(ChatBlock.Kind.Other("quantumLeap")))
    }

    @Test
    fun cardsReplaceABodyThatWasOnlyTheirFallback() {
        val block = ChatBlock("b1", ChatBlock.Kind.Task("t1"), "Buy milk")
        assertTrue(ChatBlockLayout.blocksReplaceBody(message("Buy milk", listOf(block))))
        // Whitespace differences are the same body.
        assertTrue(ChatBlockLayout.blocksReplaceBody(message("  Buy\n milk ", listOf(block))))
        // An empty body has nothing of its own to keep.
        assertTrue(ChatBlockLayout.blocksReplaceBody(message("", listOf(block))))
    }

    @Test
    fun aBodyOfItsOwnStays() {
        val block = ChatBlock("b1", ChatBlock.Kind.Task("t1"), "Buy milk")
        assertFalse(ChatBlockLayout.blocksReplaceBody(message("I added that to your list.", listOf(block))))
        assertFalse(ChatBlockLayout.blocksReplaceBody(message("Buy milk and eggs", listOf(block))))
    }

    @Test
    fun aTextOnlyTurnIsUntouched() {
        val text = ChatBlock("b1", ChatBlock.Kind.Text("Hello there"), "Hello there")
        assertFalse(ChatBlockLayout.blocksReplaceBody(message("Hello there", listOf(text))))
        assertFalse(ChatBlockLayout.blocksReplaceBody(message("Nothing at all", emptyList())))
    }

    @Test
    fun aDaySummaryKeepsItsBody() {
        val block = ChatBlock("b1", ChatBlock.Kind.Task("t1"), "Buy milk")
        assertFalse(ChatBlockLayout.blocksReplaceBody(message("Buy milk", listOf(block), ChatMessage.Kind.DaySummary)))
    }

    /** The review card is chrome: a turn that is only a review card is no body to replace. */
    @Test
    fun aReviewCardNeverReplacesTheBody() {
        val review = ChatBlock(
            "b1",
            ChatBlock.Kind.MemoryReview(ChatMemoryReview("s", "2026-10-12", emptyList())),
            "Things I learned today",
        )
        assertFalse(ChatBlockLayout.blocksReplaceBody(message("Things I learned today", listOf(review))))
        assertFalse(ChatBlockLayout.blocksReplaceBody(message("", listOf(review))))
        // Beside a card that does carry the turn, the review card no longer blocks the replacement.
        val task = ChatBlock("b2", ChatBlock.Kind.Task("t1"), "Buy milk")
        assertTrue(ChatBlockLayout.blocksReplaceBody(message("Buy milk\nThings I learned today", listOf(task, review))))
    }

    /** The lines a card cannot draw stay readable when the cards took the body away. */
    @Test
    fun linesWithoutACardSurviveABodyReplacement() {
        val thinking = ChatBlock("b1", ChatBlock.Kind.Other("thinking"), "Thinking about it")
        val task = ChatBlock("b2", ChatBlock.Kind.Task("t1"), "Buy milk")
        val blocks = listOf(thinking, task, ChatBlock("b3", ChatBlock.Kind.Text("  "), "   "))
        assertEquals(listOf("Thinking about it"), ChatBlockLayout.fallbackLines(blocks))
        assertEquals("Thinking about it\nBuy milk", ChatBlockLayout.structuredFallback(blocks))
    }

    @Test
    fun hasRenderableSeesOnlyCards() {
        assertTrue(ChatBlockLayout.hasRenderable(listOf(ChatBlock("b", ChatBlock.Kind.Goal("g", "s"), ""))))
        assertFalse(ChatBlockLayout.hasRenderable(listOf(ChatBlock("b", ChatBlock.Kind.Other("thinking"), "Thinking"))))
        assertFalse(ChatBlockLayout.hasRenderable(emptyList()))
    }
}

/** The day summary's list, as Flutter `DaySummaryWidget.splitMessage` reads it. */
class ChatDaySummaryTest {
    @Test
    fun aNumberedListLosesItsNumbers() {
        val text = "1. Walked with Anna\n2. Finished the deck\n3. Booked the flight"
        assertEquals(
            listOf("Walked with Anna", "Finished the deck", "Booked the flight"),
            ChatDaySummary.items(text),
        )
    }

    @Test
    fun proseSplitsAtSentenceEnds() {
        assertEquals(listOf("Swam at the lake", "Finished the deck"), ChatDaySummary.items("Swam at the lake. Finished the deck."))
        assertEquals(listOf("One thing happened"), ChatDaySummary.items("One thing happened"))
        assertEquals(listOf("Done"), ChatDaySummary.items("Done."))
    }

    @Test
    fun nothingInNothingOut() {
        assertTrue(ChatDaySummary.items("").isEmpty())
        assertTrue(ChatDaySummary.items("  \n ").isEmpty())
    }
}

package com.friend.ios.network.endpoints

import com.friend.ios.core.models.ChatBlock
import com.friend.ios.core.models.ChatMemoryReview
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.ChatQuestion
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * `content_blocks` as they arrive: two dialects, a JSON string on a push, and every kind of damage a
 * single block can carry (a missing field, an unknown type, a whole block absent). Port of
 * `ChatBlockMapperTests.swift`.
 */
class ChatBlockMapperTest {
    private fun blocks(json: String): List<ChatBlock> = ChatBlockMapper.blocks(Json.parseToJsonElement(json))

    private fun blocksOf(json: String): ChatBlock? = ChatBlockMapper.block(Json.parseToJsonElement(json) as JsonObject)

    private fun fallback(json: String): String = ChatBlockMapper.fallbackText(Json.parseToJsonElement(json) as JsonObject)

    @Test
    fun aTaskCardReadsInBothDialects() {
        val camel = blocks("""[{"id":"b1","type":"taskCard","taskId":"t1"}]""").first()
        assertEquals("b1", camel.id)
        assertEquals(ChatBlock.Kind.Task("t1"), camel.kind)

        val snake = blocks("""[{"id":"b2","type":"task_card","task_id":"t2"}]""").first()
        assertEquals(ChatBlock.Kind.Task("t2"), snake.kind)
    }

    @Test
    fun aBlockWithoutATaskIdIsOnlyItsLine() {
        val blocks = blocks("""[{"id":"b1","type":"taskCard"}]""")
        assertEquals(listOf(ChatBlock.Kind.Other("taskCard")), blocks.map { it.kind })
        assertEquals("Task", blocks.first().fallbackText)
    }

    @Test
    fun aGoalAndAMemoryLinkNeedTheirIdAndSummary() {
        val goal = blocks("""[{"id":"g","type":"goalLink","goalId":"g1","summary":"Run 10k"}]""")
        assertEquals(ChatBlock.Kind.Goal("g1", "Run 10k"), goal.first().kind)
        // No summary: not a link, only the line.
        val bare = blocks("""[{"id":"g","type":"goal_link","goal_id":"g1"}]""")
        assertEquals(ChatBlock.Kind.Other("goal_link"), bare.first().kind)
        assertEquals("Goal", bare.first().fallbackText)

        val memory = blocks("""[{"id":"m","type":"memoryLink","memoryId":"m1","summary":"Lives in Berlin"}]""")
        assertEquals(ChatBlock.Kind.Memory("m1", "Lives in Berlin"), memory.first().kind)
        val bareMemory = blocks("""[{"id":"m","type":"memoryLink","memory_id":"m1"}]""")
        assertEquals(ChatBlock.Kind.Other("memoryLink"), bareMemory.first().kind)
    }

    @Test
    fun aConversationLinkCarriesItsStepsAndWhetherItIsACapture() {
        val json = """
            [{"id":"c","type":"conversationLink","conversationId":"c1","summary":"Standup","recommended_action_items":[
            {"description":"Book the room","taskId":"t9"},{"description":"Book the room"},{"taskId":"t8"}]}]
        """.trimIndent()
        val block = blocks(json).first()
        // A hint without a description is dropped; the same line twice is kept (the mapper does not dedupe).
        assertEquals(
            ChatBlock.Kind.Conversation(
                conversationID = "c1", summary = "Standup",
                actionItems = listOf(
                    ChatBlock.ActionItemHint("Book the room", "t9"),
                    ChatBlock.ActionItemHint("Book the room", null),
                ),
                isCapture = false,
            ),
            block.kind,
        )
        assertEquals("Meeting notes ready - Standup", block.fallbackText)

        val capture = blocks("""[{"id":"c","type":"capture_link","conversation_id":"c2","summary":"Walk"}]""")
        assertEquals(
            ChatBlock.Kind.Conversation("c2", "Walk", emptyList(), isCapture = true),
            capture.first().kind,
        )
    }

    /** A conversation link with no summary has nothing to draw, so only its line stays. */
    @Test
    fun aLinkWithoutItsSummaryFallsBackToItsLine() {
        val blocks = blocks("""[{"id":"c","type":"conversationLink","conversationId":"c1"}]""")
        assertEquals(listOf(ChatBlock.Kind.Other("conversationLink")), blocks.map { it.kind })
        assertEquals("Meeting notes ready", blocks.first().fallbackText)
    }

    @Test
    fun aQuestionKeepsItsPreparedAnswers() {
        val json = """
            [{"id":"q","type":"questionCard","questionId":"q1","text":"Which one?","subject":{"kind":"task","id":"t1"},
            "options":[{"optionId":"o1","label":"The roof","preparedAnswer":"Go with the roof"},{"optionId":"o2","label":"The cellar"}]}]
        """.trimIndent()
        val block = blocks(json).first()
        val question = (block.kind as ChatBlock.Kind.Question).question
        assertEquals("q1", question.questionID)
        assertEquals("Which one?", question.text)
        assertEquals(listOf("o1", "o2"), question.options.map { it.id })
        // An option with no prepared answer sends its own label.
        assertEquals(listOf("Go with the roof", "The cellar"), question.options.map { it.preparedAnswer })
        assertEquals(2, question.visibleOptions.size)
        assertFalse(question.isAnswered)
    }

    @Test
    fun anAnsweredQuestionShowsOnlyTheChosenOption() {
        val json = """
            [{"id":"q","type":"questionCard","questionId":"q1","text":"Which one?","subject":{"kind":"task","id":"t1"},
            "selectedOptionId":"o2","options":[{"optionId":"o1","label":"The roof"},{"optionId":"o2","label":"The cellar"}]}]
        """.trimIndent()
        val block = blocks(json).first()
        val question = (block.kind as ChatBlock.Kind.Question).question
        assertTrue(question.isAnswered)
        assertEquals(listOf("The cellar"), question.visibleOptions.map { it.label })
    }

    /**
     * A question is a question only with its subject and at least one usable option; anything less
     * keeps the question's line (the word "Question" when it carries no text of its own).
     */
    @Test
    fun aBrokenQuestionIsOnlyItsLine() {
        val partials: List<Pair<String, String?>> = listOf(
            """{"id":"q","type":"question_card","questionId":"q1","options":[{"optionId":"o1","label":"A"}]}""" to "Question",
            """{"id":"q","type":"question_card","questionId":"q1","text":"Which?","subject":{"kind":"task"}}""" to "Which?",
            """{"id":"q","type":"question_card","questionId":"q1","text":"Which?","subject":{"kind":"task","id":"t1"},"options":[]}""" to "Which?",
            """{"id":"q","type":"question_card","questionId":"q1","text":"Which?","subject":{"kind":"task","id":"t1"},"options":[{"label":"No id"}]}""" to "Which?",
            """{"id":"q","type":"question_card","question_id":"q1","text":"Which?","subject":{"kind":"task","id":"t1"},"options":[{"option_id":"o1","label":"The roof"}]}""" to null,
        )
        for ((partial, line) in partials) {
            val block = blocks("[$partial]").firstOrNull()
            if (line == null) {
                // The snake_case spelling of an option is read like the camelCase one.
                assertEquals(
                    ChatBlock.Kind.Question(
                        ChatQuestion("q1", "Which?", listOf(ChatQuestion.Option("o1", "The roof", "The roof")), null),
                    ),
                    block?.kind,
                )
                continue
            }
            assertEquals(partial, ChatBlock.Kind.Other("question_card"), block?.kind)
            assertEquals(partial, line, block?.fallbackText)
        }
    }

    @Test
    fun anAgentSpawnIsRunningAndACompletionCarriesItsStatus() {
        val spawn = blocks(
            """[{"id":"a1","type":"agentSpawn","sessionId":"s","runId":"r","title":"Check flights","objective":"Find one"}]""",
        ).first()
        assertEquals(
            ChatBlock.Kind.AgentRun("Check flights", "Find one", ChatBlock.AgentRunStatus.Running),
            spawn.kind,
        )

        fun completion(status: String?): ChatBlock.Kind? {
            val field = status?.let { ",\"status\":\"$it\"" }.orEmpty()
            val json = "[{\"id\":\"a2\",\"type\":\"agent_completion\",\"title\":\"Did it\",\"output\":\"Booked\"$field}]"
            return blocks(json).firstOrNull()?.kind
        }
        fun completed(status: ChatBlock.AgentRunStatus) = ChatBlock.Kind.AgentRun("Did it", "Booked", status)
        assertEquals(completed(ChatBlock.AgentRunStatus.Completed), completion("completed"))
        assertEquals(completed(ChatBlock.AgentRunStatus.Completed), completion("succeeded"))
        assertEquals(completed(ChatBlock.AgentRunStatus.Cancelled), completion("cancelled"))
        assertEquals(completed(ChatBlock.AgentRunStatus.TimedOut), completion("timed_out"))
        assertEquals(completed(ChatBlock.AgentRunStatus.Failed), completion("failed"))
        // An unknown word is not read as success.
        assertEquals(completed(ChatBlock.AgentRunStatus.Failed), completion("banana"))
        // Older stored completions carry no status at all: they completed.
        assertEquals(completed(ChatBlock.AgentRunStatus.Completed), completion(null))
    }

    @Test
    fun aSpawnWithoutARunIsOnlyItsLine() {
        val blocks = blocks("""[{"id":"a1","type":"agent_spawn","session_id":"s","title":"Check flights"}]""")
        assertEquals(listOf(ChatBlock.Kind.Other("agent_spawn")), blocks.map { it.kind })
    }

    @Test
    fun aDiscoveryCarriesItsLongTextAndItsLine() {
        val blocks = blocks(
            """[{"id":"d","type":"discoveryCard","title":"A cafe","summary":"Nearby","fullText":"Two doors down, open late."}]""",
        )
        assertEquals(ChatBlock.Kind.Discovery("A cafe", "Nearby", "Two doors down, open late."), blocks.first().kind)
        assertEquals("Discovery - A cafe - Nearby", blocks.first().fallbackText)
    }

    @Test
    fun aMemoryReviewKeepsThreeItemsAtMost() {
        val items = (1..5).joinToString(",") { """{"memoryId":"m$it","content":"Fact $it","category":"system"}""" }
        val json = """[{"id":"r","type":"memory_review_card","summaryId":"s1","date":"2026-10-12","items":[$items]}]"""
        val block = blocks(json).first()
        val review = (block.kind as ChatBlock.Kind.MemoryReview).review
        assertEquals("s1", review.summaryID)
        assertEquals("2026-10-12", review.date)
        assertEquals(listOf("m1", "m2", "m3"), review.items.map { it.memoryID })
        assertEquals("Fact 1", review.items.first().content)
        // The review card draws its own heading: it says nothing as a line.
        assertTrue(block.fallbackText.isEmpty())
    }

    @Test
    fun aReviewWithNothingUsableIsNoCard() {
        // Items without an id or without text are dropped, and a card with none left is nothing.
        val blocks = blocks(
            """[{"id":"r","type":"memoryReviewCard","items":[{"content":"No id"},{"memoryId":"m1"}]}]""",
        )
        assertTrue(blocks.isEmpty())
    }

    /** The follow-up chip and the evidence envelope are read elsewhere; they must not double as cards. */
    @Test
    fun theFollowUpAndEvidenceBlocksAreLeftOut() {
        val blocks = blocks(
            """
            [{"id":"f","type":"followUp","text":"Want Tuesday too?"},
            {"id":"e","type":"evidence","references":[]},
            {"id":"e2","type":"evidence_envelope"},
            {"id":"t","type":"taskCard","taskId":"t1"}]
            """.trimIndent(),
        )
        assertEquals(listOf("t"), blocks.map { it.id })
    }

    @Test
    fun anUnknownTypeKeepsItsLine() {
        val blocks = blocks("""[{"id":"x","type":"quantumLeap","title":"Leap","summary":"Up"}]""")
        assertEquals(listOf(ChatBlock.Kind.Other("quantumLeap")), blocks.map { it.kind })
        assertEquals("Chat item - Leap - Up", blocks.first().fallbackText)
    }

    /**
     * A block with no id still renders, under an id of its own; a drawing type without one is not
     * drawn (there would be nothing to address it by).
     */
    @Test
    fun aBlockWithoutAnIdGetsOneOfItsOwn() {
        val blocks = blocks("""[{"type":"taskCard","taskId":"t1"},{"type":"thinking","text":"Looking at the calendar"}]""")
        assertEquals(listOf("block-0", "block-1"), blocks.map { it.id })
        assertEquals(ChatBlock.Kind.Other("taskCard"), blocks[0].kind)
        assertEquals(ChatBlock.Kind.Other("thinking"), blocks[1].kind)
        assertEquals("Thinking - Looking at the calendar", blocks[1].fallbackText)
    }

    /** A block with neither a card nor a line of its own leaves no empty row behind. */
    @Test
    fun aBlockWithNeitherKindNorLineIsDropped() {
        assertTrue(blocks("""[{"id":"r","type":"memoryReviewCard"}]""").isEmpty())
        // The review card is the only type whose line is empty by design: a broken one is nothing.
        assertTrue(fallback("""{"type":"memoryReviewCard"}""").isEmpty())
    }

    @Test
    fun theBlockArrayAlsoArrivesAsAJSONString() {
        // A push sends the same array as a string.
        val text = """[{"id":"b1","type":"taskCard","taskId":"t1"},""" +
            """{"id":"b2","type":"questionCard","questionId":"q1","text":"Which?",""" +
            """"subject":{"kind":"task","id":"t1"},"options":[{"optionId":"o1","label":"A"}]}]"""
        val blocks = ChatBlockMapper.blocks(Json.parseToJsonElement("\"${text.replace("\"", "\\\"")}\""))
        assertEquals(listOf("b1", "b2"), blocks.map { it.id })
        assertEquals(ChatBlock.Kind.Task("t1"), blocks.first().kind)
        // Garbage in a string is no blocks at all, never a crash.
        assertTrue(ChatBlockMapper.blocks(Json.parseToJsonElement("\"not json\"")).isEmpty())
        assertTrue(ChatBlockMapper.blocks(Json.parseToJsonElement("""{"type":"taskCard"}""")).isEmpty())
        assertTrue(ChatBlockMapper.blocks(null).isEmpty())
        assertTrue(ChatBlockMapper.blocks(Json.parseToJsonElement("42")).isEmpty())
    }

    @Test
    fun aMessageReadsItsBlocksAndItsKindOffTheWire() {
        val json = """
            {"id":"m1","text":"Buy milk","sender":"ai","created_at":"2026-10-12T09:00:00Z","type":"day_summary",
            "content_blocks":[{"id":"b1","type":"taskCard","taskId":"t1"}]}
        """.trimIndent()
        val message = ChatMessageMapper.message(fromJSON = json)!!
        assertEquals(ChatMessage.Kind.DaySummary, message.kind)
        assertEquals(listOf(ChatBlock.Kind.Task("t1")), message.blocks.map { it.kind })
        assertEquals("Task", message.blocks.first().fallbackText)
    }

    /** A message with no `type`, and one with a type this client does not know, are both plain text. */
    @Test
    fun anUnknownMessageKindReadsAsText() {
        val plain = ChatMessageMapper.message(fromJSON = """{"id":"m2","text":"Hi","sender":"ai"}""")!!
        assertEquals(ChatMessage.Kind.Text, plain.kind)
        assertTrue(plain.blocks.isEmpty())
        val odd = ChatMessageMapper.message(fromJSON = """{"id":"m3","text":"Hi","sender":"ai","type":"recap_v9"}""")!!
        assertEquals(ChatMessage.Kind.Text, odd.kind)
    }

    /** The review card's own line is empty, so nothing of it reaches the plain-text path. */
    @Test
    fun aReviewKeepsItsItemsAndSaysNothingAsALine() {
        val json = """{"id":"r","type":"memoryReviewCard","summaryId":"s1","items":[{"memoryId":"m1","content":"F"}]}"""
        assertEquals("", fallback(json))
        val review = (blocksOf(json)!!.kind as ChatBlock.Kind.MemoryReview).review
        assertEquals(ChatMemoryReview.maxItems, 3)
        assertEquals("m1", review.items.single().memoryID)
    }

    /** A block object read on its own (no array around it) still carries its own id. */
    @Test
    fun aSingleBlockObjectReadsWithItsOwnFields() {
        val block = blocksOf("""{"id":"b9","type":"taskCard","taskId":"t9"}""")
        assertEquals("b9", block?.id)
        assertEquals(ChatBlock.Kind.Task("t9"), block?.kind)
        assertNull(blocksOf("""{"type":"follow_up","text":"again?"}"""))
    }
}

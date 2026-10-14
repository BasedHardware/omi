package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.Memory
import com.friend.ios.core.models.MemoryConflict
import com.friend.ios.core.models.SpeakerPrompt
import com.friend.ios.core.models.SpeakerPromptAnswer
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.service.InMemorySharedPreferences
import com.friend.ios.service.fakeAPI
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.ZoneId

/**
 * Ports of `MemoryReviewTests.swift`, `TaskTidyUpTests.swift` and the prompt half of
 * `VoicesStoreTests.swift`: the memory review queue, the tidy-up's prompt, parse and apply, and
 * the "Who is this?" prompts.
 */
class ReviewTidyUpPromptsTest {
    private val zone = ZoneId.of("Europe/Berlin")

    private fun memory(id: String, reasons: List<String> = emptyList(), at: Long = 0, category: String = "interesting", subject: String? = null) =
        Memory(id, "fact $id", null, category, Instant.ofEpochSecond(at), null, uncertaintyReasons = reasons, subjectName = subject)

    // Memory review

    @Test
    fun reviewAsksOnlyAboutRealDoubtsInPriorityOrder() = runTest {
        val api = fakeAPI {
            "memories" returns listOf(
                memory("plain", listOf("single_source")),
                memory("stale", listOf("stale"), at = 30),
                memory("other", listOf("third_party_subject"), at = 10, subject = "Lena"),
                memory("old", at = 1),
                memory("new", listOf("contradicted_by:old"), at = 5),
                memory("manual", listOf("stale"), category = "manual"),
                memory("once", listOf("low_capture_signal", "single_source"), at = 40),
            )
        }
        val store = MemoriesStore(api.client, CoroutineScope(Dispatchers.Unconfined))
        store.load()
        val queue = store.reviewQueue
        assertEquals(listOf("memory.new", "memory.other", "memory.stale", "memory.once"), queue.map { it.id })
        assertEquals(MemoryReviewQuestion.WhichIsRight("fact old", "fact new"), queue[0].question)
        assertEquals(MemoryReviewQuestion.AboutSomeoneElse("Lena"), queue[1].question)
        assertEquals(MemoryReviewQuestion.HeardOnce, queue[3].question)
        assertEquals(4, store.reviewCount)
    }

    @Test
    fun conflictsComeFirstAndAFailedResolveComesBack() = runTest {
        val conflict = MemoryConflict("r1", "f1", "Lives in Munich.", listOf("old"), null)
        val api = fakeAPI {
            "memories" returns listOf(memory("old"))
            "memoryReviewQueue" returns listOf(conflict)
            "resolveMemoryConflict" throws APIError.Http(500, "")
        }
        val store = MemoriesStore(api.client, CoroutineScope(Dispatchers.Unconfined))
        store.load()
        store.loadReviewQueue()
        val item = store.reviewQueue.first()
        assertEquals(MemoryReviewQuestion.WhichIsRight("fact old", "Lives in Munich."), item.question)
        store.answer(item, MemoryReviewAnswer.KeepNew)
        assertEquals(MemoryConflict.Decision.Accept, api.called("resolveMemoryConflict").single()[1])
        assertEquals(listOf(conflict), store.reviewConflicts)
        assertNotNull(store.lastError)
    }

    @Test
    fun neitherDiscardsBothVersions() = runTest {
        val api = fakeAPI {
            "memories" returns listOf(memory("old"), memory("new", listOf("contradicted_by:old")))
            "reviewMemory" returns Unit
        }
        val store = MemoriesStore(api.client, CoroutineScope(Dispatchers.Unconfined))
        store.load()
        store.answer(store.reviewQueue.single(), MemoryReviewAnswer.Neither)
        assertEquals(listOf(listOf<Any?>("new", false), listOf<Any?>("old", false)), api.called("reviewMemory"))
        assertTrue(store.memories.isEmpty())
    }

    /**
     * The chat's review card holds an id from the message, which may not be on the loaded list: the
     * verdict still goes out, and nothing on screen moves.
     */
    @Test
    fun reviewOfAnUnloadedMemoryStillVotes() = runTest {
        var failure: Throwable? = null
        val api = fakeAPI {
            "memories" returns listOf(memory("a"), memory("b"))
            "reviewMemory" does { failure?.let { throw it } }
        }
        val store = MemoriesStore(api.client, CoroutineScope(Dispatchers.Unconfined))
        store.load()
        store.review("nowhere", isRight = false)
        assertEquals(listOf(listOf<Any?>("nowhere", false)), api.called("reviewMemory"))
        assertEquals(listOf("a", "b"), store.memories.map { it.id })
        assertNull(store.lastError)

        // A failed vote leaves the list exactly as it was, with no row to put back.
        failure = APIError.Http(500, "")
        store.review("nowhere", isRight = true)
        assertEquals(listOf("a", "b"), store.memories.map { it.id })
        assertNotNull(store.lastError)
    }

    // Tidy-up

    private fun task(id: String, text: String, created: Long) = Fixtures.task(id, text, created = Instant.ofEpochSecond(created))

    @Test
    fun parseMapsKeysAndDropsRepeats() {
        val keys = mapOf("t1" to "a", "t2" to "b", "t3" to "c", "t4" to "d")
        val answer = """
            Sure! ```json
            {"merge":[{"keep":"t1","drop":["t2","t1","t9"],"why":"same call"}],
             "done":[{"id":"t2","why":"dup"},{"id":3,"why":"happened"}],
             "not_task":["4"],"important":["t1","t1","t3"]}
            ```
        """.trimIndent()
        val proposal = TaskTidyUp.parse(answer, keys)!!
        assertEquals(listOf(TaskTidyUp.Merge("a", listOf("b"), "same call")), proposal.merges)
        assertEquals(listOf(TaskTidyUp.Change("c", "happened")), proposal.done)
        assertEquals(listOf(TaskTidyUp.Change("d", "")), proposal.notTask)
        assertEquals(listOf("a", "c"), proposal.important)
        assertNull(TaskTidyUp.parse("no json here", keys))
        assertEquals(proposal, TaskTidyUp.decode(TaskTidyUp.encode(proposal)))
    }

    @Test
    fun promptListsTasksWithKeys() {
        val prompt = TaskTidyUp.prompt(
            listOf(task("a", "Call | Anna\nback", 0)), source = { "Weekly sync" }, now = Instant.parse("2026-10-08T10:00:00Z"), zone = zone,
        )
        assertTrue(prompt.contains("Today is 2026-10-08."))
        assertTrue(prompt.contains("t1 | Call / Anna back | - | \"Weekly sync\" 1970-01-01"))
    }

    @Test
    fun tidyUpAsksOnceADayAndAppliesWhatIsKept() = runTest {
        val defaults = InMemorySharedPreferences()
        val api = fakeAPI {
            "actionItems" returns listOf(task("a", "Call Anna", 2), task("b", "Phone Anna", 1), task("c", "Old thing", 0))
            "chatSessions" returns emptyList<Pair<String, String>>()
            "createChatSession" returns "s1"
            "sendChatMessage" returns flowOf(
                ChatStreamEvent.Delta("{\"merge\":[{\"keep\":\"t1\",\"drop\":[\"t2\"]}],"),
                ChatStreamEvent.Done(ChatMessage("m", "{\"merge\":[{\"keep\":\"t1\",\"drop\":[\"t2\"],\"why\":\"same\"}],\"done\":[{\"id\":\"t3\"}]}", ChatMessage.Sender.Omi, Instant.EPOCH)),
            )
            "setActionItemStatus" returns Unit
        }
        val store = TasksStore(api.client, zone, defaults = defaults)
        store.load()
        val now = Instant.parse("2026-10-08T07:00:00Z")
        store.tidyUpIfDue(source = { null }, now = now)
        val proposal = store.currentTidyUp!!
        assertEquals(2, proposal.edits.size)
        // Stored: a new store (the next launch) still has it; the day is marked.
        assertEquals(proposal, TasksStore(api.client, zone, defaults = defaults).tidyUp)
        store.tidyUpIfDue(source = { null }, now = now.plusSeconds(60))
        assertEquals(1, api.called("sendChatMessage").size)
        assertEquals(1, store.applyTidyUp(proposal.edits.take(1)))
        assertEquals(listOf<Any?>("b", ActionItem.Status.Superseded, "a"), api.called("setActionItemStatus").single())
        assertNull(store.tidyUp)
    }

    // "Who is this?"

    @Test
    fun answeringTakesThePromptOffAndAFailureBringsItBack() = runTest {
        val first = SpeakerPrompt("p1", SpeakerPrompt.Kind.OwnerCheck, conversationID = "c", speakerID = 1, segmentIDs = emptyList())
        val second = first.copy(id = "p2")
        var fail = false
        val api = fakeAPI {
            "speakerPrompts" returns listOf(first, second)
            "markSpeakerPromptsShown" returns Unit
            "answerSpeakerPrompt" does { if (fail) throw APIError.Http(500, "") }
        }
        val voices = VoicesStore(api.client)
        voices.loadPrompts()
        voices.promptsShown()
        voices.promptsShown()
        assertEquals(1, api.called("markSpeakerPromptsShown").size)
        voices.answer(first, SpeakerPromptAnswer.Me)
        assertEquals(second, voices.currentPrompt)
        fail = true
        voices.answer(second, SpeakerPromptAnswer.Skip)
        assertEquals(second, voices.currentPrompt)
        assertNotNull(voices.lastError)
    }
}

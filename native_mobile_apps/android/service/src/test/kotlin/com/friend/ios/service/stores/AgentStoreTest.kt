package com.friend.ios.service.stores

import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.Recommendation
import com.friend.ios.core.models.Workstream
import com.friend.ios.core.models.WorkstreamRef
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.ZoneOffset

@OptIn(ExperimentalCoroutinesApi::class)
class AgentStoreTest {
    private val now = Instant.parse("2026-10-08T15:00:00Z")
    private val task = Fixtures.task("t1", "Draft the pricing memo for Anna", conversation = "c1")

    private fun TestScope.store(api: FakeAgentAPI, prefs: Preferences = Preferences(FakePrefs())) =
        AgentStore(api, prefs, this, now = { now })

    private fun answer(text: String) = ChatMessage(id = "m1", text = text, sender = ChatMessage.Sender.Omi, createdAt = now)

    @Test
    fun takeOverRunsInItsOwnThreadAndRecordsTheResult() = runTest {
        val api = FakeAgentAPI().apply {
            frames = listOf(ChatStreamEvent.Step("Preparing response…"), ChatStreamEvent.Step("Searching the web"), ChatStreamEvent.Delta("Done"), ChatStreamEvent.Done(answer("Memo drafted.")))
        }
        val prefs = Preferences(FakePrefs())
        val agent = store(api, prefs)
        agent.takeOver(task, "Pricing sync")
        val run = agent.runs.getValue("t1")
        assertEquals(AgentStore.RunState.Done("Memo drafted."), run.state)
        assertEquals(listOf("Searching the web"), run.steps)
        assertEquals("ws1", run.workstreamID)
        assertEquals("s1", run.sessionID)
        assertEquals(listOf("✦ Draft the pricing memo for Anna" to AgentStore.RUN_SESSION_APP_ID), api.createdSessions)
        assertEquals(listOf("s1"), prefs.strings(NativeKey.AgentChatSessionIDs))
        assertEquals(ChatContext(ChatContext.Kind.Task, "t1", task.description), api.contexts.single())
        assertTrue(api.prompts.single().contains("It came up in my conversation \"Pricing sync\"."))
        assertEquals(listOf(AgentStore.STARTED_SUMMARY, "Searching the web", "Done: Memo drafted."), api.events.map { it.second })
        assertEquals(listOf("artifact.ws1", "update.ws1.completed"), api.writes)
    }

    @Test
    fun cannedAnswerAndErrorFrameFailWithTheirReason() = runTest {
        val api = FakeAgentAPI().apply { frames = listOf(ChatStreamEvent.Done(answer(ChatStreamEvent.serviceFailureTexts[2]))) }
        val agent = store(api)
        agent.takeOver(task, null)
        assertEquals(RunFailure.Timeout, agent.runs.getValue("t1").failure)
        assertEquals(RunFailure.Timeout.eventSummary, api.events.last().second)

        api.frames = listOf(ChatStreamEvent.Failed("quota_exceeded"), ChatStreamEvent.Done(answer("Sorry, I encountered an error. Please try again.")))
        agent.resume(task, null)
        assertEquals(RunFailure.QuotaExceeded, agent.runs.getValue("t1").failure)
        assertFalse(RunFailure.QuotaExceeded.canRetry)
    }

    @Test
    fun streamErrorsAndEmptyStreamsKeepTheirReason() = runTest {
        val api = FakeAgentAPI().apply { streamError = APIError.Http(503, "") }
        val agent = store(api)
        agent.takeOver(task, null)
        assertEquals(RunFailure.ServerError, agent.runs.getValue("t1").failure)

        api.streamError = null
        api.frames = emptyList()
        agent.resume(task, null)
        assertEquals(RunFailure.NoAnswer, agent.runs.getValue("t1").failure)
    }

    @Test
    fun bookkeepingFailureStillRunsTheWork() = runTest {
        val api = FakeAgentAPI().apply {
            generationError = APIError.Transport("down")
            frames = listOf(ChatStreamEvent.Done(answer("Memo drafted.")))
        }
        val agent = store(api)
        agent.takeOver(task, null)
        assertEquals(AgentStore.RunState.Done("Memo drafted."), agent.runs.getValue("t1").state)
        assertNull(agent.runs.getValue("t1").workstreamID)
        assertTrue(api.events.isEmpty())
    }

    @Test
    fun stopEndsTheStreamAsStoppedAndResumeKeepsTheThread() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = FakeAgentAPI().apply {
            streamFlow = flow {
                emit(ChatStreamEvent.Step("Reading the calendar"))
                gate.await()
            }
        }
        val agent = store(api)
        val job = launch { agent.takeOver(task, null) }
        runCurrent()
        assertTrue(agent.runs.getValue("t1").isActive)
        assertEquals(AgentStore.RunState.Working("Reading the calendar"), agent.runs.getValue("t1").state)
        agent.stop("t1")
        advanceUntilIdle()
        job.join()
        assertTrue(agent.runs.getValue("t1").isStopped)

        api.streamFlow = null
        api.frames = listOf(ChatStreamEvent.Done(answer("Picked up again.")))
        agent.resume(task, null)
        assertEquals(1, api.createdSessions.size)
        assertEquals(listOf("s1", "s1"), api.streamSessions)
        assertTrue(api.prompts.last().contains("pick up where you left off"))
    }

    @Test
    fun aRunOutlivesTheCallerThatStartedIt() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = FakeAgentAPI().apply {
            streamFlow = flow {
                gate.await()
                emit(ChatStreamEvent.Done(answer("Done anyway.")))
            }
        }
        val agent = store(api)
        val caller = launch { agent.takeOver(task, null) }
        runCurrent()
        caller.cancel()
        gate.complete(Unit)
        advanceUntilIdle()
        assertEquals(AgentStore.RunState.Done("Done anyway."), agent.runs.getValue("t1").state)
    }

    @Test
    fun openedRunsPersistAndANewRunIsNewsAgain() = runTest {
        val prefs = Preferences(FakePrefs())
        val api = FakeAgentAPI().apply { frames = listOf(ChatStreamEvent.Done(answer("Ok."))) }
        val agent = store(api, prefs)
        agent.markOpened("t1")
        assertEquals(setOf("t1"), store(api, prefs).openedRunIDs)
        agent.takeOver(task, null)
        assertFalse("t1" in agent.openedRunIDs)
        assertTrue(prefs.strings(NativeKey.OpenedAgentRuns).isEmpty())
    }

    @Test
    fun recommendationsHideDecidedHandledAndExpiredOnes() = runTest {
        val fresh = Recommendation("r1", "Send", "", "", taskID = "t9", dedupeKey = "k1")
        val decided = Recommendation("r2", "Book", "", "", taskID = null, dedupeKey = "k2")
        val expired = Recommendation("r3", "Old", "", "", taskID = null, expiresAt = now.minusSeconds(60))
        val handled = Recommendation("r4", "Memo", "", "", taskID = "t1")
        val api = FakeAgentAPI().apply { recommendations = listOf(fresh, decided, expired, handled) }
        val agent = store(api)
        agent.loadRecommendations()
        agent.decide(decided, Recommendation.Decision.Later)
        val tasks = listOf(task.copy(workstreamID = "ws1"))
        assertEquals(listOf("r1"), agent.openRecommendations(tasks).map { it.id })
        assertEquals(listOf("feedback.r2.Later.7"), api.writes)
    }

    @Test
    fun recoveredRunsReadTheirWorkstream() = runTest {
        fun event(seq: Int, summary: String, minutesAgo: Long) =
            Workstream.Event("e$seq", "agent_update", summary, now.minusSeconds(minutesAgo * 60), seq)
        val open = Workstream("ws1", "Memo", Workstream.Status.Open, null, listOf(event(1, AgentStore.STARTED_SUMMARY, 3), event(2, "Searching the web", 2)))
        val quiet = Workstream("ws2", "Old", Workstream.Status.Open, null, listOf(event(1, AgentStore.STARTED_SUMMARY, 60)))
        val done = Workstream("ws3", "Done", Workstream.Status.Completed, "Booked.", listOf(event(1, "Done: Booked.", 5)))
        val failed = Workstream("ws4", "Failed", Workstream.Status.Open, null, listOf(event(1, RunFailure.ToolLoop.eventSummary, 5)))
        val api = FakeAgentAPI().apply { workstreams = listOf(open, quiet, done, failed).associateBy { it.id } }
        val agent = store(api)
        val tasks = (1..4).map { Fixtures.task("t$it", "Task $it").copy(workstreamID = "ws$it") }
        agent.loadWorkstreams(tasks)
        val items = agent.workItems(tasks).associateBy { it.id }
        assertEquals(AgentStore.RunState.Working("Searching the web"), items.getValue("t1").state)
        assertTrue(items.getValue("t2").isStopped)
        assertEquals(AgentStore.RunState.Done("Booked."), items.getValue("t3").state)
        assertEquals(RunFailure.ToolLoop, items.getValue("t4").failure)
        assertNotNull(agent.histories["t1"])
    }

    @Test
    fun failureCodesRoundTrip() {
        assertEquals(RunFailure.NotConnected, RunFailure.fromStreamError("Your calendar is not connected"))
        assertEquals(RunFailure.Refused, RunFailure.fromAnswer("Hmm. " + RunFailure.REFUSAL_TEXT))
        assertEquals(RunFailure.Timeout, RunFailure.fromEvent(RunFailure.Timeout.eventSummary))
        assertEquals(RunFailure.CouldNotFinish, RunFailure.fromEvent(AgentStore.FAILED_SUMMARY))
        assertEquals(RunFailure.Offline, RunFailure.fromError(APIError.Transport("x")))
        assertEquals(RunFailure.QuotaExceeded, RunFailure.fromError(APIError.Http(402, "")))
        assertFalse(AgentStore.isStepEvent("Done: it"))
        assertFalse(AgentStore.isStepEvent("Still working…"))
        assertTrue(AgentStore.isStepEvent("Checking the calendar"))
    }
}

class HomeAttentionRunsTest {
    private val zone = ZoneOffset.UTC
    private val now: Instant = Instant.parse("2026-10-08T15:00:00Z")
    private val tasks = listOf(
        Fixtures.task("a", "Draft the memo for Anna", due = now.plusSeconds(3_600)),
        Fixtures.task("b", "Book the dentist appointment", due = now.minusSeconds(86_400)),
    )

    private fun run(id: String, state: AgentStore.RunState, minutesAgo: Long = 1) =
        AgentStore.Run(id = id, taskTitle = id, state = state, steps = emptyList(), partialText = "", startedAt = now.minusSeconds(minutesAgo * 60))

    @Test
    fun aRunningTaskKeepsItsCardEvenWithAWorkstream() {
        val running = tasks.map { if (it.id == "a") it.copy(workstreamID = "ws") else it }
        val inbox = HomeAttention.inbox(
            HomeAttention.Input(runs = listOf(run("a", AgentStore.RunState.Working("Searching"))), tasks = running, now = now, zone = zone),
        )
        assertEquals(setOf("task.a", "task.b"), inbox.needsYou.map { it.id }.toSet())
        assertTrue(inbox.later.none { it is HomeAttention.Item.Working })
    }

    @Test
    fun anEndedRunReplacesTheCard() {
        val inbox = HomeAttention.inbox(
            HomeAttention.Input(
                runs = listOf(run("a", AgentStore.RunState.Done("Drafted.")), run("b", AgentStore.RunState.Failed("stopped"))),
                tasks = tasks, now = now, zone = zone,
            ),
        )
        assertEquals(listOf("finished.a", "help.b"), inbox.needsYou.map { it.id })
        assertEquals(HomeTapTargets.Target.Run("a"), HomeTapTargets.target(inbox.needsYou[0]))
    }

    @Test
    fun severalFinishedRunsFoldIntoOneCardAndOpenedOnesLeave() {
        val runs = listOf(run("a", AgentStore.RunState.Done("1"), 2), run("b", AgentStore.RunState.Done("2"), 1), run("c", AgentStore.RunState.Done("3"), 3))
        val inbox = HomeAttention.inbox(HomeAttention.Input(runs = runs, openedRunIDs = setOf("c"), tasks = tasks, now = now, zone = zone))
        assertEquals(listOf("finished"), inbox.needsYou.map { it.id })
        assertEquals(listOf("finished.b", "finished.a"), inbox.later.map { it.id })
        assertEquals(HomeTapTargets.Target.Later, HomeTapTargets.target(inbox.needsYou[0]))
    }

    @Test
    fun aRunWithoutACardWaitsInLaterAsWorking() {
        val inbox = HomeAttention.inbox(
            HomeAttention.Input(runs = listOf(run("gone", AgentStore.RunState.Starting)), tasks = tasks, now = now, zone = zone),
        )
        assertEquals(listOf("working.gone"), inbox.later.map { it.id })
    }
}

/** The agent half of the API, with the rest unimplemented. */
class FakeAgentAPI(
    private val base: APIClientProtocol = HomeFakeAPI.unimplemented(),
) : APIClientProtocol by base {
    var frames: List<ChatStreamEvent> = emptyList()
    var streamFlow: Flow<ChatStreamEvent>? = null
    var streamError: Exception? = null
    var generationError: Exception? = null
    var recommendations: List<Recommendation> = emptyList()
    var workstreams: Map<String, Workstream> = emptyMap()
    val createdSessions = mutableListOf<Pair<String, String>>()
    val contexts = mutableListOf<ChatContext?>()
    val prompts = mutableListOf<String>()
    val streamSessions = mutableListOf<String?>()
    /** (idempotency key, summary) of every workstream event. */
    val events = mutableListOf<Pair<String, String>>()
    val writes = mutableListOf<String>()

    override suspend fun createChatSession(title: String, appID: String): String {
        createdSessions += title to appID
        return "s${createdSessions.size}"
    }

    override suspend fun accountGeneration(): Int {
        generationError?.let { throw it }
        return 7
    }

    override suspend fun startWork(onTask: String, title: String, generation: Int): String = "ws1"

    override suspend fun recordWorkstreamEvent(
        ref: WorkstreamRef,
        kind: String,
        summary: String,
        evidence: List<Map<String, String>>,
        idempotencyKey: String,
    ): String {
        events += idempotencyKey to summary
        return "e${events.size}"
    }

    override suspend fun recordResultArtifact(ref: WorkstreamRef, messageID: String, resultText: String, evidenceEventID: String, runID: String) {
        writes += "artifact.${ref.id}"
    }

    override suspend fun updateWorkstream(ref: WorkstreamRef, status: Workstream.Status?, summary: String?) {
        writes += "update.${ref.id}.${status?.rawValue}"
    }

    override suspend fun workstream(workstreamID: String): Workstream = workstreams[workstreamID] ?: throw APIError.Http(404, "")

    override suspend fun workstreamEvents(workstreamID: String, afterSequence: Int): List<Workstream.Event> =
        workstreams[workstreamID]?.events ?: throw APIError.Http(404, "")

    override suspend fun chatSessions(appID: String): List<Pair<String, String>> = emptyList()

    override suspend fun chatSessions(): List<Pair<String, String>> = emptyList()

    override suspend fun whatMattersNow(): List<Recommendation> = recommendations

    override suspend fun sendRecommendationFeedback(recommendation: Recommendation, decision: Recommendation.Decision, generation: Int) {
        writes += "feedback.${recommendation.id}.$decision.$generation"
    }

    override fun streamAgent(text: String, context: ChatContext?, sessionID: String?, deviceTools: List<String>): Flow<ChatStreamEvent> {
        prompts += text
        contexts += context
        streamSessions += sessionID
        streamFlow?.let { return it }
        return flow {
            streamError?.let { throw it }
            frames.forEach { emit(it) }
        }
    }
}

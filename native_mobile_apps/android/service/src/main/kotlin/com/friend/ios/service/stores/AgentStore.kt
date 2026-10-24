package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.Recommendation
import com.friend.ios.core.models.Workstream
import com.friend.ios.core.models.WorkstreamRef
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.UUID

/**
 * Port of `AgentStore.swift`: "Omi takes over": runs a task through the chat agent and records it
 * on a backend workstream (PLAN.md 4.4). The backend stores workstreams but executes nothing; the
 * chat agent does the work with its server-side tools, and this store keeps the workstream in step.
 *
 * Runs live in [scope] (the app's), not in the screen that started them: a card that leaves Home
 * mid-run must not end the run (Swift's unstructured `Task { await agent.takeOver(...) }`).
 *
 * Device tools ("Omi asks", `AgentStore+Asks.swift`) live in `AgentStoreAsks.kt`.
 */
class AgentStore(
    internal val api: APIClientProtocol,
    private val preferences: Preferences?,
    private val scope: CoroutineScope,
    internal val now: () -> Instant = { Instant.now() },
) {
    sealed interface RunState {
        data object Starting : RunState
        data class Working(val step: String) : RunState
        data class Done(val result: String) : RunState
        /** Why it stopped: a [RunFailure] code (older runs: a free-text marker). */
        data class Failed(val code: String) : RunState
    }

    // Port of `AgentStore+Run.swift`.
    data class Run(
        /** The task id. */
        val id: String,
        val taskTitle: String,
        val workstreamID: String? = null,
        val state: RunState,
        val steps: List<String>,
        val partialText: String,
        val startedAt: Instant,
        /** The run's own chat thread (resume continues in it). */
        val sessionID: String? = null,
        /** When the work last moved (a step, text, an event on the workstream). */
        val lastProgressAt: Instant? = null,
        /** When this session's run ended (null while running, and for runs recovered from the backend). */
        val finishedAt: Instant? = null,
    ) {
        val isActive: Boolean get() = state is RunState.Starting || state is RunState.Working

        /** Why the run stopped, when it did. */
        val failure: RunFailure?
            get() {
                val code = (state as? RunState.Failed)?.code ?: return null
                return RunFailure.from(code) ?: RunFailure.fromEvent(code) ?: RunFailure.CouldNotFinish
            }

        /** Died without a word (no progress for [STALE_AFTER], no live stream): "Tap to resume". */
        val isStopped: Boolean get() = failure == RunFailure.Stopped
    }

    /** What an earlier run left on the backend: its steps (workstream events) and its thread. */
    data class RunHistory(
        val events: List<Workstream.Event>,
        val steps: List<String>,
        val partialText: String,
        val sessionID: String?,
    )

    var runs: Map<String, Run> by mutableStateOf(emptyMap())
        internal set
    var recommendations: List<Recommendation> by mutableStateOf(emptyList())
        internal set
    /** Dedupe keys of recommendations the user answered this session. */
    var decidedRecommendations: Set<String> by mutableStateOf(emptySet())
        internal set
    /** Tasks whose finished run the user has opened; Home only points at the others. */
    var openedRunIDs: Set<String> by mutableStateOf(preferences?.strings(NativeKey.OpenedAgentRuns).orEmpty().toSet())
        private set
    /** Workstreams Omi started in earlier sessions, keyed by workstream id. */
    var workstreams: Map<String, Workstream> by mutableStateOf(emptyMap())
        internal set
    /** Earlier runs rebuilt from the backend after a restart, keyed by task id. */
    var histories: Map<String, RunHistory> by mutableStateOf(emptyMap())
        internal set
    /** Device tool calls waiting for the user ("Omi asks"), by task id. */
    var deviceToolRequests: Map<String, PendingDeviceTool> by mutableStateOf(emptyMap())
        internal set
    /** A run asked something (the shell may tell the user when the app is away). */
    var onDeviceToolRequest: ((PendingDeviceTool) -> Unit)? = null
    /** The phone's side of the device tools (the app supplies it); null declares none. */
    var deviceTools: com.friend.ios.core.models.DeviceToolPerforming? = null

    /** Omi's questions, for Home's "Needs you". */
    val pendingDeviceTools: List<PendingDeviceTool>
        get() = deviceToolRequests.values.sortedBy { it.taskTitle }
    /**
     * Called when a run ends (task, whether it finished): the shell tells the user when the app
     * is not in front, since a hand-over can take minutes.
     */
    var onRunEnded: ((ActionItem, Boolean) -> Unit)? = null

    /** Per running task: the run id, its workstream and when a step was last written there. */
    private val contexts = mutableMapOf<String, RunContext>()
    /** Per running task: the stream's job ("Stop" cancels it) and the runs the user stopped. */
    private val streams = mutableMapOf<String, Deferred<Pair<ChatMessage?, RunFailure?>>>()
    private val stopRequests = mutableSetOf<String>()

    private data class RunContext(
        val runID: String,
        val ref: WorkstreamRef? = null,
        val lastStepEventAt: Instant? = null,
        val lastStepEvent: String? = null,
        val stepEvents: Int = 0,
    )

    val activeRuns: List<Run> get() = runs.values.filter { it.isActive }.sortedByDescending { it.startedAt }

    val recentRuns: List<Run> get() = runs.values.sortedByDescending { it.startedAt }

    /**
     * What Omi is doing or did: this session's runs plus earlier ones recovered from the backend
     * (tasks carry the workstream id), so the list survives an app restart. Finished runs drop off
     * after two days; running and failed ones stay until dealt with. A recovered run that has not
     * moved for [STALE_AFTER] is stopped, not "working" forever.
     */
    fun workItems(tasks: List<ActionItem>): List<Run> {
        val items = runs.toMutableMap()
        for (task in tasks) {
            if (items[task.id] != null || task.isCompleted) continue
            val workstream = task.workstreamID?.let { workstreams[it] } ?: continue
            items[task.id] = recoveredRun(task, workstream, histories[task.id])
        }
        val cutoff = now().minus(FINISHED_RUN_VISIBILITY)
        return items.values
            .filter { run -> run.state !is RunState.Done || run.startedAt.isAfter(cutoff) }
            .sortedByDescending { it.startedAt }
    }

    /** The user saw this task's finished run (the hand-over sheet showed its result). */
    fun markOpened(taskID: String) {
        if (taskID in openedRunIDs) return
        openedRunIDs = openedRunIDs + taskID
        preferences?.append(taskID, NativeKey.OpenedAgentRuns)
    }

    suspend fun takeOver(task: ActionItem, conversationTitle: String?) {
        scope.launch { run(task, conversationTitle, resumeSessionID = null) }.join()
    }

    /**
     * "Tap to resume": a stopped or failed run continues in the same workstream and, when the
     * run's thread is known, in that thread (else it starts fresh).
     */
    suspend fun resume(task: ActionItem, conversationTitle: String?) {
        if (runs[task.id]?.isActive == true) return
        val sessionID = runs[task.id]?.sessionID ?: histories[task.id]?.sessionID
        runs = runs - task.id
        scope.launch { run(task, conversationTitle, resumeSessionID = sessionID) }.join()
    }

    private suspend fun run(task: ActionItem, conversationTitle: String?, resumeSessionID: String?) {
        if (runs[task.id]?.isActive == true) return
        // A new run of the same task is news again.
        if (task.id in openedRunIDs) {
            openedRunIDs = openedRunIDs - task.id
            preferences?.let { it.set(NativeKey.OpenedAgentRuns, it.strings(NativeKey.OpenedAgentRuns).filter { id -> id != task.id }) }
        }
        val runID = UUID.randomUUID().toString().lowercase()
        update(task.id) {
            Run(
                id = task.id, taskTitle = task.description, state = RunState.Starting, steps = emptyList(), partialText = "",
                startedAt = now(), sessionID = resumeSessionID, lastProgressAt = now(),
            )
        }
        contexts[task.id] = RunContext(runID)

        // A thread of its own per run, under the run app id, so the main chat stays the user's.
        var sessionID = resumeSessionID
        if (sessionID == null) {
            sessionID = try {
                api.createChatSession(SESSION_TITLE_PREFIX + task.description, RUN_SESSION_APP_ID)
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                null
            }
            sessionID?.let { preferences?.append(it, NativeKey.AgentChatSessionIDs) }
        }
        update(task.id) { it?.copy(sessionID = sessionID) }

        val workstream = openWorkstream(task, runID, sessionID)
        update(task.id) { it?.copy(workstreamID = workstream?.id) }
        contexts[task.id] = contexts[task.id]?.copy(ref = workstream) ?: RunContext(runID, workstream)
        val prompt = if (resumeSessionID == null) prompt(task, conversationTitle) else resumePrompt(task, conversationTitle)
        val outcome = work(task, prompt, sessionID)
        deviceToolRequests = deviceToolRequests - task.id
        record(outcome, workstream, runID)
        contexts.remove(task.id)
        onRunEnded?.invoke(task, outcome.isSuccess)
    }

    /**
     * Opens (or reuses) the task's workstream and notes the start, with the run's thread as
     * evidence (a restart finds it there). Null if bookkeeping fails; the work itself still runs.
     */
    private suspend fun openWorkstream(task: ActionItem, runID: String, sessionID: String?): WorkstreamRef? = try {
        val generation = api.accountGeneration()
        val id = api.startWork(task.id, task.description, generation)
        val ref = WorkstreamRef(id, generation)
        val evidence = sessionID?.let { listOf(mapOf("kind" to "external", "id" to "chat_session:$it", "scope" to "canonical")) }.orEmpty()
        api.recordWorkstreamEvent(ref, "agent_update", STARTED_SUMMARY, evidence, "run:$runID:start")
        ref
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        null
    }

    /**
     * Streams the task through the chat agent. The typed reason of a failure survives: an `error:`
     * frame, a canned answer, a thrown error and an empty stream each keep their own.
     */
    private suspend fun work(task: ActionItem, prompt: String, sessionID: String?): Result<ChatMessage> {
        // Its own job, so "Stop" can end it (`stop`) while it waits for the next frame.
        val consumer = scope.async { consume(task, prompt, sessionID) }
        streams[task.id] = consumer
        var (finalMessage, failure) = try {
            consumer.await()
        } catch (e: CancellationException) {
            if (task.id !in stopRequests) throw e
            null to null
        }
        streams.remove(task.id)
        if (stopRequests.remove(task.id)) {
            finalMessage = null
            failure = RunFailure.Stopped
        }
        if (failure == null) {
            val canned = finalMessage?.let { RunFailure.fromAnswer(it.text) }
            if (canned != null) {
                failure = canned
            } else if (finalMessage?.text.isNullOrEmpty()) {
                failure = RunFailure.NoAnswer
            }
        }
        update(task.id) { it?.copy(finishedAt = now()) }
        val failed = failure
        if (failed != null) {
            update(task.id) { it?.copy(state = RunState.Failed(failed.rawValue)) }
            return Result.failure(RunFailureBox(failed))
        }
        val message = finalMessage ?: return Result.failure(RunFailureBox(RunFailure.NoAnswer))
        update(task.id) { it?.copy(state = RunState.Done(message.text)) }
        return Result.success(message)
    }

    private suspend fun consume(task: ActionItem, prompt: String, sessionID: String?): Pair<ChatMessage?, RunFailure?> {
        var finalMessage: ChatMessage? = null
        var failure: RunFailure? = null
        try {
            val context = ChatContext(ChatContext.Kind.Task, task.id, task.description)
            val tools = DeviceToolResolver.declaredTools(deviceTools)
            api.streamAgent(prompt, context, sessionID, deviceTools = tools).collect { event ->
                when (event) {
                    is ChatStreamEvent.Done -> finalMessage = event.message
                    // The first reason wins; the canned answer that may follow says less.
                    is ChatStreamEvent.Failed -> if (failure == null) failure = RunFailure.fromStreamError(event.code)
                    is ChatStreamEvent.DeviceTool -> ask(event.request, task)
                    is ChatStreamEvent.Step, is ChatStreamEvent.Delta, ChatStreamEvent.MemorySaved -> apply(event, task.id)
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            if (failure == null) failure = RunFailure.fromError(e)
        }
        return finalMessage to failure
    }

    /**
     * "Stop" on a running hand-over: the stream ends, the run reads as stopped (it can resume in
     * its thread), and a waiting "Omi asks" goes away.
     */
    fun stop(taskID: String) {
        if (runs[taskID]?.isActive != true) return
        val stream = streams[taskID] ?: return
        stopRequests += taskID
        deviceToolRequests = deviceToolRequests - taskID
        stream.cancel()
    }

    private suspend fun apply(event: ChatStreamEvent, taskID: String) {
        when (event) {
            is ChatStreamEvent.Step -> {
                update(taskID) { it?.copy(lastProgressAt = now()) }
                // Keep-alive frames say nothing about the work.
                if (isHeartbeat(event.text)) {
                    update(taskID) { run -> if (run?.state is RunState.Starting) run.copy(state = RunState.Working("")) else run }
                    return
                }
                update(taskID) { run -> run?.let { it.copy(steps = it.steps + event.text, state = RunState.Working(event.text)) } }
                recordStep(event.text, taskID)
            }
            is ChatStreamEvent.Delta -> update(taskID) { run ->
                val next = run?.let { it.copy(partialText = it.partialText + event.text, lastProgressAt = now()) }
                if (next?.state is RunState.Starting) next.copy(state = RunState.Working("")) else next
            }
            else -> Unit
        }
    }

    /**
     * Writes a think step to the workstream (throttled, no repeats), so other devices see what
     * Omi is doing and a restart can show the steps.
     */
    private suspend fun recordStep(step: String, taskID: String) {
        val context = contexts[taskID] ?: return
        val ref = context.ref ?: return
        val text = step.trim()
        if (!isStepEvent(text) || text == context.lastStepEvent) return
        context.lastStepEventAt?.let { if (Duration.between(it, now()) < STEP_EVENT_INTERVAL) return }
        val next = context.copy(lastStepEventAt = now(), lastStepEvent = text, stepEvents = context.stepEvents + 1)
        contexts[taskID] = next
        try {
            api.recordWorkstreamEvent(ref, "agent_update", text, emptyList(), "run:${next.runID}:step:${next.stepEvents}")
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
        }
    }

    /**
     * Writes the outcome to the workstream: the answer as an artifact and the workstream
     * completed, or a failure event (with its reason) that leaves it open.
     */
    private suspend fun record(outcome: Result<ChatMessage>, ref: WorkstreamRef?, runID: String) {
        if (ref == null) return
        try {
            val message = outcome.getOrElse { error ->
                val failure = (error as? RunFailureBox)?.failure ?: RunFailure.CouldNotFinish
                api.recordWorkstreamEvent(ref, "agent_update", failure.eventSummary, emptyList(), "run:$runID:failed")
                return
            }
            val eventID = api.recordWorkstreamEvent(
                ref, "agent_update", "Done: ${message.text}",
                listOf(mapOf("kind" to "chat_message", "id" to message.id, "scope" to "canonical")),
                "run:$runID:done",
            )
            api.recordResultArtifact(ref, message.id, message.text, eventID, runID)
            api.updateWorkstream(ref, Workstream.Status.Completed, message.text)
        } catch (e: CancellationException) {
            throw e
        } catch (_: Exception) {
            // The answer is shown either way; the record catches up on the next run.
        }
    }

    fun dismiss(taskID: String) {
        runs = runs - taskID
    }

    /**
     * Work that outlives the screen that asked for it (Swift's unstructured `Task { await ... }`):
     * a run, a resume, a recommendation's feedback.
     */
    fun background(block: suspend CoroutineScope.() -> Unit) {
        scope.launch(block = block)
    }

    /** Replaces one run (null removes it). */
    internal fun update(taskID: String, change: (Run?) -> Run?) {
        val next = change(runs[taskID])
        runs = if (next == null) runs - taskID else runs + (taskID to next)
    }

    /** Debug builds: a run that is working without a backend (screenshots). It reaches no agent. */
    fun showDemoRun(task: ActionItem, state: RunState = RunState.Working("")) {
        update(task.id) {
            Run(id = task.id, taskTitle = task.description, state = state, steps = emptyList(), partialText = "", startedAt = now(), lastProgressAt = now())
        }
    }

    companion object {
        /**
         * Marks an agent run's chat session in its backend title, so every device can tell runs from
         * the main chat (the local list of run sessions does not survive a sign-out or a new phone).
         */
        const val SESSION_TITLE_PREFIX = "✦ "
        /**
         * The app id a run's chat session is created with. The backend's "current" main chat is its
         * newest session without an app (`database/chat.py` `get_chat_session`), so a run must never
         * be one. No app has this id, so the backend answers the run as plain Omi (with every tool).
         */
        const val RUN_SESSION_APP_ID = "omi-agent-run"
        /** Event summary that marks a failed run (`RunFailure.eventSummary` appends the reason). */
        const val FAILED_SUMMARY = "Omi could not finish this task."
        /** Event summary of a run's start; carries the chat session as evidence. */
        const val STARTED_SUMMARY = "Omi started working on this task."
        /** A run with no progress for this long and no live stream has stopped. */
        val STALE_AFTER: Duration = Duration.ofMinutes(10)
        /** Think steps are written to the workstream at most this often (other devices see progress). */
        internal val STEP_EVENT_INTERVAL: Duration = Duration.ofSeconds(15)
        /** Finished hand-overs stay on Home this long; the task keeps the result after that. */
        internal val FINISHED_RUN_VISIBILITY: Duration = Duration.ofHours(48)
        /**
         * The backend's keep-alive `think:` frames (`agentic.py` `AGENT_STREAM_SETUP_PROGRESS`,
         * `AGENT_STREAM_PROGRESS_HEARTBEAT`) and its safety-guard warning: never a step.
         */
        val heartbeats = setOf("Preparing response…", "Preparing response...", "Still working…", "Still working...")

        /** A keep-alive or warning frame, not something Omi did. */
        fun isHeartbeat(step: String): Boolean {
            val trimmed = step.trim()
            return trimmed in heartbeats || trimmed.startsWith("⚠️")
        }

        /**
         * The trust ladder for v1: the agent prepares anything that would reach other people and
         * leaves the sending to the user.
         */
        fun prompt(task: ActionItem, conversationTitle: String?, zone: ZoneId = ZoneId.systemDefault()): String {
            val lines = mutableListOf("Please take care of this task for me: \"${task.description}\".")
            if (!conversationTitle.isNullOrEmpty()) lines += "It came up in my conversation \"$conversationTitle\"."
            task.dueAt?.let { due ->
                val formatted = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.FULL, FormatStyle.SHORT).format(due.atZone(zone))
                lines += "It is due $formatted."
            }
            lines += "Use your tools to do as much of it as you can: look things up, check my calendar and past conversations, " +
                "and prepare drafts. Do not send messages or invite other people; prepare those as drafts for me to send. " +
                "If a tool is unavailable or fails twice, stop using it and work with what you have. " +
                "Never run the same search twice; after three searches that add nothing new, stop searching. " +
                "Link every fact you took from the web to its source as a Markdown link. " +
                "Finish with a short summary of what you did and what is left for me."
            return lines.joinToString(" ")
        }

        /** Asked when a stopped run continues in its own thread. */
        fun resumePrompt(task: ActionItem, conversationTitle: String?): String =
            prompt(task, conversationTitle) +
                " You started on this earlier in this conversation and stopped before finishing: " +
                "pick up where you left off instead of starting over."
    }
}

/** Carries a [RunFailure] through [Result]. */
internal class RunFailureBox(val failure: RunFailure) : Exception(failure.rawValue)

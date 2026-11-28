package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.Workstream
import com.friend.ios.network.endpoints.ChatStreamEvent
import kotlinx.coroutines.CancellationException
import java.time.Duration
import java.time.Instant

// Port of `AgentStore+History.swift`: runs from earlier sessions, rebuilt from the backend: the
// workstream, its full event log (the steps) and the run's own chat thread; quiet ones count as
// stopped after `STALE_AFTER`.

private suspend fun <T> attempt(block: suspend () -> T): T? = try {
    block()
} catch (e: CancellationException) {
    throw e
} catch (_: Exception) {
    null
}

/**
 * Fetches the workstreams behind tasks Omi worked on before (they carry a workstream id), and for
 * unfinished ones what they did so far (steps and thread), so a restart does not show an empty
 * "working" forever.
 */
suspend fun AgentStore.loadWorkstreams(tasks: List<ActionItem>) {
    for (id in tasks.mapNotNull { it.workstreamID }.toSet()) {
        if (workstreams[id] != null) continue
        attempt { api.workstream(id) }?.let { workstreams = workstreams + (id to it) }
    }
    for (task in tasks) {
        if (task.isCompleted || runs[task.id] != null || histories[task.id] != null) continue
        val workstream = task.workstreamID?.let { workstreams[it] } ?: continue
        if (workstream.status == Workstream.Status.Completed) continue
        loadHistory(task)
    }
}

/** An earlier run's steps (its workstream events) and its thread's latest answer text. */
suspend fun AgentStore.loadHistory(task: ActionItem) {
    val workstreamID = task.workstreamID ?: return
    val events = attempt { api.workstreamEvents(workstreamID, 0) } ?: workstreams[workstreamID]?.events.orEmpty()
    var sessionID = events.reversed().flatMap { it.evidence }
        .firstOrNull { it.kind == "external" && it.id.startsWith("chat_session:") }
        ?.id?.removePrefix("chat_session:")
    if (sessionID == null) {
        val title = AgentStore.SESSION_TITLE_PREFIX + task.description
        val runSessions = attempt { api.chatSessions(AgentStore.RUN_SESSION_APP_ID) }.orEmpty()
        // Runs before the run app id were sessions without an app.
        val legacy = if (runSessions.any { it.second == title }) emptyList() else attempt { api.chatSessions() }.orEmpty()
        sessionID = (runSessions + legacy).firstOrNull { it.second == title }?.first
    }
    var partialText = ""
    if (sessionID != null) {
        attempt { api.chatHistory(20, 0, sessionID) }?.let { messages ->
            partialText = messages.lastOrNull { it.sender == ChatMessage.Sender.Omi && RunFailure.fromAnswer(it.text) == null }?.text ?: ""
        }
    }
    histories = histories + (task.id to AgentStore.RunHistory(events, AgentStore.steps(events), partialText, sessionID))
}

internal fun AgentStore.recoveredRun(task: ActionItem, workstream: Workstream, history: AgentStore.RunHistory?): AgentStore.Run {
    val events = history?.events?.takeIf { it.isNotEmpty() } ?: workstream.events
    val lastEvent = events.lastOrNull()
    val lastAgentEvent = events.lastOrNull { it.kind == "agent_update" }
    val result = workstream.summary ?: lastEvent?.summary ?: ""
    val lastActivity = listOfNotNull(workstream.lastActivityAt, lastEvent?.createdAt).maxOrNull()
    val state: AgentStore.RunState = when {
        workstream.status == Workstream.Status.Completed ->
            RunFailure.fromAnswer(result)?.let { AgentStore.RunState.Failed(it.rawValue) } ?: AgentStore.RunState.Done(result)
        lastAgentEvent?.let { RunFailure.fromEvent(it.summary) } != null ->
            AgentStore.RunState.Failed(RunFailure.fromEvent(lastAgentEvent!!.summary)!!.rawValue)
        AgentStore.isStale(lastActivity, now()) -> AgentStore.RunState.Failed(RunFailure.Stopped.rawValue)
        else -> AgentStore.RunState.Working(lastAgentEvent?.summary?.takeIf { AgentStore.isStepEvent(it) } ?: "")
    }
    return AgentStore.Run(
        id = task.id, taskTitle = task.description, workstreamID = workstream.id, state = state,
        steps = history?.steps ?: AgentStore.steps(events),
        partialText = history?.partialText?.ifEmpty { null }
            ?: if (workstream.status == Workstream.Status.Completed) AgentStore.writtenBeforeFailure(result) else "",
        startedAt = lastEvent?.createdAt ?: Instant.EPOCH, sessionID = history?.sessionID, lastProgressAt = lastActivity,
    )
}

/** The agent's own steps among a workstream's events (not the system, artifact or marker events). */
internal fun AgentStore.Companion.steps(events: List<Workstream.Event>): List<String> =
    events.filter { it.kind == "agent_update" }.map { it.summary }.filter { isStepEvent(it) }

/**
 * What the agent wrote before a canned failure was appended ("I'll gather context ... I'm having
 * trouble ..."); empty for a real answer or a bare failure.
 */
internal fun AgentStore.Companion.writtenBeforeFailure(answer: String): String {
    if (RunFailure.fromAnswer(answer) == null) return ""
    val canned = ChatStreamEvent.serviceFailureTexts + listOf(RunFailure.REFUSAL_TEXT, RunFailure.EMPTY_ANSWER_TEXT)
    var text = answer.trim()
    for (suffix in canned) if (text.endsWith(suffix)) text = text.dropLast(suffix.length)
    return text.trim()
}

/** No sign of life for `STALE_AFTER` (no known time at all counts as stale). */
internal fun AgentStore.Companion.isStale(lastActivity: Instant?, now: Instant): Boolean {
    lastActivity ?: return true
    return Duration.between(lastActivity, now) > AgentStore.STALE_AFTER
}

/**
 * A workstream event or stream frame that is one of the agent's steps (not the start, a
 * heartbeat, the result or a failure).
 */
fun AgentStore.Companion.isStepEvent(summary: String): Boolean {
    val text = summary.trim()
    return text.isNotEmpty() && text != AgentStore.STARTED_SUMMARY && text != "Work initiated by the user" && !isHeartbeat(text) &&
        !text.startsWith("Done: ") && RunFailure.fromEvent(text) == null
}

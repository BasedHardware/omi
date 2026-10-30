package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.DeviceToolResult
import com.friend.ios.core.models.Recommendation
import com.friend.ios.core.models.Workstream
import com.friend.ios.core.models.WorkstreamRef
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.generated.OmiAPI
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import java.security.MessageDigest
import java.util.UUID

/**
 * Port of `APIClient+Agent.swift` and the agent half of `APIClient+DeviceTools.swift`: agent
 * bookkeeping on backend workstreams (`routers/workstreams.py`). The backend records, the chat
 * agent works: the client opens a work intent, streams the task through `v2/messages`, and
 * records progress and the result on the workstream (same contract as the desktop app).
 */
interface AgentAPI {
    /** `GET v1/candidates/control` -> account generation for task-intelligence writes. */
    suspend fun accountGeneration(): Int

    /** `POST v1/work-intents` for a task. Idempotent per task. Returns the workstream id. */
    suspend fun startWork(onTask: String, title: String, generation: Int): String

    /** `POST v1/workstreams/{id}/events` -> event id. */
    suspend fun recordWorkstreamEvent(
        ref: WorkstreamRef,
        kind: String,
        summary: String,
        evidence: List<Map<String, String>>,
        idempotencyKey: String,
    ): String

    /** `POST v1/workstreams/{id}/artifacts`: the result, pointing at the chat message that holds it. */
    suspend fun recordResultArtifact(ref: WorkstreamRef, messageID: String, resultText: String, evidenceEventID: String, runID: String)

    /** `PATCH v1/workstreams/{id}` */
    suspend fun updateWorkstream(ref: WorkstreamRef, status: Workstream.Status?, summary: String?)

    /** `GET v1/workstreams/{id}` */
    suspend fun workstream(workstreamID: String): Workstream

    /** `GET v1/what-matters-now` (up to three recommendations; empty is the normal case). */
    suspend fun whatMattersNow(): List<Recommendation>

    /**
     * `POST v1/task-intelligence/feedback`: what the user decided about a recommendation. The
     * backend pauses it (later: a day, dismiss: a month) and learns from it.
     */
    suspend fun sendRecommendationFeedback(recommendation: Recommendation, decision: Recommendation.Decision, generation: Int)

    /** `GET v1/workstreams/{id}/events?after_sequence=`: the whole log, oldest first (paged by 200). */
    suspend fun workstreamEvents(workstreamID: String, afterSequence: Int): List<Workstream.Event>

    /**
     * `POST v2/messages` for an agent run: declares the device tools this phone can run (so the
     * agent can ask mid-run), and reports typed `error:` frames as [ChatStreamEvent.Failed].
     */
    fun streamAgent(text: String, context: ChatContext?, sessionID: String?, deviceTools: List<String>): Flow<ChatStreamEvent>

    /**
     * `POST v2/messages/device-tool/{call_id}/result`. 404 when the call is no longer waiting
     * (the agent timed out or the turn ended).
     */
    suspend fun sendDeviceToolResult(callID: String, result: DeviceToolResult)
}

internal class AgentEndpoints(private val http: HttpCore) : AgentAPI {
    private val chat = ChatEndpoints(http)

    override suspend fun accountGeneration(): Int {
        val text = http.data(Method.GET, "v1/candidates/control")
        return http.decode(OmiAPI.TaskWorkflowControl.serializer(), text).accountGeneration ?: 0
    }

    override suspend fun startWork(onTask: String, title: String, generation: Int): String {
        val body = buildJsonObject {
            put("origin", "task")
            put("task_id", onTask)
            put("title", title)
        }
        val text = http.data(
            Method.POST, "v1/work-intents", body = Body.Json(body.toString()),
            headers = mapOf("Idempotency-Key" to "work-intent:task:$onTask", "X-Account-Generation" to "$generation"),
        )
        return http.decode(OmiAPI.WorkIntentReceipt.serializer(), text).workstreamId
    }

    override suspend fun recordWorkstreamEvent(
        ref: WorkstreamRef,
        kind: String,
        summary: String,
        evidence: List<Map<String, String>>,
        idempotencyKey: String,
    ): String {
        val body = buildJsonObject {
            put("kind", kind)
            put("summary", summary.take(2000))
            putJsonArray("evidence_refs") { evidence.forEach { ref -> addJsonObject { ref.forEach { (k, v) -> put(k, v) } } } }
            put("sensitivity", "normal")
        }
        val text = http.data(
            Method.POST, "v1/workstreams/${ref.id}/events", body = Body.Json(body.toString()),
            headers = mapOf("Idempotency-Key" to idempotencyKey, "X-Account-Generation" to "${ref.generation}"),
        )
        return http.decode(OmiAPI.WorkstreamEvent.serializer(), text).eventId
    }

    override suspend fun recordResultArtifact(ref: WorkstreamRef, messageID: String, resultText: String, evidenceEventID: String, runID: String) {
        val hash = MessageDigest.getInstance("SHA-256").digest(resultText.toByteArray()).joinToString("") { "%02x".format(it) }
        val body = buildJsonObject {
            put("logical_key", "omi-result-$runID")
            put("version", 1)
            put("kind", "chat_answer")
            put("uri", "omi://chat/messages/$messageID")
            put("content_hash", hash)
            put("source_run_id", runID)
            putJsonArray("evidence_event_ids") { add(kotlinx.serialization.json.JsonPrimitive(evidenceEventID)) }
            putJsonArray("evidence_refs") {}
        }
        http.data(
            Method.POST, "v1/workstreams/${ref.id}/artifacts", body = Body.Json(body.toString()),
            headers = mapOf("Idempotency-Key" to "artifact:$runID", "X-Account-Generation" to "${ref.generation}"),
        )
    }

    override suspend fun updateWorkstream(ref: WorkstreamRef, status: Workstream.Status?, summary: String?) {
        val body = buildJsonObject {
            if (status != null) put("status", status.rawValue)
            if (summary != null) put("current_state_summary", summary.take(2000))
        }
        http.data(
            Method.PATCH, "v1/workstreams/${ref.id}", body = Body.Json(body.toString()),
            headers = mapOf("Idempotency-Key" to "workstream-update:${ref.id}:${UUID.randomUUID()}", "X-Account-Generation" to "${ref.generation}"),
        )
    }

    override suspend fun workstream(workstreamID: String): Workstream {
        val detail = http.decode(OmiAPI.WorkstreamDetailProjection.serializer(), http.data(Method.GET, "v1/workstreams/$workstreamID"))
        return Workstream(
            id = detail.workstream.workstreamId,
            title = detail.workstream.title,
            status = Workstream.Status.from(detail.workstream.status.rawValue),
            summary = detail.workstream.currentStateSummary,
            events = detail.recentEvents.sortedBy { it.sequence }.map(WorkstreamMapper::event),
            updatedAt = BackendDate.parse(detail.workstream.updatedAt),
            lastProgressAt = BackendDate.parse(detail.workstream.lastMeaningfulProgressAt),
        )
    }

    override suspend fun whatMattersNow(): List<Recommendation> {
        val projection = http.decode(OmiAPI.WhatMattersNowProjection.serializer(), http.data(Method.GET, "v1/what-matters-now"))
        return projection.recommendations.map(RecommendationMapper::map)
    }

    override suspend fun sendRecommendationFeedback(recommendation: Recommendation, decision: Recommendation.Decision, generation: Int) {
        http.data(
            Method.POST, "v1/task-intelligence/feedback", body = Body.Json(RecommendationMapper.feedbackBody(recommendation, decision).toString()),
            headers = mapOf(
                "Idempotency-Key" to "feedback:${recommendation.id}:${RecommendationMapper.rawValue(decision)}",
                "X-Account-Generation" to "$generation",
            ),
        )
    }

    override suspend fun workstreamEvents(workstreamID: String, afterSequence: Int): List<Workstream.Event> {
        val text = http.data(
            Method.GET, "v1/workstreams/$workstreamID/events",
            query = listOf("after_sequence" to "$afterSequence", "limit" to "200"),
        )
        return http.decode(ListSerializer(OmiAPI.WorkstreamEvent.serializer()), text).sortedBy { it.sequence }.map(WorkstreamMapper::event)
    }

    // The chat stream with no files is exactly the agent's request (`APIClient+DeviceTools.swift`).
    override fun streamAgent(text: String, context: ChatContext?, sessionID: String?, deviceTools: List<String>): Flow<ChatStreamEvent> =
        chat.sendChatMessage(text, emptyList(), context, sessionID, deviceTools)

    override suspend fun sendDeviceToolResult(callID: String, result: DeviceToolResult) {
        val body = buildJsonObject { put("result", DeviceToolFrame.payload(result)) }
        http.data(Method.POST, "v2/messages/device-tool/$callID/result", body = Body.Json(body.toString()))
    }
}

object RecommendationMapper {
    fun map(dto: OmiAPI.Recommendation): Recommendation = Recommendation(
        id = dto.interventionId,
        headline = dto.headline,
        whyNow = dto.whyNow,
        action = dto.recommendedAction,
        taskID = dto.destinationTaskId,
        workstreamID = dto.destinationWorkstreamId,
        goalLabel = dto.goalOrWorkstreamLabel?.ifEmpty { null },
        alternativeAction = dto.alternativeAction?.ifEmpty { null },
        evidencePreview = dto.evidencePreview,
        evidence = dto.evidenceRefs.map { Recommendation.Evidence(kind = it.kind.rawValue, id = it.id) },
        feedbackSubjectKind = dto.feedbackSubjectKind.rawValue,
        feedbackSubjectID = dto.feedbackSubjectId,
        dedupeKey = dto.dedupeKey,
        expiresAt = BackendDate.parse(dto.expiresAt),
    )

    fun rawValue(decision: Recommendation.Decision): String = when (decision) {
        Recommendation.Decision.DoNow -> "doNow"
        Recommendation.Decision.Later -> "later"
        Recommendation.Decision.Dismiss -> "dismiss"
        Recommendation.Decision.Complete -> "complete"
        Recommendation.Decision.AlreadyHandled -> "alreadyHandled"
    }

    /**
     * `FeedbackCreate`: "already handled" is a dismiss with a reason; do now, later and dismiss
     * must name the intervention.
     */
    fun feedbackBody(recommendation: Recommendation, decision: Recommendation.Decision): JsonObject = buildJsonObject {
        put("subject_kind", recommendation.feedbackSubjectKind)
        put("subject_id", recommendation.feedbackSubjectID)
        put("intervention_id", recommendation.id)
        when (decision) {
            Recommendation.Decision.DoNow -> put("action", "do_now")
            Recommendation.Decision.Later -> put("action", "later")
            Recommendation.Decision.Dismiss -> put("action", "dismiss")
            Recommendation.Decision.Complete -> put("action", "complete")
            Recommendation.Decision.AlreadyHandled -> {
                put("action", "dismiss")
                put("reason", "already_handled")
            }
        }
    }
}

object WorkstreamMapper {
    fun event(dto: OmiAPI.WorkstreamEvent): Workstream.Event = Workstream.Event(
        id = dto.eventId,
        kind = dto.kind.rawValue,
        summary = dto.summary,
        createdAt = BackendDate.parse(dto.createdAt),
        sequence = dto.sequence,
        evidence = dto.evidenceRefs.orEmpty().map { Workstream.Event.Evidence(kind = it.kind.rawValue, id = it.id) },
    )
}

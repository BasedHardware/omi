package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.ChatChart
import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.ChatEvidence
import com.friend.ios.core.models.ChatFile
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.job
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import java.io.IOException
import java.net.SocketTimeoutException
import java.time.Instant
import java.util.Base64
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/**
 * One frame of the `POST v2/messages` stream (backend `routers/chat.py`, `utils/retrieval/agentic.py`).
 * Frames are single lines `<prefix><payload>`; newlines inside payloads arrive as `__CRLF__`.
 * Port of `ChatStreamEvent` in `APIClient+Chat.swift`.
 */
sealed interface ChatStreamEvent {
    data class Step(val text: String) : ChatStreamEvent
    data class Delta(val text: String) : ChatStreamEvent
    data object MemorySaved : ChatStreamEvent
    data class Failed(val code: String) : ChatStreamEvent
    data class Done(val message: ChatMessage) : ChatStreamEvent
    /**
     * A `tool:` frame: the agent waits until the app posts this call's result (only sent when
     * the request declared `device_tools`).
     */
    data class DeviceTool(val request: DeviceToolRequest) : ChatStreamEvent

    companion object {
        /**
         * Canned failure texts the agent streams as ordinary answer text
         * (backend `utils/retrieval/agentic.py:247-248, 1080, 1272, 1340`, and the safety guard's
         * tool-call, loop and context limits in `utils/retrieval/safety.py`).
         */
        val serviceFailureTexts = listOf(
            "Sorry, I encountered an error. Please try again.",
            "Unable to complete the response. Please try again.",
            "The response took too long. Please try again.",
            "I'm having trouble finding all the information you need. " +
                "Could you try asking a simpler question or breaking this into separate questions?",
            "I seem to be stuck trying to answer your question. Could you rephrase it in a different way?",
            "That's a lot of information to process at once! Could you narrow down your request? " +
                "Try asking about a smaller time period or being more specific about what you're looking for.",
        )

        fun isServiceFailure(text: String): Boolean = text.trim() in serviceFailureTexts

        fun parse(line: String): ChatStreamEvent? {
            fun payload(prefix: String): String? = if (line.startsWith(prefix)) line.removePrefix(prefix).replace("__CRLF__", "\n") else null
            payload("data: ")?.let { return Delta(it) }
            payload("think: ")?.let { text ->
                // Strip the optional "|app_id:<id>" suffix.
                return Step(text.split("|app_id:").first())
            }
            if (line.startsWith("memory:")) return MemorySaved
            payload("error: ")?.let { text ->
                val message = runCatching { (Json.parseToJsonElement(text) as? JsonObject)?.string("message") }.getOrNull()
                return Failed(message ?: text)
            }
            if (line.startsWith("tool: ")) return DeviceToolFrame.parse(line.removePrefix("tool: "))?.let(::DeviceTool)
            payload("done: ")?.let { encoded ->
                val data = runCatching { Base64.getDecoder().decode(encoded.trim()) }.getOrNull() ?: return null
                return ChatMessageMapper.message(fromJSON = String(data, Charsets.UTF_8))?.let(::Done)
            }
            return null
        }

        /** The machine-readable reason of an `error:` frame (`quota_exceeded`, `timeout`, `server_error` …). */
        fun errorCode(line: String): String? {
            if (!line.startsWith("error: ")) return null
            val obj = runCatching { Json.parseToJsonElement(line.removePrefix("error: ")) as? JsonObject }.getOrNull() ?: return null
            return obj.string("error")
        }
    }
}

/**
 * Port of `APIClient+Chat.swift`, `+ChatExtras.swift`, `+ChatApps.swift` and the chat half of
 * `+Search.swift` (contracts: `backend/routers/chat.py`).
 */
interface ChatAPI {
    /**
     * `POST v2/messages` with photos and files (ids from [uploadChatFile]). Unlike the plain send,
     * a typed `error:` frame arrives as [ChatStreamEvent.Failed] with its code, so the chat can
     * word it. Cold: the request goes out when collected; cancelling the collector cancels the call.
     */
    fun sendChatMessage(
        text: String,
        fileIDs: List<String>,
        context: ChatContext?,
        sessionID: String?,
        deviceTools: List<String>,
    ): Flow<ChatStreamEvent>

    /**
     * `GET v2/messages` with `offset` (counted in visible messages, newest first on the wire;
     * returned oldest first). A page shorter than `limit` is the start of the chat.
     */
    suspend fun chatHistory(limit: Int, offset: Int, sessionID: String?): List<ChatMessage>

    /** `POST v2/chat-sessions`: a separate thread, so agent runs never land in the main chat. */
    suspend fun createChatSession(title: String): String

    /** `GET v2/chat-sessions` (newest first): ids and titles. */
    suspend fun chatSessions(): List<Pair<String, String>>

    /**
     * `GET v2/chat-sessions?app_id=`: one app's chat threads, newest first. The backend always
     * filters by app, so these never include the main chat's sessions or agent runs.
     */
    suspend fun chatSessions(appID: String): List<Pair<String, String>>

    /**
     * `POST v2/chat-sessions` with `app_id`: messages sent into it are answered by that app
     * (the backend reads the app from the session, `utils/chat_session_target.py`).
     */
    suspend fun createChatSession(title: String, appID: String): String

    /** `POST v1/users/analytics/chat_message`: 1 helpful, -1 not helpful (with a reason key), 0 cleared. */
    suspend fun rateChatMessage(id: String, value: Int, reason: String?)

    /**
     * `DELETE v2/messages?chat_session_id=`: empties that one session (it stays) and returns Omi's
     * new greeting. Always scoped: without a session the backend deletes its "current" one.
     */
    suspend fun clearChat(sessionID: String): ChatMessage?

    /** `POST v2/files` (multipart `files`): one photo or document for the next message. */
    suspend fun uploadChatFile(filename: String, mimeType: String, data: ByteArray): ChatFile
}

internal class ChatEndpoints(private val http: HttpCore) : ChatAPI {
    override fun sendChatMessage(
        text: String,
        fileIDs: List<String>,
        context: ChatContext?,
        sessionID: String?,
        deviceTools: List<String>,
    ): Flow<ChatStreamEvent> = flow {
        val body = buildJsonObject {
            put("text", text)
            putJsonArray("file_ids") { fileIDs.forEach { add(it) } }
            put("time_zone", TimeZone.getDefault().id)
            if (context != null) {
                putJsonObject("context") {
                    put("type", context.kind.rawValue)
                    put("id", context.id)
                    put("title", context.title)
                }
            }
            if (deviceTools.isNotEmpty()) putJsonArray("device_tools") { deviceTools.forEach { add(it) } }
        }
        val request = http.request(
            Method.POST, "v2/messages",
            query = sessionID?.let { listOf("chat_session_id" to it) }.orEmpty(),
            body = Body.Json(body.toString()),
            headers = mapOf("X-Omi-Chat-Failure-Protocol" to "1"),
        )
        // "Omi asks" waits for a person; the turn's own budget bounds it server-side.
        val seconds = if (deviceTools.isEmpty()) 180L else 300L
        val client = http.client.newBuilder().callTimeout(seconds, TimeUnit.SECONDS).readTimeout(seconds, TimeUnit.SECONDS).build()
        val call = client.newCall(request)
        val cancel = currentCoroutineContext().job.invokeOnCompletion { call.cancel() }
        try {
            call.execute().use { response ->
                if (response.code !in 200..299) throw APIError.Http(response.code, "")
                val source = response.body?.source() ?: return@use
                while (true) {
                    val line = source.readUtf8Line() ?: break
                    if (line.isEmpty() || line.startsWith(":")) continue
                    val code = ChatStreamEvent.errorCode(line)
                    if (code != null) {
                        emit(ChatStreamEvent.Failed(code))
                    } else {
                        ChatStreamEvent.parse(line)?.let { emit(it) }
                    }
                }
            }
        } catch (e: SocketTimeoutException) {
            throw e
        } catch (e: IOException) {
            if (!currentCoroutineContext().job.isActive) throw CancellationException("chat stream cancelled")
            throw APIError.Transport(e.message ?: e.toString())
        } finally {
            cancel.dispose()
        }
    }.flowOn(Dispatchers.IO)

    override suspend fun chatHistory(limit: Int, offset: Int, sessionID: String?): List<ChatMessage> {
        val query = mutableListOf("limit" to "$limit", "offset" to "$offset")
        if (sessionID != null) query.add("chat_session_id" to sessionID)
        val text = http.data(Method.GET, "v2/messages", query = query)
        val array = runCatching { Json.parseToJsonElement(text) as? JsonArray }.getOrNull() ?: return emptyList()
        return array.mapNotNull { (it as? JsonObject)?.let(ChatMessageMapper::message) }.reversed()
    }

    override suspend fun createChatSession(title: String): String =
        sessionID(http.data(Method.POST, "v2/chat-sessions", body = Body.Json(buildJsonObject { put("title", title.take(120)) }.toString())))

    override suspend fun chatSessions(): List<Pair<String, String>> = sessions(http.data(Method.GET, "v2/chat-sessions"))

    override suspend fun chatSessions(appID: String): List<Pair<String, String>> =
        sessions(http.data(Method.GET, "v2/chat-sessions", query = listOf("app_id" to appID)))

    override suspend fun createChatSession(title: String, appID: String): String {
        val body = buildJsonObject {
            put("title", title.take(120))
            put("app_id", appID)
        }
        return sessionID(http.data(Method.POST, "v2/chat-sessions", body = Body.Json(body.toString())))
    }

    override suspend fun rateChatMessage(id: String, value: Int, reason: String?) {
        val query = mutableListOf("message_id" to id, "value" to "$value")
        if (!reason.isNullOrEmpty()) query.add("reason" to reason)
        http.data(Method.POST, "v1/users/analytics/chat_message", query = query)
    }

    override suspend fun clearChat(sessionID: String): ChatMessage? {
        val text = http.data(Method.DELETE, "v2/messages", query = listOf("chat_session_id" to sessionID))
        return ChatMessageMapper.message(fromJSON = text)
    }

    override suspend fun uploadChatFile(filename: String, mimeType: String, data: ByteArray): ChatFile {
        val text = http.data(Method.POST, "v2/files", body = Body.File("files", filename, mimeType, data))
        val array = runCatching { Json.parseToJsonElement(text) as? JsonArray }.getOrNull()
        return (array?.firstOrNull() as? JsonObject)?.let(ChatMessageMapper::file) ?: throw APIError.Decoding("upload without file")
    }

    private fun sessionID(text: String): String {
        val obj = runCatching { Json.parseToJsonElement(text) as? JsonObject }.getOrNull()
        return obj?.string("id") ?: throw APIError.Decoding("chat session without id")
    }

    private fun sessions(text: String): List<Pair<String, String>> {
        val array = runCatching { Json.parseToJsonElement(text) as? JsonArray }.getOrNull() ?: return emptyList()
        return array.mapNotNull { item -> (item as? JsonObject)?.let { obj -> obj.string("id")?.let { it to (obj.string("title") ?: "") } } }
    }
}

/** Port of `ChatMessageMapper` (`APIClient+Chat.swift` + `+ChatExtras.swift`): backend `Message` JSON. */
object ChatMessageMapper {
    fun message(fromJSON: String): ChatMessage? =
        runCatching { Json.parseToJsonElement(fromJSON) as? JsonObject }.getOrNull()?.let(::message)

    fun message(obj: JsonObject): ChatMessage? {
        val id = obj.string("id") ?: return null
        val references = obj.elements("memories").mapNotNull { element ->
            val memory = element as? JsonObject ?: return@mapNotNull null
            val memoryID = memory.string("id") ?: return@mapNotNull null
            val structured = memory["structured"] as? JsonObject
            ChatMessage.Reference(
                conversationID = memoryID,
                title = structured?.string("title") ?: "",
                emoji = structured?.string("emoji"),
                createdAt = BackendDate.parse(memory.string("created_at")),
            )
        }
        val message = ChatMessage(
            id = id,
            text = obj.string("text") ?: "",
            sender = if (obj.string("sender") == "human") ChatMessage.Sender.User else ChatMessage.Sender.Omi,
            createdAt = BackendDate.parse(obj.string("created_at")) ?: Instant.now(),
            references = references,
        )
        return withExtras(message, obj)
    }

    /** Rating, follow-up chip, chart and files of a stored or streamed message (backend `Message`). */
    fun withExtras(message: ChatMessage, obj: JsonObject): ChatMessage {
        // A push carries the blocks as a JSON string; the mapper reads both that and the array.
        val rawBlocks = obj["content_blocks"]
        val blocks = (rawBlocks as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
        val envelope = obj["evidence"] as? JsonObject
        return message.copy(
            serverID = message.id,
            rating = obj.number("rating")?.toInt(),
            followUp = blocks.firstOrNull { it.string("type") == "followUp" }?.string("text"),
            chart = (obj["chart_data"] as? JsonObject)?.let(::chart),
            files = obj.elements("files").mapNotNull { (it as? JsonObject)?.let(::file) },
            evidence = envelope?.elements("references").orEmpty().mapNotNull { (it as? JsonObject)?.let(::evidence) },
            blocks = ChatBlockMapper.blocks(rawBlocks),
            kind = ChatMessage.Kind.from(obj.string("type")),
        )
    }

    /** One source reference (backend `ChatEvidenceReference`); a reference without an id is dropped. */
    fun evidence(obj: JsonObject): ChatEvidence? {
        val id = obj.string("id")?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        fun text(key: String) = obj.string(key)?.takeIf { it.isNotBlank() }
        return ChatEvidence(
            id = id,
            kind = ChatEvidence.Kind.from(obj.string("kind")),
            state = ChatEvidence.State.from(obj.string("state")),
            title = text("title"),
            summary = text("summary"),
            conversationID = text("conversation_id"),
            segmentID = text("segment_id"),
            startMs = obj.number("start_ms")?.toInt(),
            endMs = obj.number("end_ms")?.toInt(),
            capturedAtMs = obj.number("captured_at_ms")?.toLong(),
        )
    }

    fun file(obj: JsonObject): ChatFile? {
        val id = obj.string("id") ?: return null
        val thumbnail = obj.string("thumbnail")?.takeIf { it.startsWith("http") }
        return ChatFile(id = id, name = obj.string("name") ?: "", mimeType = obj.string("mime_type") ?: "", thumbnailURL = thumbnail)
    }

    fun chart(obj: JsonObject): ChatChart? {
        val series = obj.elements("datasets").mapNotNull { element ->
            val set = element as? JsonObject ?: return@mapNotNull null
            val points = set.elements("data_points").mapNotNull { p ->
                val point = p as? JsonObject ?: return@mapNotNull null
                val label = point.string("label") ?: return@mapNotNull null
                val value = point.number("value") ?: return@mapNotNull null
                ChatChart.Point(label, value)
            }
            if (points.isEmpty()) null else ChatChart.Series(set.string("label") ?: "", points, set.string("color"))
        }
        if (series.isEmpty()) return null
        return ChatChart(
            kind = ChatChart.Kind.from(obj.string("chart_type")) ?: ChatChart.Kind.Bar,
            title = obj.string("title") ?: "",
            xLabel = obj.string("x_label"),
            yLabel = obj.string("y_label"),
            series = series,
        )
    }
}


private fun JsonObject.number(key: String): Double? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.let { it.doubleOrNull ?: it.longOrNull?.toDouble() }

private fun JsonObject.elements(key: String): List<JsonElement> = (this[key] as? JsonArray).orEmpty()

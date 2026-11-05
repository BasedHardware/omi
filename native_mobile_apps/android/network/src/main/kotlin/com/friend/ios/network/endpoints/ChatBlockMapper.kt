package com.friend.ios.network.endpoints

import com.friend.ios.core.models.ChatBlock
import com.friend.ios.core.models.ChatMemoryReview
import com.friend.ios.core.models.ChatQuestion
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Port of `ChatBlockMapper` (`OmiNetwork/Mappers/ChatBlockMapper.swift`): `content_blocks` of a chat
 * message (backend `models/chat.py` stores them verbatim; the vocabulary is the macOS agent's
 * `ConversationContentBlock`, mirrored by Flutter's `chat_content_block.dart`). Two dialects
 * arrive: camelCase (desktop, agent runs) and snake_case (chat-first specs), so every field is read
 * in both. A push carries the array as a JSON string. A malformed block keeps its fallback line as
 * [ChatBlock.Kind.Other]; the follow-up and evidence blocks are read elsewhere and left out.
 */
internal object ChatBlockMapper {
    fun blocks(value: JsonElement?): List<ChatBlock> {
        val raw: List<JsonObject> = when (value) {
            is JsonArray -> value.map { it as? JsonObject ?: return emptyList() }
            is JsonPrimitive -> {
                if (!value.isString) return emptyList()
                val parsed = JsonAccess.parse(value.content) as? JsonArray ?: return emptyList()
                parsed.map { it as? JsonObject ?: return emptyList() }
            }
            else -> return emptyList()
        }
        return raw.mapIndexedNotNull { index, json -> block(json, index) }
    }

    /** Types that never become a block: the follow-up chip and the evidence envelope. */
    val skippedTypes: Set<String> = setOf("followUp", "follow_up", "evidence", "evidence_envelope")

    fun block(json: JsonObject, index: Int = 0): ChatBlock? {
        val type = string(json, "type") ?: return null
        if (type in skippedTypes) return null
        val fallback = fallbackText(json)
        val id = string(json, "id") ?: "block-$index"
        val kind = if (string(json, "id") == null) null else kind(type, json)
        // Malformed: only its line, and nothing at all when the line is empty.
        return kind?.let { ChatBlock(id = id, kind = it, fallbackText = fallback) }
            ?: if (fallback.isEmpty()) null else ChatBlock(id = id, kind = ChatBlock.Kind.Other(type), fallbackText = fallback)
    }

    private fun kind(type: String, json: JsonObject): ChatBlock.Kind? = when (type) {
        "text" -> ChatBlock.Kind.Text(string(json, "text") ?: "")
        "taskCard", "task_card" -> string(json, "taskId", "task_id")?.let { ChatBlock.Kind.Task(it) }
        "goalLink", "goal_link" -> {
            val goal = string(json, "goalId", "goal_id")
            val summary = string(json, "summary")
            if (goal != null && summary != null) ChatBlock.Kind.Goal(goal, summary) else null
        }
        "memoryLink", "memory_link" -> {
            val memory = string(json, "memoryId", "memory_id")
            val summary = string(json, "summary")
            if (memory != null && summary != null) ChatBlock.Kind.Memory(memory, summary) else null
        }
        "conversationLink", "conversation_link", "captureLink", "capture_link" -> {
            val conversation = string(json, "conversationId", "conversation_id")
            val summary = string(json, "summary")
            if (conversation == null || summary == null) {
                null
            } else {
                val items = (json["recommendedActionItems"] ?: json["recommended_action_items"]) as? JsonArray
                val hints = items.orEmpty().mapNotNull { element ->
                    val item = element as? JsonObject ?: return@mapNotNull null
                    string(item, "description")?.let { ChatBlock.ActionItemHint(it, string(item, "taskId", "task_id")) }
                }
                ChatBlock.Kind.Conversation(
                    conversationID = conversation, summary = summary, actionItems = hints, isCapture = type.startsWith("capture"),
                )
            }
        }
        "discoveryCard", "discovery_card" -> ChatBlock.Kind.Discovery(
            title = string(json, "title") ?: "",
            summary = string(json, "summary") ?: "",
            fullText = string(json, "fullText", "full_text") ?: "",
        )
        "questionCard", "question_card" -> question(json)?.let(ChatBlock.Kind::Question)
        "agentSpawn", "agent_spawn" -> {
            val hasRun = string(json, "sessionId", "session_id") != null && string(json, "runId", "run_id") != null
            if (!hasRun) {
                null
            } else {
                ChatBlock.Kind.AgentRun(
                    title = string(json, "title") ?: "",
                    detail = string(json, "objective") ?: "",
                    status = ChatBlock.AgentRunStatus.Running,
                )
            }
        }
        "agentCompletion", "agent_completion" -> {
            // Older stored completions carry no status: they were completed.
            val status = ChatBlock.AgentRunStatus.fromCompletionStatus(string(json, "status") ?: "completed")
            ChatBlock.Kind.AgentRun(
                title = string(json, "title") ?: "", detail = string(json, "output") ?: "", status = status,
            )
        }
        "memoryReviewCard", "memory_review_card" -> memoryReview(json)?.let(ChatBlock.Kind::MemoryReview)
        else -> ChatBlock.Kind.Other(type)
    }

    /** Needs the question, its subject and at least one option with an id and a label. */
    private fun question(json: JsonObject): ChatQuestion? {
        val questionID = string(json, "questionId", "question_id") ?: return null
        val text = string(json, "text") ?: return null
        val subject = json["subject"] as? JsonObject ?: return null
        if (string(subject, "kind") == null || string(subject, "id") == null) return null
        val rawOptions = json["options"] as? JsonArray ?: return null
        val options = rawOptions.mapNotNull { element ->
            val option = element as? JsonObject ?: return@mapNotNull null
            val id = string(option, "optionId", "option_id") ?: return@mapNotNull null
            val label = string(option, "label") ?: return@mapNotNull null
            ChatQuestion.Option(id = id, label = label, preparedAnswer = string(option, "preparedAnswer", "prepared_answer") ?: label)
        }
        if (options.isEmpty()) return null
        return ChatQuestion(
            questionID = questionID, text = text, options = options,
            selectedOptionID = string(json, "selectedOptionId", "selected_option_id"),
        )
    }

    /** Items without an id or text are dropped; a card with none left is no card. */
    private fun memoryReview(json: JsonObject): ChatMemoryReview? {
        val items = (json["items"] as? JsonArray).orEmpty().mapNotNull { element ->
            val item = element as? JsonObject ?: return@mapNotNull null
            val id = string(item, "memoryId", "memory_id") ?: return@mapNotNull null
            val content = string(item, "content") ?: return@mapNotNull null
            ChatMemoryReview.Item(memoryID = id, content = content, category = string(item, "category") ?: "")
        }
        if (items.isEmpty()) return null
        return ChatMemoryReview(summaryID = string(json, "summaryId", "summary_id") ?: "", date = string(json, "date") ?: "", allItems = items)
    }

    /**
     * The one line a block reads as without its card (Flutter `ServerMessage._blockFallbackText`,
     * which follows the desktop's projection), so a turn whose text is only these lines can show
     * the cards instead of repeating them.
     */
    fun fallbackText(json: JsonObject): String {
        fun value(camel: String, snake: String? = null): String = string(json, camel, snake)?.trim() ?: ""
        fun labelled(label: String, details: List<String>): String {
            val unique = LinkedHashSet<String>()
            for (detail in details) if (detail.isNotEmpty()) unique.add(detail)
            return if (unique.isEmpty()) label else (listOf(label) + unique).joinToString(" - ")
        }
        return when (string(json, "type") ?: "") {
            "text" -> value("text").ifEmpty { "Message" }
            "toolCall", "tool_call" -> labelled("Tool", listOf(value("name"), value("output"), value("inputSummary", "input_summary")))
            "thinking" -> labelled("Thinking", listOf(value("text")))
            "discoveryCard", "discovery_card" -> labelled("Discovery", listOf(value("title"), value("summary")))
            "questionCard", "question_card" -> value("text").ifEmpty { "Question" }
            "memoryReviewCard", "memory_review_card", "followUp", "follow_up", "evidence", "evidence_envelope" -> ""
            "taskCard", "task_card" -> "Task"
            "goalLink", "goal_link" -> labelled("Goal", listOf(value("summary")))
            "captureLink", "capture_link" -> labelled("Capture", listOf(value("summary")))
            "conversationLink", "conversation_link" -> labelled("Meeting notes ready", listOf(value("summary")))
            "memoryLink", "memory_link" -> labelled("Memory", listOf(value("summary")))
            "citation" -> labelled("Source", listOf(value("title"), value("preview")))
            "agentSpawn", "agent_spawn" -> labelled("Agent started", listOf(value("title"), value("objective")))
            "agentCompletion", "agent_completion" -> labelled("Agent completed", listOf(value("title"), value("output")))
            else -> labelled("Chat item", listOf(value("title"), value("summary"), value("text")))
        }
    }

    /** A non-blank string under the camelCase key, else the snake_case one. */
    private fun string(json: JsonObject, camel: String, snake: String? = null): String? {
        val value = json[camel] ?: snake?.let { json[it] }
        val text = (value as? JsonPrimitive)?.takeIf { it.isString }?.content ?: return null
        return text.takeIf { it.isNotBlank() }
    }
}

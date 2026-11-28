package com.friend.ios.core.models

/**
 * Port of `ChatBlock.swift`: one structured part of an answer (backend `Message.content_blocks`,
 * the vocabulary of the macOS agent's `ConversationContentBlock`): a task, a link to a goal, memory
 * or conversation, a discovery, a question with prepared answers, a background run, or the day's
 * memories to review. Every block keeps the line a client that cannot draw it shows instead
 * ([fallbackText]).
 */
data class ChatBlock(
    val id: String,
    val kind: Kind,
    /**
     * The block as one line of text (the desktop's synthesized fallback); empty for blocks that
     * say nothing on their own (a review card draws its own heading).
     */
    val fallbackText: String,
) {
    sealed interface Kind {
        /** Prose that belongs to the answer. */
        data class Text(val text: String) : Kind

        /** A task by id, drawn live from the task list. */
        data class Task(val taskID: String) : Kind

        data class Goal(val goalID: String, val summary: String) : Kind

        data class Memory(val memoryID: String, val summary: String) : Kind

        /** A conversation (`conversationLink`) or the capture an answer came from (`captureLink`). */
        data class Conversation(
            val conversationID: String,
            val summary: String,
            val actionItems: List<ActionItemHint>,
            val isCapture: Boolean,
        ) : Kind

        data class Discovery(val title: String, val summary: String, val fullText: String) : Kind

        data class Question(val question: ChatQuestion) : Kind

        /** A background run that started (`agentSpawn`) or ended (`agentCompletion`). */
        data class AgentRun(val title: String, val detail: String, val status: AgentRunStatus) : Kind

        /** "Things I learned today": memories to confirm, drop or correct (`memoryReviewCard`). */
        data class MemoryReview(val review: ChatMemoryReview) : Kind

        /** Thinking, a tool call, a citation, a malformed or unknown block: only its fallback line. */
        data class Other(val type: String) : Kind
    }

    /** An action item a conversation link recommends (plain text; the task exists when [taskID] is set). */
    data class ActionItemHint(val description: String, val taskID: String?)

    enum class AgentRunStatus {
        Running,
        Completed,
        Cancelled,
        TimedOut,
        Failed,
        ;

        companion object {
            /** Only explicit successful states read as completed; anything unknown reads as failed. */
            fun fromCompletionStatus(raw: String): AgentRunStatus = when (raw.trim().lowercase()) {
                "completed", "succeeded", "success" -> Completed
                "cancelled", "canceled", "stopped" -> Cancelled
                "timed_out", "timedout", "timeout" -> TimedOut
                else -> Failed
            }
        }
    }
}

/**
 * Port of `ChatQuestion`: a question Omi asks with answers ready to tap (`questionCard`). An
 * answered one keeps the question readable and shows only the chosen answer.
 */
data class ChatQuestion(
    val questionID: String,
    val text: String,
    val options: List<Option>,
    val selectedOptionID: String?,
) {
    data class Option(
        val id: String,
        val label: String,
        /** What is sent when it is tapped (the label when the block has none). */
        val preparedAnswer: String,
    )

    /** The answers to show: all of them, or only the chosen one once answered. */
    val visibleOptions: List<Option>
        get() = selectedOptionID?.let { chosen -> options.filter { it.id == chosen } } ?: options

    val isAnswered: Boolean get() = selectedOptionID != null
}

/**
 * Port of `ChatMemoryReview`: up to three memories the day produced, by id and the text the recap
 * showed (`backend/utils/memory/learned_today.py`). The verdicts live on the memories themselves.
 */
data class ChatMemoryReview(
    val summaryID: String,
    /** The recap's local day (`yyyy-MM-dd`). */
    val date: String,
    /** Every row the wire carried; the card draws [items]. */
    private val allItems: List<Item>,
) {
    /** The rows the card shows: never more than [maxItems], as iOS caps in its initializer. */
    val items: List<Item> = allItems.take(maxItems)

    data class Item(
        val memoryID: String,
        val content: String,
        val category: String,
    ) {
        val id: String get() = memoryID
    }

    companion object {
        /** The card never shows more than this many rows. */
        const val maxItems = 3
    }
}

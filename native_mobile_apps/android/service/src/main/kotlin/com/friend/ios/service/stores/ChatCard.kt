package com.friend.ios.service.stores

/**
 * Port of `ChatStore+Cards.swift`. A card the app draws under an answer, from what the agent did
 * (never from model markup, so a web page or an answer cannot fake one): a missing connection, a
 * task Omi added or ticked off.
 */
sealed interface ChatCard {
    /** The answer failed on a connection that is missing (`google_calendar`, `gmail`, `apple_health`). */
    data class Connect(val integration: String) : ChatCard
    data class TaskAdded(val taskID: String, val title: String) : ChatCard
    data class TaskCompleted(val taskID: String, val title: String) : ChatCard

    val id: String
        get() = when (this) {
            is Connect -> "connect:$integration"
            is TaskAdded -> "added:$taskID"
            is TaskCompleted -> "done:$taskID"
        }
}

/**
 * The task list as the chat sees it, to show what the agent added or ticked off. `TasksStore`
 * (another area) is adapted to this by the app shell; the chat never depends on it directly.
 */
interface ChatTasks {
    /** One task: id, its words, whether it is done. */
    data class Task(val id: String, val description: String, val isCompleted: Boolean)

    val tasks: List<Task>
    /** Set when the last action failed. */
    val lastError: String?
    suspend fun load()
    suspend fun delete(id: String)
    suspend fun setCompleted(id: String, completed: Boolean)
}

/** Reading cards out of a finished turn. Pure, so the rules are tested on the backend's own texts. */
object ChatCardDetector {
    /**
     * The connections the backend names when a tool cannot run (`calendar_tools.py`,
     * `gmail_tools.py`, `apple_health_tools.py`: "Google Calendar is not connected. Please connect …").
     */
    val connections: List<Pair<String, List<String>>> = listOf(
        "google_calendar" to listOf("google calendar", "google kalender", "google-kalender", "your calendar", "deinen kalender", "dein kalender"),
        "gmail" to listOf("gmail", "google account", "google-konto", "google konto"),
        "apple_health" to listOf("apple health", "apple health app", "health app"),
    )

    /** How an answer says it is not there. */
    val missingPhrases = listOf(
        "is not connected", "isn't connected", "not connected", "is not linked", "isn't linked", "not linked",
        "please connect", "connect your", "need to connect", "needs to be connected", "don't have access", "do not have access",
        "nicht verbunden", "nicht verknüpft", "verbinde ", "verbinden", "keinen zugriff",
    )

    /** Connections the answer (or a step) says are missing, in the order of [connections]. */
    fun missingConnections(text: String, steps: List<String> = emptyList()): List<String> {
        val sentences = (listOf(text) + steps)
            .flatMap { it.lowercase().split('.', '!', '?', '\n') }
            .map { it.replace("’", "'") }
        return connections.mapNotNull { (id, names) ->
            val named = sentences.any { sentence -> names.any { sentence.contains(it) } && missingPhrases.any { sentence.contains(it) } }
            if (named) id else null
        }
    }

    /**
     * The agent touched tasks: its steps name the task tools (`agentic.py` display names
     * "Creating action item" / "Updating action item", or the raw tool names).
     */
    fun touchedTasks(steps: List<String>): Boolean = steps.any { raw ->
        val step = raw.lowercase()
        step.contains("create_action_item") || step.contains("update_action_item") ||
            (step.contains("action item") && (step.contains("creat") || step.contains("updat")))
    }

    /** Tasks that appeared or were ticked off between the two lists. */
    fun taskChanges(before: List<ChatTasks.Task>, after: List<ChatTasks.Task>): List<ChatCard> {
        val previous = LinkedHashMap<String, ChatTasks.Task>().also { map -> before.forEach { map.putIfAbsent(it.id, it) } }
        val cards = mutableListOf<ChatCard>()
        for (task in after) {
            val old = previous[task.id]
            if (old != null) {
                if (!old.isCompleted && task.isCompleted) cards.add(ChatCard.TaskCompleted(task.id, task.description))
            } else {
                cards.add(ChatCard.TaskAdded(task.id, task.description))
            }
        }
        return cards
    }
}

package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.ChatFile
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.ChatQuote
import com.friend.ios.core.models.OmiApp
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.AppsAPI
import com.friend.ios.network.endpoints.ChatAPI
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.launch
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.time.Instant
import java.util.UUID

/**
 * Port of `ChatStore.swift` (+ `+Thread`, `+Extras`, `+Cards`, `+Apps`): the conversation with
 * Omi. Mirrors `message_provider.dart`. Depends on [ChatAPI] only, so tests use a small fake.
 */
class ChatStore(
    internal val api: ChatAPI,
    internal val preferences: Preferences,
    internal val scope: CoroutineScope,
    /** The app list, for the chat apps (the app's client serves both; test fakes may not). */
    internal val apps: AppsAPI? = api as? AppsAPI,
) {
    var messages: List<ChatMessage> by mutableStateOf(emptyList())
        internal set
    var isStreaming: Boolean by mutableStateOf(false)
        private set
    var currentStep: String? by mutableStateOf(null)
        private set
    var hasLoaded: Boolean by mutableStateOf(false)
        private set
    /** History could not be loaded; the screen offers a retry. */
    var historyFailed: Boolean by mutableStateOf(false)
        private set
    /** Older messages exist on the backend (the last page came back full). */
    var hasEarlier: Boolean by mutableStateOf(false)
        internal set
    var isLoadingEarlier: Boolean by mutableStateOf(false)
        private set
    var context: ChatContext? by mutableStateOf(null)
    /** The message the next question replies to (long press or swipe "Reply"); sent as a quote. */
    var replyingTo: ChatMessage? by mutableStateOf(null)
    /** Photos and files picked for the next message. */
    var attachments: List<PendingAttachment> by mutableStateOf(emptyList())
        internal set
    /** The phone reports no connection (the screen keeps this current): failures read as offline. */
    var networkUnavailable: Boolean by mutableStateOf(false)
    /** A reply finished as a real answer (the screen reads it aloud). */
    var onAnswer: ((ChatMessage) -> Unit)? = null
    /** The chat app this chat talks to; null is Omi itself. */
    var chatApp: OmiApp? by mutableStateOf(null)
        internal set
    /** The user's enabled apps that can chat (the header's "Talk to…" menu). */
    var chatApps: List<OmiApp> by mutableStateOf(emptyList())
        internal set
    /**
     * A device tool call Omi is waiting on in the chat ("Omi asks"); answered with
     * `answerDeviceTool` (`ChatStoreDeviceTools.kt`). Only arrives once the chat declares tools.
     */
    var pendingDeviceTool: PendingDeviceTool? by mutableStateOf(null)
        internal set
    /** The phone's side of the device tools (the app supplies it); null declares none. */
    var deviceTools: com.friend.ios.core.models.DeviceToolPerforming? = null
    /** The answer the pending "Omi asks" belongs to (its card shows under it). */
    var pendingDeviceToolMessageID: String? by mutableStateOf(null)
        internal set
    /** Answers during which Omi asked something (the thread's "Approvals" filter). */
    var askedMessageIDs: Set<String> by mutableStateOf(emptySet())
        internal set
    /** The task list, to show what the agent added or ticked off. */
    var tasks: ChatTasks? = null
    /** Cards drawn under answers, by message id. */
    var cardsByMessage: Map<String, List<ChatCard>> by mutableStateOf(emptyMap())
        internal set
    /** Cards the user took back, never shown again this session. */
    internal val undoneCards = mutableSetOf<String>()

    internal var streamJob: Job? = null
    private var loadJob: Job? = null
    /** Bumped on every switch of chat app: a load for the previous one is discarded. */
    private var scopeGeneration = 0
    internal var sessionID: String? = null
    private var stopped = false
    private val pageSize = 50
    /** Messages fetched from the backend so far: the next older page starts here. */
    internal var fetchedCount = 0

    /** Loads once; concurrent callers (the screen, a send) share the same load. */
    suspend fun loadHistory() {
        if (hasLoaded) return
        loadJob?.let {
            it.join()
            return
        }
        val generation = scopeGeneration
        val job = scope.launch(start = CoroutineStart.LAZY) {
            val resolved = resolveSession()
            if (generation != scopeGeneration) return@launch
            sessionID = resolved
            try {
                val history = api.chatHistory(pageSize, 0, sessionID)
                if (generation != scopeGeneration) return@launch
                // Prepend: a send may already have added local messages while this loaded.
                prepend(history)
                historyFailed = false
                hasLoaded = true
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                historyFailed = true
            }
        }
        loadJob = job
        job.join()
        if (loadJob === job) loadJob = null
    }

    /**
     * The page before the oldest loaded message (call when the top of the chat appears).
     * Offsets count from the newest message, so messages sent since shift the page: the overlap
     * is dropped by id, and nothing in between is skipped.
     */
    suspend fun loadEarlier() {
        if (!hasLoaded || !hasEarlier || isLoadingEarlier) return
        isLoadingEarlier = true
        try {
            val page = try {
                api.chatHistory(pageSize, fetchedCount, sessionID)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                return
            }
            prepend(page)
        } finally {
            isLoadingEarlier = false
        }
    }

    private fun prepend(page: List<ChatMessage>) {
        fetchedCount += page.size
        hasEarlier = page.size == pageSize
        val known = messages.map { it.id }.toSet()
        val hidden = preferences.strings(NativeKey.HiddenChatMessages).toSet()
        val older = page.filter { it.id !in known && it.id !in hidden }.map(::marked)
        messages = older + messages
        collectConnectCards(older)
    }

    suspend fun retryHistory() {
        historyFailed = false
        loadHistory()
    }

    /** Starts over for another chat app: its own history, session and earlier pages. */
    internal fun resetForScope() {
        scopeGeneration += 1
        streamJob?.cancel()
        loadJob?.cancel()
        loadJob = null
        messages = emptyList()
        attachments = emptyList()
        cardsByMessage = emptyMap()
        replyingTo = null
        askedMessageIDs = emptySet()
        pendingDeviceTool = null
        pendingDeviceToolMessageID = null
        hasLoaded = false
        historyFailed = false
        hasEarlier = false
        fetchedCount = 0
        sessionID = null
        isStreaming = false
        currentStep = null
        stopped = false
    }

    /**
     * The backend treats the newest session without an app as "current" (voice questions,
     * integration messages and greetings land there). Agent runs open theirs under
     * `AgentStore.RUN_SESSION_APP_ID`, so they are never listed here; older runs were sessions
     * without an app. The main chat pins one session: the newest that is not a run (known
     * locally, or marked in its title by any device), and every send names it.
     */
    internal suspend fun resolveMainSession(): String? {
        val agentSessions = preferences.strings(NativeKey.AgentChatSessionIDs).toSet()
        val pinned = preferences.string(NativeKey.MainChatSessionID)
        val sessions = try {
            api.chatSessions()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // Offline: trust the pin unless it is known to be a run.
            return pinned?.takeIf { it !in agentSessions }
        }
        val chats = sessions.filter { it.first !in agentSessions && !it.second.startsWith(AgentStore.SESSION_TITLE_PREFIX) }
        if (pinned != null && chats.any { it.first == pinned }) return pinned
        chats.firstOrNull()?.let { main ->
            preferences.set(NativeKey.MainChatSessionID, main.first)
            return main.first
        }
        // No chat yet: open one, so sends never land in an agent run's session.
        val created = try {
            api.createChatSession("Omi")
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return null
        }
        preferences.set(NativeKey.MainChatSessionID, created)
        return created
    }

    /** Sends [text] with the uploaded attachments (none while one is still uploading). */
    fun send(text: String) {
        if (isUploading) return
        val files = attachments.mapNotNull { it.file }
        // A reply carries its quote in front (`ChatQuote`); the thread draws it above the question.
        val trimmed = text.trim()
        val quoted = replyingTo?.let { ChatQuote.replyingTo(it).prefixing(trimmed) } ?: trimmed
        if (!send(if (trimmed.isEmpty()) trimmed else quoted, files)) return
        attachments = emptyList()
        replyingTo = null
    }

    internal fun send(text: String, files: List<ChatFile>): Boolean {
        val trimmed = text.trim()
        if (trimmed.isEmpty() || isStreaming) return false
        val generation = scopeGeneration
        val placeholderID = "pending-${UUID.randomUUID()}"
        messages = messages +
            ChatMessage(id = "local-${UUID.randomUUID()}", text = trimmed, sender = ChatMessage.Sender.User, createdAt = Instant.now(), files = files) +
            ChatMessage(id = placeholderID, text = "", sender = ChatMessage.Sender.Omi, createdAt = Instant.now())
        isStreaming = true
        currentStep = null
        stopped = false
        streamJob = scope.launch { stream(trimmed, files, placeholderID, generation) }
        return true
    }

    /**
     * One turn into the pinned session, declaring the device tools (an app's chat declares
     * none), then the cards for what the turn did.
     */
    private suspend fun stream(text: String, files: List<ChatFile>, placeholderID: String, generation: Int, onFirstAnswer: (() -> Unit)? = null) {
        if (!hasLoaded) {
            try {
                loadHistory()
            } catch (e: CancellationException) {
                stopped = true
            }
        }
        val tasksBefore = tasks?.tasks
        val tools = if (chatApp == null) DeviceToolResolver.declaredTools(deviceTools) else emptyList()
        var answering = false
        if (!stopped) {
            try {
                api.sendChatMessage(text, files.map { it.id }, context, sessionID, tools)
                    .takeWhile { generation == scopeGeneration }
                    .collect { event ->
                        if (!answering && event is ChatStreamEvent.Delta) {
                            answering = true
                            onFirstAnswer?.invoke()
                        }
                        apply(event, placeholderID)
                    }
            } catch (e: CancellationException) {
                stopped = true
            } catch (e: Exception) {
                markFailed(placeholderID, failure(e, networkUnavailable))
            }
        }
        if (generation != scopeGeneration) return
        finish(placeholderID)
        try {
            collectCards(placeholderID, tasksBefore)
        } catch (e: CancellationException) {
            // Stopped: the cards read from the text are already there.
        }
    }

    /** Stop generating: what arrived stays, marked as stopped (not as an error). */
    fun cancel() {
        stopped = true
        streamJob?.cancel()
    }

    /** Asks the question behind a failed answer again, with the same photos and files. */
    fun retry(messageID: String) {
        if (isStreaming) return
        val index = messages.indexOfFirst { it.id == messageID }
        if (index < 0) return
        val question = messages.subList(0, index).lastOrNull { it.sender == ChatMessage.Sender.User } ?: return
        val questionIndex = messages.indexOf(question)
        messages = messages.filterIndexed { i, _ -> i !in questionIndex..index }
        send(question.text, question.files)
    }

    private fun update(id: String, change: (ChatMessage) -> ChatMessage) {
        messages = messages.map { if (it.id == id) change(it) else it }
    }

    private fun apply(event: ChatStreamEvent, placeholderID: String) {
        if (messages.none { it.id == placeholderID }) return
        when (event) {
            is ChatStreamEvent.Step -> {
                currentStep = event.text
                update(placeholderID) { it.copy(steps = it.steps + event.text) }
            }
            is ChatStreamEvent.Delta -> {
                currentStep = null
                update(placeholderID) { it.copy(text = it.text + event.text) }
            }
            is ChatStreamEvent.Failed -> markFailed(placeholderID, failure(forStreamCode = event.code, offline = networkUnavailable))
            is ChatStreamEvent.Done -> update(placeholderID) { current ->
                // Keep the local id: a new identity would rebuild the bubble as it finishes.
                val message = event.message
                var next = current.copy(
                    text = message.text.ifEmpty { current.text },
                    references = message.references,
                    evidence = message.evidence,
                    serverID = message.serverID ?: message.id,
                    followUp = message.followUp,
                    chart = message.chart,
                    blocks = message.blocks,
                    kind = message.kind,
                )
                if (ChatStreamEvent.isServiceFailure(next.text) && next.failure == null) next = next.copy(failure = failure(forCanned = next.text))
                next
            }
            ChatStreamEvent.MemorySaved -> Unit
            is ChatStreamEvent.DeviceTool -> {
                askedMessageIDs = askedMessageIDs + placeholderID
                receive(event.request, placeholderID)
            }
        }
    }

    sealed interface VoiceAnswer {
        data class Answered(val text: String) : VoiceAnswer
        data object NoSpeech : VoiceAnswer
        data object Failed : VoiceAnswer
    }

    /**
     * A spoken question the phone already transcribed (Ask Omi from the Omi): asked like a typed
     * one in the main chat and awaited, so the caller can show or read the answer.
     */
    suspend fun ask(question: String, onFirstAnswer: () -> Unit = {}): VoiceAnswer {
        val trimmed = question.trim()
        if (trimmed.isEmpty()) return VoiceAnswer.NoSpeech
        if (isStreaming) return VoiceAnswer.Failed
        if (chatApp != null) talk(null)
        val placeholderID = "pending-${UUID.randomUUID()}"
        messages = messages +
            ChatMessage(id = "voice-${UUID.randomUUID()}", text = trimmed, sender = ChatMessage.Sender.User, createdAt = Instant.now()) +
            ChatMessage(id = placeholderID, text = "", sender = ChatMessage.Sender.Omi, createdAt = Instant.now())
        isStreaming = true
        currentStep = null
        stopped = false
        stream(trimmed, emptyList(), placeholderID, scopeGeneration, onFirstAnswer)
        val answer = messages.firstOrNull { it.id == placeholderID }
        return if (answer == null || answer.failure != null) VoiceAnswer.Failed else VoiceAnswer.Answered(answer.text)
    }

    /**
     * Quota, offline and timeout keep their own wording; anything else is "could not answer", or
     * "interrupted" once part of the answer arrived.
     */
    private fun markFailed(placeholderID: String, failure: ChatMessage.Failure) = update(placeholderID) {
        if (failure == ChatMessage.Failure.CouldNotAnswer && it.text.isNotEmpty()) it.copy(failure = ChatMessage.Failure.Interrupted) else it.copy(failure = failure)
    }

    private fun finish(placeholderID: String) {
        messages.firstOrNull { it.id == placeholderID }?.let { message ->
            val failure = when {
                stopped -> ChatMessage.Failure.Stopped
                message.text.isEmpty() && message.failure == null -> ChatMessage.Failure.CouldNotAnswer
                else -> message.failure
            }
            if (failure != message.failure) update(placeholderID) { it.copy(failure = failure) }
            if (failure == null) messages.firstOrNull { it.id == placeholderID }?.let { onAnswer?.invoke(it) }
        }
        // The turn is over: the agent no longer waits for an answer.
        if (pendingDeviceToolMessageID == placeholderID) {
            pendingDeviceTool = null
            pendingDeviceToolMessageID = null
        }
        isStreaming = false
        currentStep = null
        stopped = false
    }

    // Thread (ChatStore+Thread.swift)

    /** Whether [message] belongs in the thread under [query] and [filter] (null: everything). */
    fun matches(message: ChatMessage, query: String, filter: ChatThreadFilter?): Boolean {
        val needle = query.trim()
        if (needle.isNotEmpty()) {
            val inText = message.text.contains(needle, ignoreCase = true)
            val inFiles = message.files.any { it.name.contains(needle, ignoreCase = true) }
            val inSources = message.references.any { it.title.contains(needle, ignoreCase = true) }
            if (!inText && !inFiles && !inSources) return false
        }
        filter ?: return true
        return when (filter) {
            ChatThreadFilter.Approvals -> message.id in askedMessageIDs
            ChatThreadFilter.Drafts -> {
                if (message.sender != ChatMessage.Sender.Omi || message.failure != null) return false
                val text = message.text.lowercase()
                DRAFT_WORDS.any { text.contains(it) } ||
                    (message.id in askedMessageIDs && message.steps.any { it.lowercase().contains("draft") })
            }
            ChatThreadFilter.Jobs -> {
                val touched = ChatCardDetector.touchedTasks(message.steps)
                val hasTaskCard = cards(message.id).any { it !is ChatCard.Connect }
                // Stored answers carry no steps: one that talks about a task it set or finished counts too.
                val text = message.text.lowercase()
                val aboutTasks = TASK_WORDS.any { text.contains(it) }
                message.sender == ChatMessage.Sender.Omi && message.failure == null && (touched || hasTaskCard || aboutTasks)
            }
            ChatThreadFilter.Files -> message.files.isNotEmpty()
        }
    }

    /** The loaded messages that match (all of them without a query or filter). */
    fun visibleMessages(query: String, filter: ChatThreadFilter?): List<ChatMessage> {
        if (query.isBlank() && filter == null) return messages
        return messages.filter { matches(it, query, filter) }
    }

    /**
     * Removes [messageID] from the thread on this phone; the backend keeps it. It stays hidden
     * when the history loads again. Not while its answer is still coming in.
     */
    fun hide(messageID: String) {
        val message = messages.firstOrNull { it.id == messageID } ?: return
        if (isStreaming && message.id == messages.lastOrNull()?.id) return
        val stored = setOfNotNull(message.id, message.serverID).filter { !it.startsWith("local-") && !it.startsWith("pending-") }
        for (id in stored.sorted()) preferences.append(id, NativeKey.HiddenChatMessages)
        messages = messages.filter { it.id != messageID }
        if (replyingTo?.id == messageID) replyingTo = null
    }

    /** The failed answer right after the question [messageID] (its "Try again" asks it once more). */
    fun failedAnswer(after: String): ChatMessage? {
        val index = messages.indexOfFirst { it.id == after }
        if (index < 0 || messages[index].sender != ChatMessage.Sender.User || index + 1 >= messages.size) return null
        val answer = messages[index + 1]
        if (answer.sender != ChatMessage.Sender.Omi || (isStreaming && answer.id == messages.lastOrNull()?.id)) return null
        return when (answer.failure) {
            ChatMessage.Failure.CouldNotAnswer, ChatMessage.Failure.Offline, ChatMessage.Failure.Timeout -> answer
            ChatMessage.Failure.Interrupted, ChatMessage.Failure.Stopped, ChatMessage.Failure.QuotaExceeded -> null
            null -> if (answer.isServiceFailure) answer else null
        }
    }

    // Extras (ChatStore+Extras.swift)

    val isUploading: Boolean get() = attachments.any { it.state is PendingAttachment.State.Uploading }

    val canAttach: Boolean get() = attachments.size < MAX_ATTACHMENTS && !isStreaming

    /** Uploads at once; a failed upload stays in the row (marked) until removed. */
    fun attach(data: ByteArray, filename: String, mimeType: String, preview: ByteArray?) {
        if (!canAttach) return
        val id = UUID.randomUUID().toString()
        attachments = attachments + PendingAttachment(id, filename, mimeType, preview, PendingAttachment.State.Uploading)
        scope.launch {
            val state = try {
                PendingAttachment.State.Uploaded(api.uploadChatFile(filename, mimeType, data).copy(localPreview = preview))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                PendingAttachment.State.Failed
            }
            attachments = attachments.map { if (it.id == id) it.copy(state = state) else it }
        }
    }

    fun removeAttachment(id: String) {
        attachments = attachments.filter { it.id != id }
    }

    /**
     * Thumbs up (1), down (-1, with a reason key) or cleared (0). The rating shows at once and is
     * taken back if the backend refuses it; returns whether it was saved.
     */
    suspend fun rate(messageID: String, value: Int, reason: String? = null): Boolean {
        val message = messages.firstOrNull { it.id == messageID } ?: return false
        val serverID = message.serverID ?: return false
        val previous = message.rating
        update(messageID) { it.copy(rating = if (value == 0) null else value) }
        return try {
            api.rateChatMessage(serverID, value, reason)
            true
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            update(messageID) { it.copy(rating = previous) }
            false
        }
    }

    /**
     * Empties the main chat on the backend (its session only, never an agent run's) and starts
     * over with Omi's new greeting.
     */
    suspend fun clearChat(): Boolean {
        if (!hasLoaded) loadHistory()
        val sessionID = sessionID ?: return false
        streamJob?.cancel()
        return try {
            val greeting = api.clearChat(sessionID)
            messages = listOfNotNull(greeting)
            fetchedCount = messages.size
            hasEarlier = false
            attachments = emptyList()
            true
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            false
        }
    }

    // Cards (ChatStore+Cards.swift)

    /** The cards under one answer. */
    fun cards(messageID: String): List<ChatCard> = cardsByMessage[messageID].orEmpty()

    /** Takes a task card back: an added task is deleted, a ticked one opens again. The card goes. */
    suspend fun undo(card: ChatCard, messageID: String) {
        val tasks = tasks ?: return
        when (card) {
            is ChatCard.TaskAdded -> tasks.delete(card.taskID)
            is ChatCard.TaskCompleted -> tasks.setCompleted(card.taskID, false)
            is ChatCard.Connect -> return
        }
        if (tasks.lastError != null) return
        cardsByMessage = cardsByMessage + (messageID to cards(messageID).filter { it != card })
        undoneCards.add(card.id)
    }

    /** A connect card the user dealt with (connected, or "Not now"). */
    fun dismiss(card: ChatCard, messageID: String) {
        cardsByMessage = cardsByMessage + (messageID to cards(messageID).filter { it != card })
    }

    /**
     * After a turn: a missing connection, and the tasks it added or ticked off (the list is read
     * again only when a step says the agent touched tasks).
     */
    internal suspend fun collectCards(messageID: String, tasksBefore: List<ChatTasks.Task>?) {
        val message = messages.firstOrNull { it.id == messageID } ?: return
        if (message.sender != ChatMessage.Sender.Omi) return
        add(ChatCardDetector.missingConnections(message.text, message.steps).map { ChatCard.Connect(it) }, messageID, newest = true)
        val tasks = tasks
        if (tasks != null && tasksBefore != null && ChatCardDetector.touchedTasks(message.steps)) {
            tasks.load()
            add(ChatCardDetector.taskChanges(tasksBefore, tasks.tasks), messageID, newest = true)
        }
    }

    /**
     * Connect cards from stored answers (older pages): each connection's card stays on the newest
     * answer that asked for it.
     */
    internal fun collectConnectCards(page: List<ChatMessage>) {
        for (message in page.reversed()) {
            if (message.sender != ChatMessage.Sender.Omi || message.failure != null) continue
            add(ChatCardDetector.missingConnections(message.text).map { ChatCard.Connect(it) }, message.id, newest = false)
        }
    }

    internal fun add(cards: List<ChatCard>, messageID: String, newest: Boolean) {
        var byMessage = cardsByMessage
        for (card in cards) {
            if (card in byMessage[messageID].orEmpty() || card.id in undoneCards) continue
            if (card is ChatCard.Connect) {
                val elsewhere = byMessage.any { it.key != messageID && card in it.value }
                if (elsewhere) {
                    if (!newest) continue
                    byMessage = byMessage.mapValues { (_, list) -> list.filter { it != card } }
                }
            }
            byMessage = byMessage + (messageID to byMessage[messageID].orEmpty() + card)
        }
        cardsByMessage = byMessage
    }

    // Apps (ChatStore+Apps.swift)

    /** The user's enabled apps with the `chat` or `persona` capability. */
    suspend fun loadChatApps() {
        val api = apps ?: return
        val found = try {
            api.searchApps(query = "", installedOnly = true, offset = 0)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            return
        }
        chatApps = found.filter { it.worksWithChat }
        val chatApp = chatApp ?: return
        // The chosen app was turned off elsewhere: back to Omi.
        if (chatApps.none { it.id == chatApp.id }) talk(null)
    }

    /** Switches the chat to [app] (null: Omi). Not while an answer is streaming. */
    suspend fun talk(app: OmiApp?) {
        if (app?.id == chatApp?.id || isStreaming) return
        chatApp = app
        preferences.set(NativeKey.SelectedChatAppID, app?.id)
        resetForScope()
        loadHistory()
    }

    /** The app chosen last time, restored once its details are known. */
    internal suspend fun restoreChatApp() {
        if (chatApp != null) return
        val id = preferences.string(NativeKey.SelectedChatAppID) ?: return
        loadChatApps()
        if (chatApp != null) return
        val app = chatApps.firstOrNull { it.id == id }
        if (app == null) {
            if (chatApps.isNotEmpty()) preferences.set(NativeKey.SelectedChatAppID, null)
            return
        }
        chatApp = app
    }

    /**
     * The session the current chat reads and writes: the main chat's pinned one, or the app's
     * newest (opened on first use).
     */
    internal suspend fun resolveSession(): String? {
        restoreChatApp()
        val app = chatApp ?: return resolveMainSession()
        return try {
            api.chatSessions(app.id).firstOrNull()?.first ?: api.createChatSession(app.name, app.id)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            null
        }
    }

    companion object {
        /** Flutter's limit per message. */
        const val MAX_ATTACHMENTS = 4
        /** Words that mark an answer as carrying a draft. */
        internal val DRAFT_WORDS = listOf("draft", "entwurf", "entworfen")
        /** Words that mark an answer as work on tasks. */
        internal val TASK_WORDS = listOf("task", "to-do", "todo", "aufgabe")

        /** A stored answer that is one of the backend's canned failures reads as a failure. */
        fun marked(message: ChatMessage): ChatMessage =
            if (message.sender == ChatMessage.Sender.Omi && ChatStreamEvent.isServiceFailure(message.text)) {
                message.copy(failure = failure(forCanned = message.text))
            } else {
                message
            }

        /** A send that threw: no connection, the request timed out, the plan's limit (HTTP 402). */
        fun failure(error: Throwable, offline: Boolean): ChatMessage.Failure = when {
            error is SocketTimeoutException -> ChatMessage.Failure.Timeout
            error is UnknownHostException || error is ConnectException -> ChatMessage.Failure.Offline
            error is APIError.Http && error.status == 402 -> ChatMessage.Failure.QuotaExceeded
            error is APIError.Transport -> ChatMessage.Failure.Offline
            else -> if (offline) ChatMessage.Failure.Offline else ChatMessage.Failure.CouldNotAnswer
        }

        /** A typed `error:` frame (backend `X-Omi-Chat-Failure-Protocol`). */
        fun failure(forStreamCode: String, offline: Boolean): ChatMessage.Failure = when (forStreamCode) {
            "quota_exceeded" -> ChatMessage.Failure.QuotaExceeded
            "timeout" -> ChatMessage.Failure.Timeout
            "offline" -> ChatMessage.Failure.Offline
            else -> if (offline) ChatMessage.Failure.Offline else ChatMessage.Failure.CouldNotAnswer
        }

        /** The backend streams some failures as answer text; the one about waiting too long is a timeout. */
        fun failure(forCanned: String): ChatMessage.Failure =
            if (forCanned.trim() == ChatStreamEvent.serviceFailureTexts[2]) ChatMessage.Failure.Timeout else ChatMessage.Failure.CouldNotAnswer
    }
}

/** One of the backend's canned failure answers (streamed as ordinary text), not a reply. */
val ChatMessage.isServiceFailure: Boolean get() = ChatStreamEvent.isServiceFailure(text)

/**
 * A photo or file picked for the next message. It uploads right away (as in Flutter), so sending
 * is instant; the message carries the uploaded ids.
 */
data class PendingAttachment(
    val id: String,
    val filename: String,
    val mimeType: String,
    /** A small JPEG for the thumbnail (photos only). */
    val preview: ByteArray?,
    val state: State,
) {
    sealed interface State {
        data object Uploading : State
        data class Uploaded(val file: ChatFile) : State
        data object Failed : State
    }

    val file: ChatFile? get() = (state as? State.Uploaded)?.file

    override fun equals(other: Any?): Boolean = other is PendingAttachment && other.id == id && other.state == state
    override fun hashCode(): Int = id.hashCode()
}

/** Finding things in the one long thread: a search over the loaded history and filter chips. */
enum class ChatThreadFilter(val rawValue: String) {
    /** Omi asked before acting (a message to send, a contact, a permission). */
    Approvals("approvals"),
    /** Answers that prepared something for the user to send or use. */
    Drafts("drafts"),
    /** Hand-overs and what Omi did to tasks. */
    Jobs("jobs"),
    /** Photos and files sent in the chat. */
    Files("files"),
}

/**
 * How the thread names a day in its dividers: "Today", "Yesterday", a weekday within the last
 * week, otherwise the date.
 */
sealed interface ChatDay {
    data object Today : ChatDay
    data object Yesterday : ChatDay
    data class Weekday(val date: java.time.LocalDate) : ChatDay
    data class Date(val date: java.time.LocalDate, val showsYear: Boolean) : ChatDay

    companion object {
        fun of(date: Instant, now: Instant = Instant.now(), zone: java.time.ZoneId = java.time.ZoneId.systemDefault()): ChatDay {
            val day = date.atZone(zone).toLocalDate()
            val today = now.atZone(zone).toLocalDate()
            return when (java.time.temporal.ChronoUnit.DAYS.between(day, today)) {
                0L -> Today
                1L -> Yesterday
                in 2L..6L -> Weekday(day)
                else -> Date(day, showsYear = day.year != today.year)
            }
        }
    }
}

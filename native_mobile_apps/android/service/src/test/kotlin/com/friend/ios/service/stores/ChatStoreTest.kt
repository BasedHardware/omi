package com.friend.ios.service.stores

import android.content.SharedPreferences
import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.ChatFile
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.ChatAPI
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class ChatStoreTest {
    private fun message(id: String, text: String, sender: ChatMessage.Sender = ChatMessage.Sender.Omi, at: Long = 0) =
        ChatMessage(id = id, text = text, sender = sender, createdAt = Instant.ofEpochSecond(1_800_000_000 + at), serverID = id)

    private fun TestScope.store(api: FakeChatAPI, prefs: Preferences = Preferences(FakePrefs())) = ChatStore(api, prefs, this)

    @Test
    fun loadHistoryPinsTheNewestNonRunSessionAndReadsItsMessages() = runTest {
        val api = FakeChatAPI().apply {
            sessions = listOf("run" to "✦ Book a table", "main" to "Omi", "old" to "Older")
            history = listOf(message("a", "Hi", ChatMessage.Sender.User), message("b", "Hello!"))
        }
        val prefs = Preferences(FakePrefs())
        val chat = store(api, prefs)
        chat.loadHistory()
        assertTrue(chat.hasLoaded)
        assertEquals(listOf("a", "b"), chat.messages.map { it.id })
        assertEquals("main", prefs.string(NativeKey.MainChatSessionID))
        assertEquals(listOf("main"), api.historySessions)
        assertFalse(chat.hasEarlier)
    }

    @Test
    fun noChatYetOpensOneSoSendsNeverLandInARun() = runTest {
        val api = FakeChatAPI().apply { sessions = listOf("run" to "✦ Task") }
        val chat = store(api)
        chat.loadHistory()
        assertEquals(listOf("Omi"), api.createdSessions)
        assertEquals("created", chat.sessionID)
    }

    @Test
    fun historyFailureOffersRetry() = runTest {
        val api = FakeChatAPI().apply { historyError = APIError.Transport("down") }
        val chat = store(api)
        chat.loadHistory()
        assertTrue(chat.historyFailed)
        assertFalse(chat.hasLoaded)
        api.historyError = null
        chat.retryHistory()
        assertTrue(chat.hasLoaded)
    }

    @Test
    fun fullPageMeansEarlierAndLoadEarlierPrependsWithoutDuplicates() = runTest {
        val page = (0 until 50).map { message("m$it", "t$it", at = it.toLong()) }
        val api = FakeChatAPI().apply { history = page }
        val chat = store(api)
        chat.loadHistory()
        assertTrue(chat.hasEarlier)
        api.history = listOf(message("old", "older", at = -5), message("m0", "t0"))
        chat.loadEarlier()
        assertEquals("old", chat.messages.first().id)
        assertEquals(51, chat.messages.size)
        assertEquals(listOf(0, 50), api.historyOffsets)
        assertFalse(chat.hasEarlier)
    }

    @Test
    fun hiddenMessagesStayHidden() = runTest {
        val prefs = Preferences(FakePrefs())
        val api = FakeChatAPI().apply { history = listOf(message("a", "one"), message("b", "two")) }
        val chat = store(api, prefs)
        chat.loadHistory()
        chat.hide("a")
        assertEquals(listOf("b"), chat.messages.map { it.id })
        val again = store(api, prefs)
        again.loadHistory()
        assertEquals(listOf("b"), again.messages.map { it.id })
    }

    @Test
    fun sendStreamsStepsAndTextIntoThePlaceholderAndKeepsItsID() = runTest {
        val done = message("server-1", "Hello there", at = 9).copy(followUp = "And then?")
        val api = FakeChatAPI().apply {
            stream = listOf(ChatStreamEvent.Step("Searching the web"), ChatStreamEvent.Delta("Hello"), ChatStreamEvent.Delta(" there"), ChatStreamEvent.Done(done))
        }
        val chat = store(api)
        chat.loadHistory()
        var answered: ChatMessage? = null
        chat.onAnswer = { answered = it }
        chat.send("  Hi  ")
        assertTrue(chat.isStreaming)
        advanceUntilIdle()
        assertFalse(chat.isStreaming)
        val (question, answer) = chat.messages
        assertEquals("Hi", question.text)
        assertTrue(answer.id.startsWith("pending-"))
        assertEquals("Hello there", answer.text)
        assertEquals(listOf("Searching the web"), answer.steps)
        assertEquals("server-1", answer.serverID)
        assertEquals("And then?", answer.followUp)
        assertNull(answer.failure)
        assertEquals(answer.id, answered?.id)
        assertEquals("Hi", api.sent.single())
    }

    @Test
    fun replyCarriesTheQuoteInFront() = runTest {
        val api = FakeChatAPI().apply {
            history = listOf(message("a", "The meeting is on Friday."))
            stream = listOf(ChatStreamEvent.Delta("ok"))
        }
        val chat = store(api)
        chat.loadHistory()
        chat.replyingTo = chat.messages.first()
        chat.send("Which time?")
        advanceUntilIdle()
        assertEquals("> Omi: The meeting is on Friday.\n\nWhich time?", api.sent.single())
        assertNull(chat.replyingTo)
    }

    @Test
    fun typedErrorFramesAndThrownErrorsReadAsTheirFailure() = runTest {
        val api = FakeChatAPI().apply { stream = listOf(ChatStreamEvent.Failed("quota_exceeded")) }
        val chat = store(api)
        chat.loadHistory()
        chat.send("Hi")
        advanceUntilIdle()
        assertEquals(ChatMessage.Failure.QuotaExceeded, chat.messages.last().failure)

        api.stream = listOf(ChatStreamEvent.Delta("Half"))
        api.streamError = APIError.Http(500, "")
        chat.send("Again")
        advanceUntilIdle()
        assertEquals(ChatMessage.Failure.Interrupted, chat.messages.last().failure)
        assertEquals("Half", chat.messages.last().text)

        api.stream = emptyList()
        api.streamError = APIError.Transport("offline")
        chat.send("Third")
        advanceUntilIdle()
        assertEquals(ChatMessage.Failure.Offline, chat.messages.last().failure)
        assertEquals(chat.messages.last(), chat.failedAnswer(chat.messages[chat.messages.size - 2].id))
    }

    @Test
    fun emptyStreamIsCouldNotAnswerAndCannedTextIsAFailure() = runTest {
        val api = FakeChatAPI().apply { stream = emptyList() }
        val chat = store(api)
        chat.loadHistory()
        chat.send("Hi")
        advanceUntilIdle()
        assertEquals(ChatMessage.Failure.CouldNotAnswer, chat.messages.last().failure)

        api.stream = listOf(ChatStreamEvent.Delta(ChatStreamEvent.serviceFailureTexts[2]), ChatStreamEvent.Done(message("s", ChatStreamEvent.serviceFailureTexts[2])))
        chat.send("Hi again")
        advanceUntilIdle()
        assertEquals(ChatMessage.Failure.Timeout, chat.messages.last().failure)
    }

    @Test
    fun cancelKeepsWhatArrivedMarkedStopped() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = FakeChatAPI().apply {
            streamFlow = flow {
                emit(ChatStreamEvent.Delta("Part"))
                gate.await()
                emit(ChatStreamEvent.Delta(" never"))
            }
        }
        val chat = store(api)
        chat.loadHistory()
        chat.send("Long question")
        advanceUntilIdle()
        assertEquals("Part", chat.messages.last().text)
        chat.cancel()
        advanceUntilIdle()
        assertFalse(chat.isStreaming)
        assertEquals("Part", chat.messages.last().text)
        assertEquals(ChatMessage.Failure.Stopped, chat.messages.last().failure)
    }

    @Test
    fun retryAsksTheQuestionAgain() = runTest {
        val api = FakeChatAPI().apply { stream = listOf(ChatStreamEvent.Failed("server_error")) }
        val chat = store(api)
        chat.loadHistory()
        chat.send("What did I promise Anna?")
        advanceUntilIdle()
        val failed = chat.messages.last()
        assertEquals(ChatMessage.Failure.CouldNotAnswer, failed.failure)
        api.stream = listOf(ChatStreamEvent.Delta("Thursday follow-up"))
        chat.retry(failed.id)
        advanceUntilIdle()
        assertEquals(2, chat.messages.size)
        assertEquals("Thursday follow-up", chat.messages.last().text)
        assertEquals(listOf("What did I promise Anna?", "What did I promise Anna?"), api.sent)
    }

    @Test
    fun rateIsOptimisticAndTakenBackOnFailure() = runTest {
        val api = FakeChatAPI().apply { history = listOf(message("a", "Answer")) }
        val chat = store(api)
        chat.loadHistory()
        assertTrue(chat.rate("a", 1))
        assertEquals(1, chat.messages.single().rating)
        api.rateError = APIError.Http(500, "")
        assertFalse(chat.rate("a", -1, "too_verbose"))
        assertEquals(1, chat.messages.single().rating)
    }

    @Test
    fun clearChatLeavesTheGreeting() = runTest {
        val api = FakeChatAPI().apply {
            history = listOf(message("a", "one"), message("b", "two"))
            greeting = message("g", "Hi, I am Omi")
        }
        val chat = store(api)
        chat.loadHistory()
        assertTrue(chat.clearChat())
        assertEquals(listOf("g"), chat.messages.map { it.id })
        assertEquals(listOf("main"), api.cleared)
    }

    @Test
    fun searchAndFilters() = runTest {
        val api = FakeChatAPI().apply {
            history = listOf(
                message("q", "Draft an email to Anna", ChatMessage.Sender.User),
                message("d", "Here is a draft for Anna."),
                message("t", "I added a task to call Bob."),
                message("f", "photo", ChatMessage.Sender.User).copy(files = listOf(ChatFile("1", "receipt.jpg", "image/jpeg"))),
            )
        }
        val chat = store(api)
        chat.loadHistory()
        assertEquals(listOf("q", "d"), chat.visibleMessages("anna", null).map { it.id })
        assertEquals(listOf("d"), chat.visibleMessages("", ChatThreadFilter.Drafts).map { it.id })
        assertEquals(listOf("t"), chat.visibleMessages("", ChatThreadFilter.Jobs).map { it.id })
        assertEquals(listOf("f"), chat.visibleMessages("receipt", ChatThreadFilter.Files).map { it.id })
        assertEquals(4, chat.visibleMessages(" ", null).size)
    }

    @Test
    fun cardsForMissingConnectionsAndTaskChanges() = runTest {
        val tasks = FakeTasks(listOf(ChatTasks.Task("1", "Old task", false)))
        val api = FakeChatAPI().apply {
            stream = listOf(
                ChatStreamEvent.Step("Creating action item"),
                ChatStreamEvent.Delta("Done. Google Calendar is not connected, please connect it."),
            )
        }
        val chat = store(api)
        chat.tasks = tasks
        chat.loadHistory()
        tasks.afterLoad = listOf(ChatTasks.Task("1", "Old task", true), ChatTasks.Task("2", "Call Bob", false))
        chat.send("Add a task")
        advanceUntilIdle()
        val id = chat.messages.last().id
        assertEquals(
            listOf(ChatCard.Connect("google_calendar"), ChatCard.TaskCompleted("1", "Old task"), ChatCard.TaskAdded("2", "Call Bob")),
            chat.cards(id),
        )
        chat.undo(ChatCard.TaskAdded("2", "Call Bob"), id)
        assertEquals(listOf("2"), tasks.deleted)
        assertEquals(2, chat.cards(id).size)
        chat.dismiss(ChatCard.Connect("google_calendar"), id)
        assertEquals(listOf(ChatCard.TaskCompleted("1", "Old task")), chat.cards(id))
    }

    @Test
    fun chatDayNamesDays() {
        val zone = java.time.ZoneOffset.UTC
        val now = Instant.parse("2026-10-08T12:00:00Z")
        assertEquals(ChatDay.Today, ChatDay.of(Instant.parse("2026-10-08T01:00:00Z"), now, zone))
        assertEquals(ChatDay.Yesterday, ChatDay.of(Instant.parse("2026-10-07T23:00:00Z"), now, zone))
        assertTrue(ChatDay.of(Instant.parse("2026-10-04T10:00:00Z"), now, zone) is ChatDay.Weekday)
        assertEquals(ChatDay.Date(java.time.LocalDate.of(2025, 12, 1), true), ChatDay.of(Instant.parse("2025-12-01T10:00:00Z"), now, zone))
    }
}

/** A fake backend: sessions, one history page per call, a scripted stream. */
class FakeChatAPI : ChatAPI {
    var sessions: List<Pair<String, String>> = listOf("main" to "Omi")
    var history: List<ChatMessage> = emptyList()
    var historyError: Exception? = null
    var stream: List<ChatStreamEvent> = emptyList()
    var streamError: Exception? = null
    var streamFlow: Flow<ChatStreamEvent>? = null
    var rateError: Exception? = null
    var greeting: ChatMessage? = null
    val sent = mutableListOf<String>()
    val historySessions = mutableListOf<String?>()
    val historyOffsets = mutableListOf<Int>()
    val createdSessions = mutableListOf<String>()
    val cleared = mutableListOf<String>()

    override fun sendChatMessage(text: String, fileIDs: List<String>, context: ChatContext?, sessionID: String?, deviceTools: List<String>): Flow<ChatStreamEvent> {
        sent.add(text)
        streamFlow?.let { return it }
        val events = stream
        val error = streamError
        return flow {
            events.forEach { emit(it) }
            if (error != null) throw error
        }
    }

    override suspend fun chatHistory(limit: Int, offset: Int, sessionID: String?): List<ChatMessage> {
        historyError?.let { throw it }
        historySessions.add(sessionID)
        historyOffsets.add(offset)
        return history
    }

    override suspend fun createChatSession(title: String): String {
        createdSessions.add(title)
        return "created"
    }

    override suspend fun chatSessions(): List<Pair<String, String>> = sessions
    override suspend fun chatSessions(appID: String): List<Pair<String, String>> = emptyList()
    override suspend fun createChatSession(title: String, appID: String): String = "app-session"

    override suspend fun rateChatMessage(id: String, value: Int, reason: String?) {
        rateError?.let { throw it }
    }

    override suspend fun clearChat(sessionID: String): ChatMessage? {
        cleared.add(sessionID)
        return greeting
    }

    override suspend fun uploadChatFile(filename: String, mimeType: String, data: ByteArray): ChatFile = ChatFile("f-$filename", filename, mimeType)
}

class FakeTasks(override var tasks: List<ChatTasks.Task>) : ChatTasks {
    var afterLoad: List<ChatTasks.Task>? = null
    val deleted = mutableListOf<String>()
    override val lastError: String? = null
    override suspend fun load() {
        afterLoad?.let { tasks = it }
    }
    override suspend fun delete(id: String) {
        deleted.add(id)
    }
    override suspend fun setCompleted(id: String, completed: Boolean) {}
}

/** An in-memory `SharedPreferences` for `Preferences` in JVM tests. */
class FakePrefs : SharedPreferences {
    private val values = HashMap<String, Any?>()
    override fun getAll(): MutableMap<String, *> = HashMap(values)
    override fun getString(key: String, defValue: String?): String? = values[key] as? String ?: defValue
    override fun getStringSet(key: String, defValues: MutableSet<String>?): MutableSet<String>? = defValues
    override fun getInt(key: String, defValue: Int): Int = values[key] as? Int ?: defValue
    override fun getLong(key: String, defValue: Long): Long = values[key] as? Long ?: defValue
    override fun getFloat(key: String, defValue: Float): Float = values[key] as? Float ?: defValue
    override fun getBoolean(key: String, defValue: Boolean): Boolean = values[key] as? Boolean ?: defValue
    override fun contains(key: String): Boolean = key in values
    override fun registerOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
    override fun unregisterOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
    override fun edit(): SharedPreferences.Editor = object : SharedPreferences.Editor {
        val pending = HashMap<String, Any?>()
        val removed = HashSet<String>()
        var clear = false
        override fun putString(key: String, value: String?) = apply { pending[key] = value }
        override fun putStringSet(key: String, values: MutableSet<String>?) = apply { pending[key] = values }
        override fun putInt(key: String, value: Int) = apply { pending[key] = value }
        override fun putLong(key: String, value: Long) = apply { pending[key] = value }
        override fun putFloat(key: String, value: Float) = apply { pending[key] = value }
        override fun putBoolean(key: String, value: Boolean) = apply { pending[key] = value }
        override fun remove(key: String) = apply { removed.add(key) }
        override fun clear() = apply { clear = true }
        override fun commit(): Boolean {
            apply()
            return true
        }
        override fun apply() {
            if (clear) values.clear()
            removed.forEach { values.remove(it) }
            values.putAll(pending)
        }
    }
}

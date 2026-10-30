package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.ContactsAccess
import com.friend.ios.core.models.DeviceContact
import com.friend.ios.core.models.DeviceToolPerforming
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.core.models.MessageComposeOutcome
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

/** The phone's side, scripted. */
class FakePerformer(
    override var canSendMessages: Boolean = true,
    override var contactsAccess: ContactsAccess = ContactsAccess.Granted,
    var afterPrompt: ContactsAccess = ContactsAccess.Granted,
    var contacts: List<DeviceContact> = emptyList(),
    var outcome: MessageComposeOutcome = MessageComposeOutcome.Opened,
) : DeviceToolPerforming {
    val composed = mutableListOf<Triple<List<String>, String, String?>>()
    var prompts = 0
    override suspend fun searchContacts(query: String, limit: Int): List<DeviceContact> =
        contacts.filter { it.name.contains(query, ignoreCase = true) }.take(limit)
    override suspend fun requestContactsAccess(): ContactsAccess {
        prompts += 1
        contactsAccess = afterPrompt
        return contactsAccess
    }
    override suspend fun composeMessage(recipients: List<String>, text: String, subject: String?): MessageComposeOutcome {
        composed += Triple(recipients, text, subject)
        return outcome
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class DeviceToolsTest {
    private val anna = DeviceContact("a", "Anna Schmidt", listOf(DeviceContact.Handle("mobile", "+49 170")), emptyList(), "+49 170")
    private val annabel = DeviceContact("b", "Annabel Lee", emptyList(), emptyList(), "")

    @Test
    fun declaresOnlyWhatThePhoneCanDo() {
        assertEquals(emptyList<String>(), DeviceToolResolver.declaredTools(null))
        assertEquals(listOf("propose_message", "search_contacts", "request_permission"), DeviceToolResolver.declaredTools(FakePerformer()))
        assertEquals(listOf("search_contacts", "request_permission"), DeviceToolResolver.declaredTools(FakePerformer(canSendMessages = false)))
    }

    @Test
    fun malformedAndUnsupportedAreAnsweredAtOnce() {
        val performer = FakePerformer()
        assertEquals("malformed_request", DeviceToolResolver.immediateResult(DeviceToolRequest("c", ""), performer)?.reason)
        assertEquals("unsupported_tool", DeviceToolResolver.immediateResult(DeviceToolRequest("c", "read_sms"), performer)?.reason)
        assertEquals("surface_unavailable", DeviceToolResolver.immediateResult(DeviceToolRequest("c", "search_contacts", query = "A"), null)?.reason)
        assertEquals("empty_body", DeviceToolResolver.immediateResult(DeviceToolRequest("c", "propose_message", recipients = listOf("x"), text = " "), performer)?.reason)
        assertEquals("unsupported_permission", DeviceToolResolver.immediateResult(DeviceToolRequest("c", "request_permission", permission = "calendar"), performer)?.reason)
        assertNull(DeviceToolResolver.immediateResult(DeviceToolRequest("c", "search_contacts", query = "Anna"), performer))
    }

    @Test
    fun contactSearchAsksBeforeReadingThenPicks() = runTest {
        val performer = FakePerformer(contactsAccess = ContactsAccess.NotDetermined, contacts = listOf(anna, annabel))
        val request = DeviceToolRequest("c", "search_contacts", query = "Anna")
        val pending = DeviceToolResolver.prepare(request, "t", "Task", performer)
        assertTrue(pending.needsContactsAccess)
        assertEquals(0, performer.prompts)
        val allowed = DeviceToolResolver.result(pending, DeviceToolChoice.Allow, performer)
        assertNull(allowed.result)
        assertEquals(listOf(anna, annabel), allowed.pending.matches)
        assertFalse(allowed.pending.needsContactsAccess)
        val picked = DeviceToolResolver.result(allowed.pending, DeviceToolChoice.Pick(anna), performer).result!!
        assertTrue(picked.ok)
        assertEquals(listOf(anna), picked.contacts)
    }

    @Test
    fun deniedContactsAndDeclines() = runTest {
        val performer = FakePerformer(contactsAccess = ContactsAccess.NotDetermined, afterPrompt = ContactsAccess.Denied)
        val pending = DeviceToolResolver.prepare(DeviceToolRequest("c", "search_contacts", query = "Anna"), "", "", performer)
        val denied = DeviceToolResolver.result(pending, DeviceToolChoice.Allow, performer).result!!
        assertEquals("authorization_denied", denied.reason)
        val message = PendingDeviceTool("", "", DeviceToolRequest("m", "propose_message", recipients = listOf("+49"), text = "Hi"))
        val declined = DeviceToolResolver.result(message, DeviceToolChoice.Decline, performer).result!!
        assertEquals("cancelled", declined.status)
        assertTrue(performer.composed.isEmpty())
    }

    /** Android cannot know whether the user sent: the result says the app opened, never "sent". */
    @Test
    fun openedComposerIsNotReportedAsSent() = runTest {
        val performer = FakePerformer()
        val message = PendingDeviceTool("", "", DeviceToolRequest("m", "propose_message", recipients = listOf("+49"), text = "Hi", subject = "S"))
        val result = DeviceToolResolver.result(message, DeviceToolChoice.Send(" Hi Anna "), performer).result!!
        assertEquals(Triple(listOf("+49"), "Hi Anna", "S"), performer.composed.single())
        assertEquals("opened", result.status)
        assertTrue(result.error!!.contains("Do not say it was sent"))
    }

    @Test
    fun chatDeclaresToolsAndWaitsForThePick() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = AskFakeAPI()
        val frame = DeviceToolRequest("call-1", "search_contacts", query = "Anna")
        api.chat.streamFlow = flow {
            emit(ChatStreamEvent.DeviceTool(frame))
            gate.await()
            emit(ChatStreamEvent.Delta("Sent to Anna."))
        }
        val chat = ChatStore(api, freshPreferences(), this)
        chat.deviceTools = FakePerformer(contacts = listOf(anna))
        chat.send("Text Anna", emptyList())
        runCurrent()
        assertEquals(listOf("propose_message", "search_contacts", "request_permission"), api.declaredTools.single())
        val pending = chat.pendingDeviceTool!!
        assertEquals(listOf(anna), pending.matches)
        assertEquals(chat.messages.last().id, chat.pendingDeviceToolMessageID)
        assertTrue(chat.pendingDeviceToolMessageID in chat.askedMessageIDs)
        chat.answerDeviceTool(DeviceToolChoice.Pick(anna))
        assertNull(chat.pendingDeviceTool)
        assertEquals("call-1", api.results.single().first)
        assertEquals(listOf(anna), api.results.single().second.contacts)
        gate.complete(Unit)
        advanceUntilIdle()
        assertEquals("Sent to Anna.", chat.messages.last().text)
    }

    @Test
    fun unsupportedToolInTheChatIsAnsweredWithoutACard() = runTest {
        val api = AskFakeAPI()
        api.chat.stream = listOf(ChatStreamEvent.DeviceTool(DeviceToolRequest("call-2", "read_sms")), ChatStreamEvent.Delta("ok"))
        val chat = ChatStore(api, freshPreferences(), this)
        chat.deviceTools = FakePerformer()
        chat.send("Hi", emptyList())
        advanceUntilIdle()
        assertNull(chat.pendingDeviceTool)
        assertEquals("unsupported_tool", api.results.single().second.reason)
    }

    @Test
    fun omiAsksComeFirstOnHome() {
        val pending = PendingDeviceTool("t1", "Text Anna", DeviceToolRequest("c", "search_contacts", query = "Anna"))
        val run = AgentStore.Run("t1", "Text Anna", state = AgentStore.RunState.Working("Looking"), steps = emptyList(), partialText = "", startedAt = Instant.EPOCH)
        val task = ActionItem(id = "t2", description = "Call mom", isCompleted = false, dueAt = null, conversationID = null, owner = ActionItem.Owner.User, workstreamID = null, createdAt = null)
        val inbox = HomeAttention.inbox(HomeAttention.Input(runs = listOf(run), asks = listOf(pending), tasks = listOf(task)))
        assertEquals(HomeAttention.Item.OmiAsks(pending), inbox.needsYou.first())
        // A run that waits on the user shows as its question, not as "working" too.
        assertTrue(inbox.later.none { it is HomeAttention.Item.Working })
        assertEquals(HomeTapTargets.Target.Run("t1"), HomeTapTargets.target(inbox.needsYou.first()))
    }

    @Test
    fun voiceReadsAloudByModeAndToggles() = runTest {
        val prefs = freshPreferences()
        val player = RecordingPlayer()
        var headphones = false
        val voice = VoicePlaybackStore(prefs, player, this, synthesize = { _, _ -> byteArrayOf(7) }, headphonesConnected = { headphones })
        val answer = ChatMessage(id = "m1", text = "**Hi** there.", sender = ChatMessage.Sender.Omi, createdAt = Instant.EPOCH)
        assertFalse(voice.answerArrived(answer))
        headphones = true
        assertTrue(voice.answerArrived(answer))
        advanceUntilIdle()
        assertEquals(1, player.played.size)
        voice.setReplyMode(VoicePlaybackStore.ReplyMode.Off)
        assertFalse(voice.answerArrived(answer.copy(id = "m2")))
        // "Read aloud" ignores the mode; a failed answer is never read.
        voice.toggle(answer.copy(id = "m3"))
        assertEquals("m3", voice.playingID)
        voice.toggle(answer.copy(id = "m3"))
        assertNull(voice.playingID)
        voice.toggle(answer.copy(id = "m4", failure = ChatMessage.Failure.CouldNotAnswer))
        assertNull(voice.playingID)
    }

    @Test
    fun backendVoiceDownFallsBackToTheSystemVoice() = runTest {
        val player = RecordingPlayer()
        val voice = VoicePlaybackStore(freshPreferences(), player, this, synthesize = { _, _ -> throw IllegalStateException("quota") })
        val answer = ChatMessage(id = "m1", text = "One. Two.", sender = ChatMessage.Sender.Omi, createdAt = Instant.EPOCH)
        launch { voice.toggle(answer) }
        advanceUntilIdle()
        assertEquals(listOf("One. Two."), player.spoken)
        assertNull(voice.playingID)
    }
}

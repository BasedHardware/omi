package com.friend.ios.service.stores

import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.SpeakerTarget
import com.friend.ios.network.APIError
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.PhoneCaptureEngine
import com.friend.ios.service.PhoneCaptureStreams
import com.friend.ios.service.UnavailableDeviceTranscriptionEngine
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `LiveSpeakersTests.swift`: naming a voice while the conversation is being recorded. */
@OptIn(ExperimentalCoroutinesApi::class)
class LiveSpeakersStoreTest {
    private val segments = listOf(
        LiveSegment("s1", "Hi there", "SPEAKER_01", 1, false, 0.0, 1.0),
        LiveSegment("s2", "How are you", "SPEAKER_01", 1, false, 1.0, 2.0),
        LiveSegment("s3", "Fine", "SPEAKER_00", 0, true, 2.0, 3.0),
    )

    /** The listen socket: server events pushed by the test, and the `speaker_assigned` it was sent. */
    private class FakeChannel : LiveTranscriptionChannel {
        val incoming = Channel<ListenEvent>(Channel.UNLIMITED)
        override val events: Flow<ListenEvent> = incoming.receiveAsFlow()
        val speakerAssignments = mutableListOf<String>()

        override fun send(audio: ByteArray) {}

        override fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String) {}

        override fun close(reason: String) {
            incoming.close()
        }

        override fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) {
            speakerAssignments += "$speakerID:$personID:$personName:${segmentIDs.joinToString(",")}"
        }
    }

    private class FakeEngine : PhoneCaptureEngine {
        override suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams {
            if (transcribeOnDevice) throw com.friend.ios.service.CaptureFailure.SpeechUnavailable
            return PhoneCaptureStreams(Channel<ByteArray>().receiveAsFlow(), Channel<Float>().receiveAsFlow(), null)
        }

        override fun stop() {}
    }

    private class Live(val api: FakeAPI, val channel: FakeChannel, val speakers: LiveSpeakersStore)

    /** A phone recording with three lines, two of them one voice; [conversationID] null: no session event. */
    private suspend fun TestScope.live(conversationID: String? = "c-live", setup: FakeAPI.() -> Unit = {}): Live {
        val channel = FakeChannel()
        val api = fakeAPI {
            "openListenSocket" returns channel
            "subscription" throws APIError.Transport("offline")
            "createPerson" does { args -> Person("p0", args[0] as String, 0) }
            "assignSpeaker" returns ConversationDetail(Fixtures.conversation("c-live", java.time.Instant.EPOCH), emptyList(), emptyList())
            setup()
        }
        val scope = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[kotlinx.coroutines.Job]!!)
        val capture = CaptureStore(
            api.client, FakeEngine(), UnavailableDeviceTranscriptionEngine(), freshPreferences(), defaultOnDevice = false,
            userID = { "alice" }, scope = scope, clock = { 1_000_000L },
        )
        capture.startPhone()
        conversationID?.let { channel.incoming.trySend(ListenEvent.ConversationStarted(it)) }
        channel.incoming.trySend(ListenEvent.Segments(segments))
        return Live(api, channel, LiveSpeakersStore(api.client, capture))
    }

    /** `assign:<conversation>:<lines or voice>:<target>`, as `FakeAPIClient.speakers.log`. */
    private fun FakeAPI.assignLog(): List<String> = called("assignSpeaker").map { args ->
        val voice = args[2] as Int?
        val lines = if (voice != null) "voice=$voice" else (args[1] as List<*>).joinToString(",")
        val target = when (val to = args[3] as SpeakerTarget) {
            SpeakerTarget.User -> "user"
            is SpeakerTarget.Person -> "person:${to.id}"
        }
        "assign:${args[0]}:$lines:$target"
    }

    @Test
    fun namingAVoiceLabelsItsLinesAndTellsTheSession() = runTest(UnconfinedTestDispatcher()) {
        val live = live()
        val anna = Person("p1", "Anna", 0)
        live.speakers.assign(segments[0], TranscriptSpeakersStore.Choice.PersonChoice(anna), TranscriptSpeakersStore.Scope.Voice)
        assertEquals(listOf("assign:c-live:voice=1:person:p1"), live.api.assignLog())
        assertEquals(listOf("1:p1:Anna:s1,s2"), live.channel.speakerAssignments)
        assertEquals(LiveSpeakersStore.Label(false, "p1"), live.speakers.label(segments[1]))
        assertEquals(LiveSpeakersStore.Label(true, null), live.speakers.label(segments[2]))
        // A later line of the same voice is covered too.
        val later = LiveSegment("s9", "Bye", null, 1, false, 9.0, 10.0)
        assertEquals("p1", live.speakers.label(later).personID)
    }

    @Test
    fun oneLineUsesBulkAssignAndANewName() = runTest(UnconfinedTestDispatcher()) {
        val live = live()
        val created = live.speakers.assign(segments[1], TranscriptSpeakersStore.Choice.NewPerson(" Ben "), TranscriptSpeakersStore.Scope.Line)
        assertEquals("Ben", created?.name)
        assertEquals(listOf("assign:c-live:s2:person:p0"), live.api.assignLog())
        assertEquals("p0", live.speakers.label(segments[1]).personID)
        assertNull(live.speakers.label(segments[0]).personID)
        assertEquals("Ben", live.speakers.name("p0"))
    }

    @Test
    fun withoutTheSessionEventTheInProgressConversationIsLookedUp() = runTest(UnconfinedTestDispatcher()) {
        val live = live(conversationID = null) { "inProgressConversationID" returns "c-rest" }
        live.speakers.assign(segments[0], TranscriptSpeakersStore.Choice.Me, TranscriptSpeakersStore.Scope.Voice)
        assertEquals(1, live.api.called("inProgressConversationID").size)
        assertEquals(listOf("assign:c-rest:voice=1:user"), live.api.assignLog())
        assertEquals(listOf("1:user::s1,s2"), live.channel.speakerAssignments)
    }

    @Test
    fun aRefusedAssignmentChangesNothing() = runTest(UnconfinedTestDispatcher()) {
        val live = live { "assignSpeaker" throws APIError.Http(500, "") }
        live.speakers.assign(segments[0], TranscriptSpeakersStore.Choice.Me, TranscriptSpeakersStore.Scope.Voice)
        assertNotNull(live.speakers.lastError)
        assertEquals(LiveSpeakersStore.Label(false, null), live.speakers.label(segments[0]))
        assertTrue(live.channel.speakerAssignments.isEmpty())
    }

    @Test
    fun notAPersonIsNotOfferedWhileRecording() = runTest(UnconfinedTestDispatcher()) {
        val live = live()
        assertNull(live.speakers.assign(segments[0], TranscriptSpeakersStore.Choice.NotAPerson, TranscriptSpeakersStore.Scope.Voice))
        assertTrue(live.api.called("assignSpeaker").isEmpty())
    }
}

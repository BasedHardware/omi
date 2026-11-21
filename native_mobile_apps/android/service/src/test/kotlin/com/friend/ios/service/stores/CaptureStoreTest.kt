package com.friend.ios.service.stores

import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.network.APIError
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.CaptureFailure
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
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class CaptureStoreTest {
    /** The socket as the store sees it: what it was sent, and a way to push server events. */
    private class FakeChannel : LiveTranscriptionChannel {
        val incoming = Channel<ListenEvent>(Channel.UNLIMITED)
        override val events: Flow<ListenEvent> = incoming.receiveAsFlow()
        val audio = mutableListOf<ByteArray>()
        val closes = mutableListOf<String>()
        val suggested = mutableListOf<List<LiveSegment>>()
        val assigned = mutableListOf<List<String>>()

        override fun send(audio: ByteArray) {
            this.audio += audio
        }

        override fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String) {
            suggested += segments
        }

        override fun close(reason: String) {
            closes += reason
            incoming.close()
        }

        override fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) {
            assigned += segmentIDs
        }

        fun emit(event: ListenEvent) {
            incoming.trySend(event)
        }
    }

    /** The microphone: a start per call, chunks pushed by the test. */
    private class FakeEngine : PhoneCaptureEngine {
        var starts = 0
        var stops = 0
        var failure: Exception? = null
        var pcm = Channel<ByteArray>(Channel.UNLIMITED)
        val onDeviceRequests = mutableListOf<Boolean>()

        override suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams {
            onDeviceRequests += transcribeOnDevice
            // Android has no on-device recognizer yet: like `LivePhoneCaptureEngine`.
            if (transcribeOnDevice) throw CaptureFailure.SpeechUnavailable
            failure?.let { throw it }
            starts += 1
            pcm = Channel(Channel.UNLIMITED)
            return PhoneCaptureStreams(pcm.receiveAsFlow(), Channel<Float>().receiveAsFlow(), null)
        }

        override fun stop() {
            stops += 1
        }
    }

    private class Harness(
        val api: FakeAPI,
        val engine: FakeEngine,
        val preferences: Preferences,
        val store: CaptureStore,
        val sockets: MutableList<FakeChannel>,
        val options: MutableList<ListenSocket.Options>,
    )

    private fun TestScope.harness(
        preferences: Preferences = freshPreferences(),
        setup: FakeAPI.() -> Unit = {},
    ): Harness {
        val sockets = mutableListOf<FakeChannel>()
        val options = mutableListOf<ListenSocket.Options>()
        val api = fakeAPI {
            "openListenSocket" does { args ->
                options += args[1] as ListenSocket.Options
                FakeChannel().also { sockets += it }
            }
            "finalizeInProgressConversation" returns "c1"
            "subscription" throws APIError.Transport("offline")
            setup()
        }
        val engine = FakeEngine()
        val scope = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[kotlinx.coroutines.Job]!!)
        val store = CaptureStore(
            api.client, engine, UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope, clock = { 1_000_000L },
        )
        return Harness(api, engine, preferences, store, sockets, options)
    }

    @Test
    fun aPhoneRecordingStreamsToTheSocketAndIsFinalizedOnStop() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        var finished = 0
        h.store.onConversationFinished = { finished += 1 }
        h.store.startPhone()

        assertEquals(CaptureStore.Phase.Live(1_000_000L), h.store.phase)
        assertTrue(h.store.isLive)
        assertEquals(CaptureStore.Source.Phone, h.store.source)
        val options = h.options.single()
        assertEquals(ListenSocket.Options.Codec.Pcm16, options.codec)
        assertEquals(ListenSocket.Options.Source.Phone, options.source)
        assertFalse(options.clientTranscription)
        // The server transcribes; the phone's preview was tried first (no recognizer on Android).
        assertEquals(listOf(true, false), h.engine.onDeviceRequests)
        assertEquals("1000.0", h.preferences.string(NativeKey.CaptureActiveSince))

        h.engine.pcm.send(ByteArray(2560) { 7 })
        val socket = h.sockets.single()
        assertEquals(2560, socket.audio.single().size)

        socket.emit(ListenEvent.ConversationStarted("c1"))
        socket.emit(ListenEvent.Segments(listOf(LiveSegment("s1", "Hello", "SPEAKER_00", 0, true, 0.0, 1.0))))
        socket.emit(ListenEvent.Segments(listOf(LiveSegment("s1", "Hello there", "SPEAKER_00", 0, true, 0.0, 1.4))))
        assertEquals("c1", h.store.liveConversationID)
        assertEquals("c1", h.preferences.string(NativeKey.CaptureOpenConversation))
        assertEquals("Hello there", h.store.liveWords)

        // The failed preview start already stopped the engine once (as on iOS).
        val stopsBefore = h.engine.stops
        h.store.stop()
        assertEquals(CaptureStore.Phase.Idle, h.store.phase)
        assertEquals(listOf("user_stop"), socket.closes)
        assertEquals(stopsBefore + 1, h.engine.stops)
        assertEquals(1, h.api.called("finalizeInProgressConversation").size)
        assertEquals("c1", h.store.lastConversationID)
        assertNull(h.preferences.string(NativeKey.CaptureOpenConversation))
        assertNull(h.preferences.string(NativeKey.CaptureActiveSince))
        assertEquals(1, finished)
    }

    @Test
    fun withoutTheMicrophoneTheRecordingFails() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.engine.failure = CaptureFailure.MicrophonePermission
        h.store.startPhone()
        assertEquals(CaptureStore.Phase.Failed("microphone"), h.store.phase)
        assertFalse(h.store.isLive)
        assertTrue(h.sockets.isEmpty())
    }

    @Test
    fun aFailedTranscriptionEndsThePhoneRecording() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()
        h.sockets.single().emit(ListenEvent.Status("stt_failed: deepgram"))
        assertEquals(CaptureStore.Phase.Failed("stt_failed: deepgram"), h.store.phase)
        assertNull(h.preferences.string(NativeKey.CaptureActiveSince))
    }

    @Test
    fun aRecordingLeftLiveByAKilledAppIsReportedOnce() = runTest(UnconfinedTestDispatcher()) {
        val preferences = freshPreferences()
        preferences.set(NativeKey.CaptureActiveSince, "1700000000.5")
        val h = harness(preferences)
        assertEquals(CaptureRecovery.Interrupted(1_700_000_000_500L), h.store.recovery)
        assertNull(preferences.string(NativeKey.CaptureActiveSince))
        h.store.dismissRecovery()
        assertNull(h.store.recovery)
    }

    private fun detail(status: Conversation.Status, lines: Int) = ConversationDetail(
        conversation = Conversation(
            "old", "Old", "", null, null, Instant.EPOCH, null, null, status, isStarred = false, actionItemCount = 0,
        ),
        summaryActionItems = emptyList(),
        transcript = List(lines) { ConversationDetail.Line(it, "SPEAKER_00", true, "hi", 0.0) },
    )

    @Test
    fun aConversationLeftOpenIsFinalizedBeforeTheNextStart() = runTest(UnconfinedTestDispatcher()) {
        val preferences = freshPreferences()
        preferences.set(NativeKey.CaptureOpenConversation, "old")
        val h = harness(preferences) {
            "conversationDetail" returns detail(Conversation.Status.InProgress, lines = 2)
            // A local backend without the finalization worker: the in-progress endpoint, only for this one.
            "finalizeConversation" throws APIError.Http(503, "")
            "inProgressConversationID" returns "old"
        }
        h.store.startPhone()
        assertEquals(listOf(listOf<Any?>("old")), h.api.called("finalizeConversation"))
        assertEquals(1, h.api.called("finalizeInProgressConversation").size)
        assertNull(preferences.string(NativeKey.CaptureOpenConversation))
        assertTrue(h.store.isLive)
    }

    @Test
    fun anEmptyLeftoverIsLeftToTheBackend() = runTest(UnconfinedTestDispatcher()) {
        val preferences = freshPreferences()
        preferences.set(NativeKey.CaptureOpenConversation, "old")
        val h = harness(preferences) { "conversationDetail" returns detail(Conversation.Status.InProgress, lines = 0) }
        h.store.startPhone()
        assertTrue(h.api.called("finalizeConversation").isEmpty())
        assertNull(preferences.string(NativeKey.CaptureOpenConversation))
    }

    /** `CaptureStore+Lifecycle.swift`: a leftover with photos and no words still has something to keep. */
    @Test
    fun aLeftoverWithOnlyPhotosIsFinalized() = runTest(UnconfinedTestDispatcher()) {
        val preferences = freshPreferences()
        preferences.set(NativeKey.CaptureOpenConversation, "old")
        val photo = com.friend.ios.core.models.ConversationPhoto("p1", null, null, isDiscarded = false, isStored = true)
        val h = harness(preferences) {
            "conversationDetail" returns detail(Conversation.Status.InProgress, lines = 0).copy(photos = listOf(photo))
            "finalizeConversation" returns Unit
        }
        h.store.startPhone()
        assertEquals(listOf(listOf<Any?>("old")), h.api.called("finalizeConversation"))
        assertNull(preferences.string(NativeKey.CaptureOpenConversation))
    }

    @Test
    fun pauseReleasesTheMicrophoneAndResumeTakesItBack() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()
        val stopsBefore = h.engine.stops
        h.store.pause()
        assertTrue(h.store.isPaused)
        assertEquals(stopsBefore + 1, h.engine.stops)
        h.store.resume()
        assertFalse(h.store.isPaused)
        assertEquals(2, h.engine.starts)
        h.engine.pcm.send(ByteArray(100))
        assertEquals(1, h.sockets.single().audio.size)
    }

    @Test
    fun aDroppedOmiSocketReopensWithTheSameRecordingAndSendsTheHeldAudioFirst() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.deviceReconnectDelays = listOf(10L)
        h.store.startDevice(ListenSocket.Options.Codec.OpusFS320)
        assertEquals(ListenSocket.Options.Source.Omi, h.options[0].source)
        assertEquals("opus_fs320", h.options[0].codec.rawValue)
        // No mark for an always-on wearable.
        assertNull(h.preferences.string(NativeKey.CaptureActiveSince))
        h.store.ingestDeviceAudio(byteArrayOf(1, 2, 3))
        h.sockets[0].emit(ListenEvent.Status("disconnected: reset"))
        assertEquals(listOf("socket_lost"), h.sockets[0].closes)
        h.store.ingestDeviceAudio(byteArrayOf(4, 5, 6))
        advanceUntilIdle()
        assertEquals(2, h.sockets.size)
        assertEquals(h.options[0].clientConversationID, h.options[1].clientConversationID)
        assertEquals(listOf(4.toByte(), 5, 6), h.sockets[1].audio.single().toList())
        h.store.deviceDisconnected()
        assertEquals(CaptureStore.Phase.Idle, h.store.phase)
        assertEquals(listOf("device_disconnected"), h.sockets[1].closes)
    }

    @Test
    fun aMutedOmiDropsItsAudio() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.isDeviceMuted = true
        h.store.startDevice(ListenSocket.Options.Codec.Opus)
        assertTrue(h.store.isPaused)
        h.store.ingestDeviceAudio(byteArrayOf(1, 2, 3))
        assertTrue(h.sockets.single().audio.isEmpty())
        assertTrue(h.preferences.bool(NativeKey.DeviceMuted, false))
    }

    @Test
    fun theMinutesRunningOutShowANotice() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()
        h.sockets.single().emit(ListenEvent.FreemiumThreshold(300, requiresOnDevice = false))
        assertEquals(TranscriptionNotice.MinutesRunningLow(300), h.store.transcriptionNotice)
        // Out of minutes: without the phone's preview the recording stays on Omi's transcription.
        h.sockets.single().emit(ListenEvent.FreemiumThreshold(0, requiresOnDevice = true))
        assertEquals(TranscriptionNotice.MinutesRunningLow(0), h.store.transcriptionNotice)
        assertEquals("""{"mode":"on_device"}""", h.preferences.string(Key.TranscriptionAllowanceLastKnown))
    }

    @Test
    fun theServerModelAndVadGateGoIntoTheSocketOptions() = runTest(UnconfinedTestDispatcher()) {
        val preferences = freshPreferences()
        preferences.set(Key.VadGateEnabled, true)
        preferences.set(Key.ConversationSilenceDuration, 600)
        val h = harness(preferences)
        h.store.usesParakeet = true
        h.store.startPhone()
        assertEquals("parakeet", h.options.single().sttService)
        assertTrue(h.options.single().vadGate)
        assertEquals(600, h.options.single().conversationTimeout)
    }

    @Test
    fun previewTailKeepsOnlyWordsTheServerHasNotSent() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.segments = listOf(LiveSegment("s1", "one two", null, 0, true, 0.0, 2.0))
        val tail = h.store.previewTail(LiveSegment("p", "one two three four", null, 0, true, 0.0, 3.0))
        assertEquals("three four", tail?.text)
        assertNull(h.store.previewTail(LiveSegment("p", "one", null, 0, true, 0.0, 1.0)))
    }

    @Test
    fun aConversationTheServerClosesStartsAFreshTranscript() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        var finished = 0
        h.store.onConversationFinished = { finished += 1 }
        h.store.startPhone()
        val socket = h.sockets.single()
        socket.emit(ListenEvent.ConversationStarted("c7"))
        socket.emit(ListenEvent.Segments(listOf(LiveSegment("s1", "Bye", null, 0, true, 0.0, 1.0))))
        socket.emit(ListenEvent.ConversationCreated("c7"))
        assertEquals("c7", h.store.lastConversationID)
        assertTrue(h.store.segments.isEmpty())
        assertNull(h.preferences.string(NativeKey.CaptureOpenConversation))
        assertEquals(1, finished)
        assertTrue(h.store.isLive)
    }
}

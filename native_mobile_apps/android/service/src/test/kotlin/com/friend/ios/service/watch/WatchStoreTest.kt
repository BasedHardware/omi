package com.friend.ios.service.watch

import androidx.compose.runtime.snapshots.Snapshot
import com.friend.ios.core.watch.WatchAudioChunk
import com.friend.ios.core.watch.WatchMessage
import com.friend.ios.core.watch.WatchPhoneState
import com.friend.ios.core.watch.WatchStopReason
import com.friend.ios.core.watch.WatchWire
import com.friend.ios.network.APIError
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.PhoneCaptureEngine
import com.friend.ios.service.PhoneCaptureStreams
import com.friend.ios.service.UnavailableDeviceTranscriptionEngine
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import com.friend.ios.service.stores.CaptureStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Data Layer stand-in: tests push the watch's messages and read what the phone sent back. */
class FakeWatchLink(
    override var isWatchPaired: Boolean = true,
    override var isWatchAppInstalled: Boolean = true,
) : WatchLink {
    private val incoming = MutableSharedFlow<WatchMessage>(extraBufferCapacity = 64)
    override val messages: Flow<WatchMessage> = incoming
    val sent = mutableListOf<WatchMessage>()
    val states = mutableListOf<WatchPhoneState>()

    /** The watch sends its bytes; the phone sees what the Data Layer would deliver. */
    fun receive(message: WatchMessage) {
        WatchWire.message(WatchWire.encode(message))?.let { check(incoming.tryEmit(it)) }
    }

    override fun send(message: WatchMessage) {
        sent += message
    }

    override fun updateState(state: WatchPhoneState) {
        states += state
    }
}

/** Port of `WatchStoreTests` (WatchTests.swift). */
@OptIn(ExperimentalCoroutinesApi::class)
class WatchStoreTest {
    private class FakeChannel : LiveTranscriptionChannel {
        val incoming = Channel<ListenEvent>(Channel.UNLIMITED)
        override val events: Flow<ListenEvent> = incoming.receiveAsFlow()
        val audio = mutableListOf<ByteArray>()
        val closes = mutableListOf<String>()
        val audioBytes get() = audio.sumOf { it.size }

        override fun send(audio: ByteArray) {
            this.audio += audio
        }

        override fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String) {}

        override fun close(reason: String) {
            closes += reason
            incoming.close()
        }
    }

    private class FakeEngine : PhoneCaptureEngine {
        val pcm = Channel<ByteArray>(Channel.UNLIMITED)

        override suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams {
            if (transcribeOnDevice) throw com.friend.ios.service.CaptureFailure.SpeechUnavailable
            return PhoneCaptureStreams(pcm.receiveAsFlow(), Channel<Float>().receiveAsFlow(), null)
        }

        override fun stop() {}
    }

    private class Harness(val api: FakeAPI, val link: FakeWatchLink, val capture: CaptureStore, val sockets: List<FakeChannel>, val options: List<ListenSocket.Options>) {
        lateinit var store: WatchStore
        var signedIn: Boolean? = true
        var omiBattery: Int? = null
        val socket: FakeChannel get() = sockets.single()
    }

    private fun TestScope.harness(signInWaitMillis: Long = 200, failSocket: Boolean = false): Harness {
        val sockets = mutableListOf<FakeChannel>()
        val options = mutableListOf<ListenSocket.Options>()
        val api = fakeAPI {
            if (failSocket) {
                "openListenSocket" throws APIError.Transport("offline")
            } else {
                "openListenSocket" does { args ->
                    options += args[1] as ListenSocket.Options
                    FakeChannel().also { sockets += it }
                }
            }
            "finalizeInProgressConversation" returns "c1"
            "subscription" throws APIError.Transport("offline")
        }
        val scope = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[Job]!!)
        val capture = CaptureStore(
            api.client, FakeEngine(), UnavailableDeviceTranscriptionEngine(), freshPreferences(), defaultOnDevice = false,
            userID = { "alice" }, scope = scope, clock = { 1_000_000L },
        )
        val link = FakeWatchLink()
        val h = Harness(api, link, capture, sockets, options)
        h.store = WatchStore(link, capture, isSignedIn = { h.signedIn }, omiBattery = { h.omiBattery }, scope = scope, signInWaitMillis = signInWaitMillis)
        h.store.start()
        return h
    }

    /** Compose applies snapshot writes on its frame clock; tests do it by hand. */
    private fun TestScope.settle() {
        Snapshot.sendApplyNotifications()
        runCurrent()
    }

    @Test
    fun watchRecordingStreamsIntoAnAppleWatchConversation() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        var finished = false
        h.capture.onConversationFinished = { finished = true }
        h.link.receive(WatchMessage.StartRecording)
        h.link.receive(WatchMessage.AudioChunk(WatchAudioChunk(ByteArray(48000) { 1 }, 0, false)))
        settle()
        assertEquals(48000, h.socket.audioBytes)
        assertEquals(CaptureStore.Source.Watch, h.capture.source)
        assertTrue(h.capture.isLive)
        assertEquals(listOf(ListenSocket.Options.Source.AppleWatch), h.options.map { it.source })
        assertEquals("apple_watch", ListenSocket.Options.Source.AppleWatch.rawValue)
        assertEquals(ListenSocket.Options.Codec.Pcm16, h.options.first().codec)
        assertEquals(16000, h.options.first().sampleRate)
        // 1.5 s chunk -> fifteen 100 ms socket messages.
        assertEquals(15, h.socket.audio.size)

        h.link.receive(WatchMessage.AudioChunk(WatchAudioChunk(ByteArray(0), 1, true)))
        h.link.receive(WatchMessage.StopRecording(null))
        settle()
        assertFalse(h.capture.isLive)
        assertEquals(1, h.api.called("finalizeInProgressConversation").size)
        assertEquals(listOf("user_stop"), h.socket.closes)
        assertTrue(finished)
        // The watch stopped itself; the phone does not echo a stop back.
        assertTrue(h.link.sent.isEmpty())
    }

    @Test
    fun stoppingOnThePhoneStopsTheWatch() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.link.receive(WatchMessage.StartRecording)
        settle()
        assertTrue(h.capture.isLive)
        h.capture.stop()
        assertEquals(listOf<WatchMessage>(WatchMessage.StopRecording(null)), h.link.sent)
        assertEquals(1, h.api.called("finalizeInProgressConversation").size)
    }

    @Test
    fun audioOutsideAWatchRecordingIsDropped() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.link.receive(WatchMessage.AudioChunk(WatchAudioChunk(ByteArray(3200) { 1 }, 7, false)))
        h.link.receive(WatchMessage.BatteryUpdate(55.4, 1))
        settle()
        assertEquals(55, h.store.battery)
        assertTrue(h.options.isEmpty())
        assertTrue(h.sockets.isEmpty())
    }

    @Test
    fun phoneAlreadyRecordingRefusesTheWatch() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.capture.startPhone()
        h.link.receive(WatchMessage.StartRecording)
        settle()
        assertEquals(listOf<WatchMessage>(WatchMessage.StopRecording(WatchStopReason.Busy)), h.link.sent)
        assertEquals(CaptureStore.Source.Phone, h.capture.source)
    }

    @Test
    fun signedOutPhoneRefusesTheWatch() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(signInWaitMillis = 50)
        h.signedIn = false
        h.link.receive(WatchMessage.StartRecording)
        settle()
        assertEquals(listOf<WatchMessage>(WatchMessage.StopRecording(WatchStopReason.SignedOut)), h.link.sent)
        assertFalse(h.capture.isLive)
    }

    @Test
    fun aSessionThatNeverRestoresRefusesTheWatchAfterTheWait() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(signInWaitMillis = 2_000)
        h.signedIn = null
        h.link.receive(WatchMessage.StartRecording)
        advanceTimeBy(1_900)
        assertTrue(h.link.sent.isEmpty())
        advanceTimeBy(200)
        assertEquals(listOf<WatchMessage>(WatchMessage.StopRecording(WatchStopReason.SignedOut)), h.link.sent)
    }

    @Test
    fun waitsForTheSessionToRestore() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(signInWaitMillis = 2_000)
        h.signedIn = null
        h.link.receive(WatchMessage.StartRecording)
        advanceTimeBy(80)
        assertFalse(h.capture.isLive)
        h.signedIn = true
        advanceTimeBy(60)
        assertTrue(h.capture.isLive)
        assertEquals(CaptureStore.Source.Watch, h.capture.source)
        assertTrue(h.link.sent.isEmpty())
    }

    @Test
    fun failedSocketTellsTheWatch() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(failSocket = true)
        h.link.receive(WatchMessage.StartRecording)
        settle()
        assertEquals(listOf<WatchMessage>(WatchMessage.StopRecording(WatchStopReason.Failed)), h.link.sent)
    }

    @Test
    fun mirrorsCaptureAndOmiBatteryToTheWatch() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        settle()
        assertEquals(listOf(WatchPhoneState(WatchPhoneState.Capture.Idle, null)), h.link.states)
        h.link.receive(WatchMessage.StartRecording)
        settle()
        assertEquals(WatchPhoneState(WatchPhoneState.Capture.Watch, null), h.link.states.last())
        h.capture.stop()
        settle()
        assertEquals(WatchPhoneState.Capture.Idle, h.link.states.last().capture)
    }

    @Test
    fun theMicrophoneAnswerOrTheWaitEndsTheRequest() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.requestMicrophone(answerWaitMillis = 1_000)
        assertTrue(h.store.isRequestingMicrophone)
        assertEquals(listOf<WatchMessage>(WatchMessage.RequestMicrophonePermission), h.link.sent)
        h.link.receive(WatchMessage.MicrophonePermissionResult(true))
        settle()
        assertEquals(true, h.store.microphoneGranted)
        assertFalse(h.store.isRequestingMicrophone)

        // A watch that never answers.
        h.store.requestMicrophone(answerWaitMillis = 1_000)
        advanceTimeBy(1_001)
        assertFalse(h.store.isRequestingMicrophone)
    }

    @Test
    fun recordWithWatchAsksTheWatchAndItsReportMakesItAvailable() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        assertFalse(h.store.isAvailable)
        assertNull(h.store.info)
        h.store.ping()
        assertEquals(listOf(WatchMessage.RequestBattery, WatchMessage.RequestWatchInfo), h.link.sent)
        h.link.receive(WatchMessage.WatchInfoUpdate(com.friend.ios.core.watch.WatchInfo("Pixel Watch 3", "Pixel Watch 3", "34", "Wear OS")))
        settle()
        assertTrue(h.store.isAvailable)
        assertTrue(h.store.isWatchPaired)
        assertTrue(h.store.isWatchAppInstalled)
        h.store.startFromPhone()
        assertEquals(WatchMessage.StartRecording, h.link.sent.last())
    }
}

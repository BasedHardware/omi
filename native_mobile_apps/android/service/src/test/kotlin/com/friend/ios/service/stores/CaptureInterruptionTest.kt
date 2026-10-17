package com.friend.ios.service.stores

import com.friend.ios.audio.AudioSessionEvent
import com.friend.ios.audio.AudioSessionMonitoring
import com.friend.ios.network.APIError
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.service.CaptureFailure
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.PhoneCaptureEngine
import com.friend.ios.service.PhoneCaptureStreams
import com.friend.ios.service.UnavailableDeviceTranscriptionEngine
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
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

/**
 * Port of `CaptureInterruptionTests.swift` (iOS fc5cb67): the phone recording survives the system
 * taking the microphone, and the health watch is the only thing that notices an engine that died
 * without saying so.
 *
 * The clock is fixed, so every notice and every recording id is comparable. The health watch is
 * driven by the test's virtual clock ([ticks]) instead of iOS's real 10 ms sleeps, which is why a
 * probe that iOS waits for happens here exactly when the test asks for it.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class CaptureInterruptionTest {
    /** The health watch's tick: [ticks] advances exactly this much per call. */
    private companion object {
        const val TICK_MILLIS = 10L
        const val NOW = 1_000_000L
    }

    /**
     * Answers `start` with fresh streams every time, so a test can see a recording come back to
     * life. `canStart` is false while a call still holds the microphone.
     *
     * [recoversItself] is false here: this is iOS's engine, which is dead after an interruption and
     * only a fresh start brings back. Android's capture controller parks a silenced session instead
     * (`aControllerThatRecoversItselfIsNotFought` models that one).
     */
    private class ResumablePhoneEngine(
        var canStart: Boolean = true,
        override var recoversItself: Boolean = false,
    ) : PhoneCaptureEngine {
        /** How often the store asked for the microphone, successful or not. */
        var attempts = 0

        /** How often it got it. */
        var starts = 0

        var stops = 0

        override var isRunning = false

        /** The audio of the start that is live now; each start replaces it. */
        var pcm = Channel<ByteArray>(Channel.UNLIMITED)

        override suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams {
            attempts += 1
            if (!canStart) throw CaptureFailure.MicrophonePermission
            starts += 1
            isRunning = true
            pcm = Channel(Channel.UNLIMITED)
            return PhoneCaptureStreams(pcm.receiveAsFlow(), Channel<Float>().receiveAsFlow(), null)
        }

        override fun stop() {
            stops += 1
            isRunning = false
        }
    }

    /** The OS signals, driven by hand (`FakeAudioSessionMonitor` on iOS). */
    private class FakeAudioSessionMonitor : AudioSessionMonitoring {
        var started = false
            private set

        var stopped = false
            private set

        private var handler: ((AudioSessionEvent) -> Unit)? = null

        override fun start(onEvent: (AudioSessionEvent) -> Unit) {
            started = true
            handler = onEvent
        }

        override fun stop() {
            stopped = true
            handler = null
        }

        fun send(event: AudioSessionEvent) {
            handler?.invoke(event)
        }
    }

    /** Where the phone's audio goes when it cannot be streamed (`SyncStore` in the app). */
    private class FakePhoneBuffer : PhoneAudioBuffering {
        var began = 0
        var ends = 0
        val chunks = mutableListOf<ByteArray>()
        val keptChunks = mutableListOf<ByteArray>()

        override fun beginPhoneAudio(manual: Boolean) {
            began += 1
        }

        override fun appendPhoneAudio(pcm: ByteArray) {
            chunks += pcm
        }

        override fun endPhoneAudio() {
            ends += 1
        }

        override fun beginKeptCopy(source: KeptAudioSource) {}

        override fun appendKeptCopy(audio: ByteArray) {
            keptChunks += audio
        }

        override fun endKeptCopy() {}
    }

    /** The socket as the store sees it: what it was sent, and a way to push server events. */
    private class FakeChannel : LiveTranscriptionChannel {
        val incoming = Channel<ListenEvent>(Channel.UNLIMITED)
        override val events: Flow<ListenEvent> = incoming.receiveAsFlow()
        val audio = mutableListOf<ByteArray>()
        val closes = mutableListOf<String>()

        override fun send(audio: ByteArray) {
            this.audio += audio
        }

        override fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String) {}

        override fun close(reason: String) {
            closes += reason
            incoming.close()
        }

        override fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) {}

        fun emit(event: ListenEvent) {
            incoming.trySend(event)
        }
    }

    private class Harness(
        val api: FakeAPI,
        val engine: ResumablePhoneEngine,
        val session: FakeAudioSessionMonitor,
        val buffer: FakePhoneBuffer,
        val store: CaptureStore,
        val sockets: MutableList<FakeChannel>,
        val options: MutableList<ListenSocket.Options>,
    )

    private fun TestScope.harness(
        engine: ResumablePhoneEngine = ResumablePhoneEngine(),
        session: FakeAudioSessionMonitor = FakeAudioSessionMonitor(),
        buffer: FakePhoneBuffer = FakePhoneBuffer(),
        preferences: Preferences = freshPreferences(),
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
        }
        val scope = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[Job]!!)
        val store = CaptureStore(
            api.client, engine, UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope, clock = { NOW }, healthTickMillis = TICK_MILLIS, audioSession = session,
        )
        store.phoneBuffer = buffer
        return Harness(api, engine, session, buffer, store, sockets, options)
    }

    /**
     * Waits (in the test's own virtual time) until the condition holds. Always a state the store
     * publishes, never an engine's own counter: a fake engine counts a start before the store's
     * continuation has run, which made iOS's version of this flaky under load.
     */
    private fun TestScope.settle(until: () -> Boolean) {
        repeat(400) {
            if (until()) return
            advanceTimeBy(5)
            runCurrent()
        }
    }

    /** Lets the health watch tick [count] times. */
    private fun TestScope.ticks(count: Int) {
        advanceTimeBy(TICK_MILLIS * count)
        runCurrent()
    }

    @Test
    fun aCallPausesCaptureAndSaysWhy() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()
        assertTrue(h.session.started)
        assertEquals(1, h.engine.starts)

        // The OS silences the recording, which is what parks the controller's session; the store is
        // told straight after.
        h.engine.isRunning = false
        h.session.send(AudioSessionEvent.Interrupted)
        assertEquals(CaptureNotice.MicrophoneTaken(NOW), h.store.notice)
        assertTrue(h.store.isPaused)
        // Android difference: the engine is not stopped here. The controller holds the parked
        // session, and stopping it would throw away the recording the system only silenced.
        assertEquals(0, h.engine.stops)
        // Still live: the conversation, the socket and the file all stay.
        assertTrue(h.store.isLive)
    }

    @Test
    fun captureComesBackWhenTheInterruptionEnds() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()
        h.engine.isRunning = false
        h.session.send(AudioSessionEvent.Interrupted)
        assertTrue(h.store.isPaused)

        h.session.send(AudioSessionEvent.InterruptionEnded(shouldResume = true))
        settle { !h.store.isPaused && h.store.notice == null }
        assertFalse(h.store.isPaused)
        assertNull(h.store.notice)
        assertTrue(h.engine.starts >= 2)
    }

    /**
     * iOS omits `shouldResume` when another app's audio ends the interruption, so the app probes
     * anyway instead of leaving the recording silent for good. Android's monitor always sends true,
     * which makes this the path a false one would take.
     */
    @Test
    fun captureProbesEvenWithoutShouldResume() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()
        h.engine.isRunning = false

        h.session.send(AudioSessionEvent.Interrupted)
        h.session.send(AudioSessionEvent.InterruptionEnded(shouldResume = false))
        settle { !h.store.isPaused && h.store.notice == null }
        assertFalse(h.store.isPaused)
        assertNull(h.store.notice)
        assertTrue(h.engine.starts >= 2)
    }

    @Test
    fun aMicrophoneThatStaysTakenKeepsTryingAndStaysVisible() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()

        h.engine.canStart = false
        h.engine.isRunning = false
        h.session.send(AudioSessionEvent.Interrupted)
        h.session.send(AudioSessionEvent.InterruptionEnded(shouldResume = true))
        settle { h.engine.attempts >= 3 }
        // Every probe was refused, and the recording is still there to be continued.
        assertTrue(h.store.isLive)
        assertTrue(h.store.isPaused)
        assertEquals(CaptureNotice.MicrophoneTaken(NOW), h.store.notice)

        h.engine.canStart = true
        settle { !h.store.isPaused }
        assertFalse(h.store.isPaused)
        assertNull(h.store.notice)
    }

    @Test
    fun aRouteWithoutAnInputPausesWithItsOwnReason() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()

        h.engine.isRunning = false
        h.session.send(AudioSessionEvent.RouteChanged(input = null))
        assertEquals(CaptureNotice.InputGone, h.store.notice)
        assertTrue(h.store.isPaused)

        h.session.send(AudioSessionEvent.RouteChanged(input = "Built-in Microphone"))
        settle { !h.store.isPaused && h.store.notice == null }
        assertNull(h.store.notice)
        assertFalse(h.store.isPaused)
        assertTrue(h.engine.starts >= 2)
    }

    /** The user's own pause is not the system's: no banner, and the app does not fight the user. */
    @Test
    fun aUserPauseClearsTheNoticeAndDoesNotRestart() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()

        h.store.pause()
        ticks(6)
        assertEquals(1, h.engine.starts)
        assertNull(h.store.notice)

        h.store.resume()
        assertNull(h.store.notice)
        assertFalse(h.store.isPaused)
        assertEquals(2, h.engine.starts)
    }

    @Test
    fun aResumeTheSystemRefusesStaysVisibleAndTriesAgain() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()

        h.store.pause()
        h.engine.canStart = false
        h.store.resume()
        assertTrue(h.store.isLive)
        assertTrue(h.store.isPaused)
        assertEquals(CaptureNotice.MicrophoneTaken(NOW), h.store.notice)

        h.engine.canStart = true
        settle { !h.store.isPaused }
        assertFalse(h.store.isPaused)
    }

    /**
     * A dead engine with no notification at all (competing audio stops the tap): the health watch is
     * the only thing that can notice, and it takes the microphone back.
     */
    @Test
    fun aSilentlyDeadEngineIsTakenBack() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()

        h.engine.isRunning = false
        settle { h.engine.isRunning && h.engine.starts >= 2 }
        assertTrue(h.engine.isRunning)
        assertTrue(h.store.isLive)
        assertFalse(h.store.isPaused)
        assertNull(h.store.notice)
    }

    @Test
    fun stoppingTheRecordingEndsTheHealthWatch() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()
        h.sockets.single().emit(ListenEvent.ConversationStarted("c1"))

        h.store.stop()
        assertTrue(h.session.stopped)
        assertEquals(CaptureStore.Phase.Idle, h.store.phase)
        val attempts = h.engine.attempts
        ticks(6)
        assertEquals(attempts, h.engine.attempts)
    }

    @Test
    fun dismissingTheNoticeLeavesTheRecordingAlone() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startPhone()

        h.engine.isRunning = false
        h.session.send(AudioSessionEvent.Interrupted)
        assertTrue(h.store.notice != null)
        h.store.dismissNotice()
        assertNull(h.store.notice)
        assertTrue(h.store.isLive)
    }

    /** A failed start before the recording is live is still a failure: nothing is on disk yet. */
    @Test
    fun aFailedFirstStartStillFails() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(engine = ResumablePhoneEngine(canStart = false))
        h.store.startPhone()
        assertEquals(CaptureStore.Phase.Failed("microphone"), h.store.phase)
        assertFalse(h.store.isLive)
        assertTrue(h.sockets.isEmpty())
    }

    /** The Omi's audio arrives over Bluetooth and never uses the app's audio session. */
    @Test
    fun theWatchOfTheDeviceIgnoresSessionEvents() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.startDevice(ListenSocket.Options.Codec.OpusFS320)
        h.session.send(AudioSessionEvent.Interrupted)
        assertNull(h.store.notice)
        assertFalse(h.session.started)
    }

    // MARK: Android only

    /**
     * Android's capture controller parks a session the system silenced and brings it back on its own
     * ticker, keeping the engine (`PhoneMicController`). The store must not open the microphone again
     * every three seconds: that would fight the controller and re-acquire the microphone for the
     * length of a call. Once the controller has the session back, the same streams carry on.
     */
    @Test
    fun aControllerThatRecoversItselfIsNotFought() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(engine = ResumablePhoneEngine(recoversItself = true))
        h.store.startPhone()
        assertEquals(1, h.engine.starts)

        h.engine.isRunning = false
        h.session.send(AudioSessionEvent.Interrupted)
        assertTrue(h.store.isPaused)
        assertEquals(CaptureNotice.MicrophoneTaken(NOW), h.store.notice)

        ticks(6)
        assertEquals(1, h.engine.starts)
        assertEquals(0, h.engine.stops)
        assertTrue(h.store.isPaused)

        // The controller has the microphone again: the recording carries on where it left off.
        h.engine.isRunning = true
        ticks(1)
        assertFalse(h.store.isPaused)
        assertNull(h.store.notice)
        assertEquals(1, h.engine.starts)
        h.engine.pcm.send(ByteArray(64) { 3 })
        assertEquals(64, h.sockets.single().audio.single().size)
    }

    /**
     * A dropped phone socket is reopened with the same options and recording id: the rest of the
     * conversation is transcribed live again instead of waiting for an upload at the end. The audio
     * of the gap goes to the phone's file, nothing is lost.
     */
    @Test
    fun aDroppedPhoneSocketIsReopened() = runTest(UnconfinedTestDispatcher()) {
        val preferences = freshPreferences()
        // Settings > Privacy > Store audio on phone, so the kept copy is on too.
        preferences.set(Key.UnlimitedLocalStorageEnabled, true)
        val h = harness(preferences = preferences)
        h.store.phoneReconnectDelays = listOf(10L)
        h.store.startPhone()
        h.sockets[0].emit(ListenEvent.ConversationStarted("c1"))

        h.sockets[0].emit(ListenEvent.Status("disconnected: reset"))
        assertEquals(listOf("socket_lost"), h.sockets[0].closes)
        assertTrue(h.store.isBuffering)
        assertEquals(CaptureRecovery.ConnectionLost, h.store.recovery)
        h.engine.pcm.send(ByteArray(32) { 5 })
        // The gap is on the phone (and in the kept copy of what streams live), not on a socket.
        assertEquals(1, h.buffer.chunks.size)
        assertEquals(1, h.buffer.keptChunks.size)

        ticks(1)
        assertEquals(2, h.sockets.size)
        assertEquals(h.options[0].clientConversationID, h.options[1].clientConversationID)
        assertFalse(h.store.isBuffering)
        assertNull(h.store.recovery)
        assertEquals(1, h.buffer.ends)
        h.engine.pcm.send(ByteArray(16) { 9 })
        assertEquals(16, h.sockets[1].audio.single().size)

        h.store.stop()
        assertEquals(listOf("socket_lost"), h.sockets[0].closes)
        assertEquals(listOf("user_stop"), h.sockets[1].closes)
    }

    /** The recording ended while the socket was away: no reconnect may open one behind its back. */
    @Test
    fun stoppingWhileReconnectingEndsThePhoneReconnect() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.phoneReconnectDelays = listOf(50L)
        h.store.startPhone()
        h.sockets[0].emit(ListenEvent.ConversationStarted("c1"))
        h.sockets[0].emit(ListenEvent.Status("disconnected: reset"))

        h.store.stop()
        ticks(20)
        assertEquals(CaptureStore.Phase.Idle, h.store.phase)
        assertFalse(h.store.reconnectingPhone)
        assertEquals(1, h.sockets.size)
    }
}

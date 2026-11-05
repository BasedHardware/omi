package com.friend.ios.service.stores

import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.PhoneCallErrorDetail
import com.friend.ios.network.endpoints.PhoneCallToken
import com.friend.ios.network.endpoints.PhoneVerification
import com.friend.ios.network.endpoints.VerifiedPhoneNumber
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.PhoneCallSocketEvent
import com.friend.ios.network.listen.PhoneCallTranscriptChannel
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.phonecalls.PhoneCallAudio
import com.friend.ios.service.phonecalls.PhoneCallEngine
import com.friend.ios.service.phonecalls.PhoneCallEngineEvent
import com.friend.ios.service.phonecalls.PhoneCallFailure
import com.friend.ios.service.phonecalls.PhoneCallRequest
import com.friend.ios.service.phonecalls.PhoneCallStreams
import com.friend.ios.service.phonecalls.PhoneNumberFormat
import com.friend.ios.service.stores.PhoneCallStore.Phase
import com.friend.ios.service.stores.PhoneCallStore.TranscriptionStatus
import com.friend.ios.service.stores.PhoneCallStore.Verification
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import kotlin.time.Duration.Companion.milliseconds

/** Port of `PhoneCallTests.swift` and `PhoneNumberTests.swift`. */
@OptIn(ExperimentalCoroutinesApi::class)
class PhoneCallStoreTest {
    /** Twilio + Telecom stand-in: tests push the call's events and audio. */
    private class FakeCallEngine : PhoneCallEngine {
        val events = Channel<PhoneCallEngineEvent>(Channel.UNLIMITED)
        val audio = Channel<PhoneCallAudio>(Channel.UNLIMITED)
        var micGranted = true
        var startError: Exception? = null
        val requests = mutableListOf<PhoneCallRequest>()
        var ended = 0
        val mutes = mutableListOf<Boolean>()
        val speakers = mutableListOf<Boolean>()
        val digits = mutableListOf<String>()

        override suspend fun requestMicrophonePermission(): Boolean = micGranted

        override suspend fun start(request: PhoneCallRequest): PhoneCallStreams {
            startError?.let { throw it }
            requests += request
            return PhoneCallStreams(events.receiveAsFlow(), audio.receiveAsFlow())
        }

        override fun end() {
            ended += 1
        }

        override fun setMuted(muted: Boolean) {
            mutes += muted
        }

        override fun setSpeaker(on: Boolean) {
            speakers += on
        }

        override fun sendDigits(digits: String) {
            this.digits += digits
        }

        fun emit(event: PhoneCallEngineEvent) {
            events.trySend(event)
        }

        fun play(channel: PhoneCallAudio.Channel, bytes: Int = 4) {
            audio.trySend(PhoneCallAudio(channel, ByteArray(bytes) { channel.rawValue }))
        }
    }

    private class FakeChannel : PhoneCallTranscriptChannel {
        val incoming = Channel<PhoneCallSocketEvent>(Channel.UNLIMITED)
        override val events: Flow<PhoneCallSocketEvent> = incoming.receiveAsFlow()
        val frames = mutableListOf<ByteArray>()
        var isClosed = false

        override fun send(frame: ByteArray) {
            frames += frame
        }

        override fun close() {
            isClosed = true
            incoming.close()
        }

        fun emit(event: PhoneCallSocketEvent) {
            incoming.trySend(event)
        }

        /** The network drops it. */
        fun drop() {
            incoming.trySend(PhoneCallSocketEvent.Closed("dropped"))
            incoming.close()
        }
    }

    private data class SocketRequest(val uid: String, val callID: String, val language: String)

    private class Harness(val api: FakeAPI, val engine: FakeCallEngine, val store: PhoneCallStore) {
        val sockets = mutableListOf<FakeChannel>()
        val socketRequests = mutableListOf<SocketRequest>()
        var socketError: Exception? = null
        val socket: FakeChannel? get() = sockets.lastOrNull()
    }

    private val now: Instant = Instant.ofEpochSecond(1_790_848_800)
    private val timing = PhoneCallStore.Timing(
        verificationPoll = 1.milliseconds, endedLinger = 20.milliseconds, reconnectBase = 5.milliseconds,
        noAudioTimeout = 30.milliseconds, historyRefreshDelay = 1.milliseconds,
    )

    private suspend fun TestScope.harness(
        verified: Boolean = true,
        timing: PhoneCallStore.Timing = this@PhoneCallStoreTest.timing,
        setup: FakeAPI.() -> Unit = {},
    ): Harness {
        var harness: Harness? = null
        val api = fakeAPI {
            "verifiedPhoneNumbers" returns if (verified) listOf(VerifiedPhoneNumber("n1", "+15551112222", now, true)) else emptyList()
            "phoneCallToken" returns PhoneCallToken("twilio-token", 3600, "uid-1")
            "openPhoneCallSocket" does { args ->
                val h = harness!!
                h.socketRequests += SocketRequest(args[0] as String, args[1] as String, args[2] as String)
                h.socketError?.let { throw it }
                FakeChannel().also { h.sockets += it }
            }
            "phoneCallConversations" returns emptyList<Any>()
            "phoneCallQuota" returns null
            setup()
        }
        val engine = FakeCallEngine()
        val scope = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[Job]!!)
        val store = PhoneCallStore(api.client, engine, { "uid-1" }, { "de" }, scope, timing, { now })
        harness = Harness(api, engine, store)
        store.loadNumbers()
        return harness
    }

    private fun segment(id: String, text: String, isUser: Boolean = false) =
        LiveSegment(id, text, if (isUser) "SPEAKER_00" else "SPEAKER_01", if (isUser) 0 else 1, isUser, 0.0, 1.0)

    // MARK: Lifecycle

    @Test
    fun aCallGoesConnectingRingingActiveEndedIdle() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        val store = h.store
        var finished = false
        store.onCallFinished = { finished = true }

        assertTrue(store.call("(555) 123-4567", contactName = "Anna"))
        assertEquals(Phase.Connecting, store.phase)
        assertTrue(store.showsCallScreen)
        // A number without + takes the caller's country code; the call id reaches Twilio.
        assertEquals(
            PhoneCallRequest("twilio-token", "+15551234567", now.toEpochMilli().toString(), "Anna"),
            h.engine.requests.single(),
        )
        assertEquals("Anna", store.otherParty)

        h.engine.emit(PhoneCallEngineEvent.Ringing)
        assertEquals(Phase.Ringing, store.phase)
        assertTrue(h.sockets.isEmpty())

        h.engine.emit(PhoneCallEngineEvent.Connected)
        assertEquals(Phase.Active, store.phase)
        assertEquals(now, store.connectedAt)
        assertEquals(SocketRequest("uid-1", store.callID!!, "de"), h.socketRequests.single())

        h.engine.emit(PhoneCallEngineEvent.Ended)
        assertEquals(Phase.Ended, store.phase)
        assertTrue(h.socket!!.isClosed)
        advanceUntilIdle()
        assertEquals(Phase.Idle, store.phase)
        assertNull(store.remoteNumber)
        assertTrue(store.transcript.isEmpty)
        assertFalse(store.showsCallScreen)
        assertTrue(finished)
    }

    @Test
    fun hangingUpEndsTheCallInTheEngine() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.call("+4930123456")
        h.engine.emit(PhoneCallEngineEvent.Connected)
        h.store.end()
        assertEquals(1, h.engine.ended)
        assertEquals(Phase.Ended, h.store.phase)
        assertNull(h.store.failure)
    }

    @Test
    fun aSecondCallWhileOneIsOnIsRefused() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        assertTrue(h.store.call("+4930123456"))
        assertFalse(h.store.call("+4930999999"))
        assertEquals(PhoneCallFailure.AlreadyInProgress, h.store.failure)
        assertEquals(1, h.engine.requests.size)
    }

    @Test
    fun theBackendsReasonIsKeptWhenNoTokenComes() = runTest(UnconfinedTestDispatcher()) {
        val h = harness {
            "phoneCallToken" throws APIError.Http(402, """{"detail":{"error":"phone_call_quota_exceeded","monthly_limit":3}}""")
        }
        assertFalse(h.store.call("+4930123456"))
        assertEquals(Phase.Idle, h.store.phase)
        assertEquals(PhoneCallFailure.Server(PhoneCallErrorDetail.QuotaExceeded(3)), h.store.failure)
        assertTrue(h.engine.requests.isEmpty())
    }

    @Test
    fun withoutMicrophoneOrNumberNoCallStarts() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.engine.micGranted = false
        assertFalse(h.store.call("+4930123456"))
        assertEquals(PhoneCallFailure.MicrophonePermission, h.store.failure)
        assertTrue(h.api.called("phoneCallToken").isEmpty())

        val unverified = harness(verified = false)
        assertFalse(unverified.store.call("+4930123456"))
        assertEquals(PhoneCallFailure.NoVerifiedNumber, unverified.store.failure)
    }

    @Test
    fun theCallSystemRefusingIsAFailure() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.engine.startError = IllegalStateException("Call system rejected the request")
        assertFalse(h.store.call("+4930123456"))
        assertEquals(PhoneCallFailure.Engine("Call system rejected the request"), h.store.failure)
        assertEquals(Phase.Idle, h.store.phase)
    }

    @Test
    fun aTwilioFailureEndsTheCallWithItsMessage() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.call("+4930123456")
        h.engine.emit(PhoneCallEngineEvent.Failed("Call service error: busy"))
        assertEquals(Phase.Ended, h.store.phase)
        assertEquals(PhoneCallFailure.Engine("Call service error: busy"), h.store.failure)
    }

    @Test
    fun muteAndSpeakerFollowTheEnginesConfirmation() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.call("+4930123456")
        h.engine.emit(PhoneCallEngineEvent.Connected)
        h.store.toggleMute()
        assertEquals(listOf(true), h.engine.mutes)
        assertFalse(h.store.isMuted)
        h.engine.emit(PhoneCallEngineEvent.Muted(true))
        assertTrue(h.store.isMuted)
        h.store.toggleSpeaker()
        h.engine.emit(PhoneCallEngineEvent.Speaker(true))
        assertTrue(h.store.isSpeakerOn)
        assertEquals(listOf(true), h.engine.speakers)
        h.store.sendDigit("5")
        assertEquals(listOf("5"), h.engine.digits)
    }

    @Test
    fun pastCallsAreThePhoneCallConversations() = runTest(UnconfinedTestDispatcher()) {
        val conversation = Fixtures.conversation("c1", now)
        val h = harness { "phoneCallConversations" returns listOf(conversation) }
        h.store.load()
        assertEquals(listOf("c1"), h.store.history.map { it.id })
    }

    // MARK: Transcription

    private suspend fun TestScope.activeCall(): Pair<Harness, FakeChannel> {
        val h = harness()
        h.store.call("+4930123456")
        h.engine.emit(PhoneCallEngineEvent.Connected)
        assertEquals(TranscriptionStatus.Connecting, h.store.transcription)
        return h to h.socket!!
    }

    @Test
    fun audioBeforeTheSocketIsBufferedThenSentTaggedByChannel() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.call("+4930123456")
        h.engine.play(PhoneCallAudio.Channel.You)
        h.engine.play(PhoneCallAudio.Channel.Them)
        assertEquals(2, h.store.pendingFrames.size)

        h.engine.emit(PhoneCallEngineEvent.Connected)
        h.engine.play(PhoneCallAudio.Channel.You)
        val socket = h.socket!!
        assertEquals(listOf<Byte>(1, 2, 1), socket.frames.map { it.first() })
        assertArrayEquals(byteArrayOf(2, 2, 2, 2, 2), socket.frames[1])
    }

    @Test
    fun segmentsUpsertByIDAndTranslationsAttach() = runTest(UnconfinedTestDispatcher()) {
        val (h, socket) = activeCall()
        socket.emit(PhoneCallSocketEvent.Segments(listOf(segment("s1", "Hallo"), segment("s2", "Hi", isUser = true))))
        assertEquals(2, h.store.transcript.segments.size)
        assertEquals(TranscriptionStatus.Active, h.store.transcription)
        socket.emit(PhoneCallSocketEvent.Segments(listOf(segment("s1", "Hallo, wie geht's?"))))
        socket.emit(PhoneCallSocketEvent.Translations(mapOf("s1" to listOf("Hello, how are you?"), "unknown" to listOf("dropped"))))
        assertEquals(listOf("Hallo, wie geht's?", "Hi"), h.store.transcript.segments.map { it.text })
        assertEquals(mapOf("s1" to listOf("Hello, how are you?")), h.store.transcript.translations)
        h.store.end()
    }

    @Test
    fun aDroppedSocketReconnectsAndKeepsTheTranscript() = runTest(UnconfinedTestDispatcher()) {
        val (h, socket) = activeCall()
        socket.emit(PhoneCallSocketEvent.Segments(listOf(segment("s1", "Hallo"))))
        socket.drop()
        assertEquals(TranscriptionStatus.Reconnecting, h.store.transcription)
        advanceTimeBy(6)
        runCurrent()
        assertEquals(2, h.sockets.size)
        assertEquals(1, h.store.transcript.segments.size)
        assertTrue(h.socketRequests.all { it.callID == h.store.callID })
        h.store.end()
    }

    @Test
    fun reconnectingGivesUpAfterTenTries() = runTest(UnconfinedTestDispatcher()) {
        val (h, socket) = activeCall()
        h.socketError = APIError.Transport("offline")
        socket.drop()
        // 5, 10, 20 ... ms of backoff, ten tries, then it gives up.
        advanceTimeBy(10_000)
        runCurrent()
        assertEquals(11, h.socketRequests.size)
        assertEquals(TranscriptionStatus.Failed, h.store.transcription)
        h.store.end()
    }

    @Test
    fun anAcceptedSocketWithoutAudioSaysSo() = runTest(UnconfinedTestDispatcher()) {
        val (h, socket) = activeCall()
        // The backend's first frames are `service_status`; they count as accepted, like Flutter.
        socket.emit(PhoneCallSocketEvent.Status("initiating"))
        assertEquals(TranscriptionStatus.Active, h.store.transcription)
        advanceTimeBy(31)
        runCurrent()
        assertEquals(TranscriptionStatus.NoAudio, h.store.transcription)
        h.engine.play(PhoneCallAudio.Channel.Them)
        assertEquals(TranscriptionStatus.Active, h.store.transcription)
        h.store.end()
    }

    @Test
    fun endingTheCallClosesTheSocketAndStopsReconnecting() = runTest(UnconfinedTestDispatcher()) {
        val (h, socket) = activeCall()
        h.store.end()
        assertTrue(socket.isClosed)
        advanceTimeBy(30)
        runCurrent()
        assertEquals(1, h.sockets.size)
    }

    @Test
    fun aDebugCallShowsWithoutTheEngine() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.debugPresent("+4930123456", "Anna", listOf(segment("s1", "Hallo")))
        assertEquals(Phase.Active, h.store.phase)
        assertTrue(h.store.showsCallScreen)
        assertTrue(h.engine.requests.isEmpty())
        assertTrue(h.sockets.isEmpty())
        assertEquals(1, h.store.transcript.segments.size)
    }

    // MARK: Verification (PhoneNumberTests.swift)

    @Test
    fun verifyingShowsTheCodeThenStoresTheNumber() = runTest(UnconfinedTestDispatcher()) {
        var checks = 0
        val h = harness(verified = false) {
            "startPhoneVerification" returns PhoneVerification("", "123456", "pending")
            "checkPhoneVerification" does {
                checks += 1
                checks == 3
            }
        }
        val store = h.store
        assertTrue(store.numbers.isEmpty() && store.numbersLoaded)
        assertTrue(store.startVerification("+4915112345678"))
        assertEquals("123456", store.verification?.code)
        assertEquals(Verification.Status.Calling, store.verification?.status)
        assertEquals(listOf(listOf<Any?>("+4915112345678")), h.api.called("startPhoneVerification"))

        h.api.apply { "verifiedPhoneNumbers" returns listOf(VerifiedPhoneNumber("n2", "+4915112345678", now, true)) }
        store.pollVerification()
        assertEquals(Verification.Status.Verified, store.verification?.status)
        assertEquals(3, checks)
        assertEquals(listOf("+4915112345678"), store.numbers.map { it.phoneNumber })
    }

    @Test
    fun anUnansweredCallIsMissedThenTimesOut() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(verified = false) {
            "startPhoneVerification" returns PhoneVerification("", "123456", "pending")
            "checkPhoneVerification" returns false
        }
        h.store.startVerification("+4915112345678")
        h.store.pollVerification()
        assertEquals(Verification.Status.TimedOut, h.store.verification?.status)
        assertEquals(30, h.api.called("checkPhoneVerification").size)
    }

    @Test
    fun statusMovesFromCallingToInProgressToMissed() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(verified = false, timing = PhoneCallStore.Timing(verificationPoll = 10.milliseconds)) {
            "startPhoneVerification" returns PhoneVerification("", "123456", "pending")
            "checkPhoneVerification" returns false
        }
        h.store.startVerification("+4915112345678")
        val poll = backgroundScope.launch { h.store.pollVerification() }
        advanceTimeBy(21)
        runCurrent()
        assertEquals(Verification.Status.InProgress, h.store.verification?.status)
        advanceTimeBy(130)
        runCurrent()
        assertEquals(Verification.Status.Missed, h.store.verification?.status)
        poll.cancel()
    }

    @Test
    fun retryingCallsAgainAndPolls() = runTest(UnconfinedTestDispatcher()) {
        var verifiedNow = false
        val h = harness(verified = false) {
            "startPhoneVerification" returns PhoneVerification("", "123456", "pending")
            "checkPhoneVerification" does { verifiedNow }
        }
        h.store.startVerification("+4915112345678")
        h.store.pollVerification()
        verifiedNow = true
        h.store.retryVerification()
        assertEquals(2, h.api.called("startPhoneVerification").size)
        assertEquals(Verification.Status.Verified, h.store.verification?.status)
    }

    @Test
    fun theBackendsRefusalIsShown() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(verified = false) {
            "startPhoneVerification" throws APIError.Http(409, """{"detail":"Phone number already verified"}""")
        }
        assertFalse(h.store.startVerification("+4915112345678"))
        assertEquals(PhoneCallFailure.Server(PhoneCallErrorDetail.Message("Phone number already verified")), h.store.verificationFailure)
        assertNull(h.store.verification)
    }

    @Test
    fun anAlreadyVerifiedNumberNeedsNoCall() = runTest(UnconfinedTestDispatcher()) {
        val h = harness(verified = false) { "startPhoneVerification" returns PhoneVerification("", null, "verified") }
        h.store.startVerification("+4915112345678")
        assertEquals(Verification.Status.Verified, h.store.verification?.status)
        h.store.pollVerification()
        assertTrue(h.api.called("checkPhoneVerification").isEmpty())
    }

    @Test
    fun deletingRemovesTheNumberOnlyWhenTheBackendDid() = runTest(UnconfinedTestDispatcher()) {
        val h = harness { "deletePhoneNumber" throws APIError.Http(503, """{"detail":"Could not remove the phone number."}""") }
        assertFalse(h.store.deleteNumber("n1"))
        assertEquals(1, h.store.numbers.size)
        h.api.apply { "deletePhoneNumber" returns Unit }
        assertTrue(h.store.deleteNumber("n1"))
        assertTrue(h.store.numbers.isEmpty())
        assertEquals(listOf(listOf<Any?>("n1"), listOf<Any?>("n1")), h.api.called("deletePhoneNumber"))
    }

    @Test
    fun aPlanWithoutCallsIsUnavailable() = runTest(UnconfinedTestDispatcher()) {
        val h = harness { "verifiedPhoneNumbers" throws APIError.Http(403, """{"detail":"Phone calls require a paid subscription"}""") }
        assertEquals(PhoneCallErrorDetail.Message("Phone calls require a paid subscription"), h.store.unavailable)
        assertTrue(h.store.numbers.isEmpty())
    }

    @Test
    fun signingOutEndsTheCallAndForgetsTheNumbers() = runTest(UnconfinedTestDispatcher()) {
        val h = harness()
        h.store.call("+4930123456")
        h.store.clearUserData()
        assertEquals(1, h.engine.ended)
        assertEquals(Phase.Idle, h.store.phase)
        assertTrue(h.store.numbers.isEmpty())
        assertFalse(h.store.numbersLoaded)
    }

    // MARK: Number format

    @Test
    fun theKeypadAddsTheCallersCountryCode() {
        assertEquals("+15551234567", PhoneNumberFormat.dialable("(555) 123-4567", "+15551112222"))
        assertEquals("+49301234567", PhoneNumberFormat.dialable("030 1234.567", "+4915112345678"))
        assertEquals("+442079460958", PhoneNumberFormat.dialable("0044 20 7946 0958", "+4915112345678"))
        assertEquals("+442079460958", PhoneNumberFormat.dialable("+44 20 7946 0958", "+15551112222"))
        assertEquals("5551234", PhoneNumberFormat.dialable("5551234", null))
    }

    @Test
    fun callingCodesMatchLongestFirst() {
        assertEquals("1", PhoneNumberFormat.callingCode("+15551112222"))
        assertEquals("49", PhoneNumberFormat.callingCode("+4915112345678"))
        assertEquals("971", PhoneNumberFormat.callingCode("+971501234567"))
        assertEquals("353", PhoneNumberFormat.callingCode("+353861234567"))
        assertNull(PhoneNumberFormat.callingCode("4915112345678"))
    }

    @Test
    fun setupTurnsANationalNumberIntoE164() {
        assertEquals("+4915112345678", PhoneNumberFormat.e164("0151 1234 5678", "DE"))
        assertEquals("+15551234567", PhoneNumberFormat.e164("(555) 123-4567", "US"))
        assertEquals("+15551234567", PhoneNumberFormat.e164("1 555 123 4567", "US"))
        assertEquals("+390612345678", PhoneNumberFormat.e164("06 1234 5678", "IT"))
        assertEquals("+442079460958", PhoneNumberFormat.e164("+44 20 7946 0958", "DE"))
        assertEquals("+442079460958", PhoneNumberFormat.e164("0044 20 7946 0958", "DE"))
        assertNull(PhoneNumberFormat.e164("123", "DE"))
        assertNull(PhoneNumberFormat.e164("12ab45678", "DE"))
    }

    @Test
    fun numbersReadInGroups() {
        assertEquals("+1 555 123 4567", PhoneNumberFormat.display("+15551234567"))
        assertEquals("+49 151 123 456 78", PhoneNumberFormat.display("+4915112345678"))
        assertEquals("5551234", PhoneNumberFormat.display("5551234"))
    }
}

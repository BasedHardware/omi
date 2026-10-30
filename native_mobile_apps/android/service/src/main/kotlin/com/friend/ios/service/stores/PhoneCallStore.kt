package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.Conversation
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.PhoneCallErrorDetail
import com.friend.ios.network.endpoints.PhoneCallQuota
import com.friend.ios.network.endpoints.PhoneCallToken
import com.friend.ios.network.endpoints.VerifiedPhoneNumber
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.PhoneCallTranscriptChannel
import com.friend.ios.service.phonecalls.PhoneCallEngine
import com.friend.ios.service.phonecalls.PhoneCallEngineEvent
import com.friend.ios.service.phonecalls.PhoneCallFailure
import com.friend.ios.service.phonecalls.PhoneCallRequest
import com.friend.ios.service.phonecalls.PhoneCallStreams
import com.friend.ios.service.phonecalls.PhoneCallTranscript
import com.friend.ios.service.phonecalls.PhoneNumberFormat
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant
import kotlin.time.Duration
import kotlin.time.Duration.Companion.seconds

/**
 * Port of `PhoneCallStore.swift`. Phone calls through Omi (Flutter `PhoneCallProvider`): the verified
 * caller ID, verifying a number, past calls, and one call at a time with its live two-channel
 * transcript. A finished call becomes a conversation on the server (the transcription socket
 * carries `source=phone_call`).
 */
class PhoneCallStore(
    internal val api: APIClientProtocol,
    internal val engine: PhoneCallEngine,
    internal val userID: () -> String?,
    internal val language: () -> String = { "multi" },
    internal val scope: CoroutineScope,
    internal val timing: Timing = Timing(),
    internal val now: () -> Instant = Instant::now,
) {
    enum class Phase {
        Idle, Connecting, Ringing, Active,

        /** Shown for `Timing.endedLinger` ("Call Ended" or the failure), then back to idle. */
        Ended,
    }

    enum class TranscriptionStatus {
        Idle, Connecting, Active, Reconnecting, Failed,

        /** The socket is open but no call audio reached it yet. */
        NoAudio,
    }

    /** Delays, shortened in tests. */
    data class Timing(
        val verificationPoll: Duration = 2.seconds,
        val endedLinger: Duration = 2.seconds,
        val reconnectBase: Duration = 1.seconds,
        val noAudioTimeout: Duration = 3.seconds,
        /** The conversation is built after the socket closes; past calls reload after this. */
        val historyRefreshDelay: Duration = 5.seconds,
    )

    /** A number being verified (`PhoneCallStore+Numbers.swift`). */
    data class Verification(
        val phoneNumber: String,
        /** Typed on the keypad during Twilio's call; null: follow the voice on the call. */
        val code: String?,
        val status: Status,
    ) {
        enum class Status {
            Calling, InProgress,

            /** Fifteen polls (30 s) without a code; polling goes on until the timeout. */
            Missed,
            Verified,
            TimedOut,
        }
    }

    // MARK: Numbers, verification, history (PhoneCallStoreNumbers.kt)

    var numbers: List<VerifiedPhoneNumber> by mutableStateOf(emptyList())
        internal set
    var numbersLoaded by mutableStateOf(false)
        internal set

    /** The plan has no calls (403) or this month's free calls are used up (402). */
    var unavailable: PhoneCallErrorDetail? by mutableStateOf(null)
        internal set
    var quota: PhoneCallQuota? by mutableStateOf(null)
        internal set
    var history: List<Conversation> by mutableStateOf(emptyList())
        internal set
    var verification: Verification? by mutableStateOf(null)
        internal set
    var verificationFailure: PhoneCallFailure? by mutableStateOf(null)
        internal set
    var isStartingVerification by mutableStateOf(false)
        internal set

    // MARK: The call

    var phase by mutableStateOf(Phase.Idle)
        private set
    var remoteNumber: String? by mutableStateOf(null)
        private set
    var contactName: String? by mutableStateOf(null)
        private set
    var isMuted by mutableStateOf(false)
        private set
    var isSpeakerOn by mutableStateOf(false)
        private set

    /** When the other side picked up; the screen counts the duration from here. */
    var connectedAt: Instant? by mutableStateOf(null)
        private set
    var transcript by mutableStateOf(PhoneCallTranscript())
        internal set
    var transcription by mutableStateOf(TranscriptionStatus.Idle)
        internal set

    /** Why the last call did not start or ended early; cleared by the next attempt. */
    var failure: PhoneCallFailure? by mutableStateOf(null)
        internal set
    var callID: String? by mutableStateOf(null)
        private set

    /** The full-screen call view is up (false while minimized to the banner). */
    var showsCallScreen by mutableStateOf(false)

    /** After a call is over (conversation lists refresh). */
    var onCallFinished: (suspend () -> Unit)? = null

    // Transcription socket state (PhoneCallStoreTranscription.kt).
    internal var socket: PhoneCallTranscriptChannel? = null

    /** Frames that arrived while no socket was open (~2 s, as Flutter). */
    internal var pendingFrames = mutableListOf<ByteArray>()
    internal var framesSent = 0
    internal var socketAccepted = false
    internal var reconnectAttempts = 0
    internal var socketTask: Job? = null
    internal var reconnectTask: Job? = null
    internal var watchdogTask: Job? = null

    /** Bumped per call and on sign-out: late events of an earlier call are ignored. */
    internal var generation = 0
    private val engineTasks = mutableListOf<Job>()

    val isInProgress: Boolean
        get() = phase == Phase.Connecting || phase == Phase.Ringing || phase == Phase.Active

    /** Who the call is with: the picked contact, else the number. */
    val otherParty: String
        get() = contactName ?: remoteNumber?.let(PhoneNumberFormat::display) ?: ""

    // MARK: Calling

    /** Places a call to a typed or picked number. `false`: it did not start, [failure] says why. */
    suspend fun call(rawNumber: String, contactName: String? = null): Boolean {
        if (isInProgress) {
            failure = PhoneCallFailure.AlreadyInProgress
            return false
        }
        val caller = numbers.firstOrNull()?.phoneNumber
        if (caller == null) {
            failure = PhoneCallFailure.NoVerifiedNumber
            return false
        }
        resetCall()
        generation += 1
        val callGeneration = generation
        val number = PhoneNumberFormat.dialable(rawNumber, callerNumber = caller)
        val id = now().toEpochMilli().toString()
        phase = Phase.Connecting
        remoteNumber = number
        this.contactName = contactName
        callID = id

        if (!engine.requestMicrophonePermission()) return abort(PhoneCallFailure.MicrophonePermission, callGeneration)
        if (callGeneration != generation) return false
        val token: PhoneCallToken = try {
            api.phoneCallToken()
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            return abort(PhoneCallFailure.Server(detail(error)), callGeneration)
        }
        if (callGeneration != generation) return false
        return try {
            val streams = engine.start(PhoneCallRequest(token.accessToken, number, id, contactName))
            if (callGeneration != generation) {
                engine.end()
                return false
            }
            observe(streams, callGeneration)
            showsCallScreen = true
            true
        } catch (error: CancellationException) {
            throw error
        } catch (error: Exception) {
            abort(PhoneCallFailure.Engine(error.message ?: error.toString()), callGeneration)
        }
    }

    /** Hangs up; the conversation finishes on the server. */
    fun end() {
        if (!isInProgress) return
        engine.end()
        finish(null, generation)
    }

    /** Waits for the engine's confirmation (`Muted`), like Flutter. */
    fun toggleMute() {
        if (!isInProgress) return
        engine.setMuted(!isMuted)
    }

    fun toggleSpeaker() {
        if (!isInProgress) return
        engine.setSpeaker(!isSpeakerOn)
    }

    fun sendDigit(digit: String) {
        if (phase != Phase.Active) return
        engine.sendDigits(digit)
    }

    /** Sign-out: the call ends and nothing of this account stays. */
    fun clearUserData() {
        if (isInProgress) engine.end()
        generation += 1
        resetCall()
        phase = Phase.Idle
        numbers = emptyList()
        numbersLoaded = false
        unavailable = null
        quota = null
        history = emptyList()
        verification = null
        verificationFailure = null
    }

    /**
     * Debug builds only (`--es omiFakeCall active`, screenshots): shows a connected call with a
     * transcript without Twilio. iOS has no such launch argument; nothing is dialed.
     */
    fun debugPresent(number: String, contactName: String?, segments: List<LiveSegment>, translations: Map<String, List<String>> = emptyMap()) {
        generation += 1
        resetCall()
        remoteNumber = number
        this.contactName = contactName
        callID = now().toEpochMilli().toString()
        connectedAt = now()
        phase = Phase.Active
        transcription = TranscriptionStatus.Active
        transcript = PhoneCallTranscript().merge(segments).applyTranslations(translations)
        showsCallScreen = true
    }

    // MARK: Engine events

    private fun observe(streams: PhoneCallStreams, callGeneration: Int) {
        engineTasks += scope.launch {
            streams.events.collect { event -> handle(event, callGeneration) }
            // The engine stopped without saying why: the call is over.
            finish(null, callGeneration)
        }
        engineTasks += scope.launch {
            streams.audio.collect { frame ->
                if (callGeneration != generation) return@collect
                forward(frame)
            }
        }
    }

    internal fun handle(event: PhoneCallEngineEvent, callGeneration: Int) {
        if (callGeneration != generation || !isInProgress) return
        when (event) {
            PhoneCallEngineEvent.Ringing -> if (phase == Phase.Connecting) phase = Phase.Ringing
            PhoneCallEngineEvent.Connected -> {
                phase = Phase.Active
                if (connectedAt == null) {
                    connectedAt = now()
                    connectTranscription()
                }
            }
            PhoneCallEngineEvent.Ended -> finish(null, callGeneration)
            is PhoneCallEngineEvent.Failed -> finish(PhoneCallFailure.Engine(event.message), callGeneration)
            is PhoneCallEngineEvent.Muted -> isMuted = event.muted
            is PhoneCallEngineEvent.Speaker -> isSpeakerOn = event.on
        }
    }

    internal fun finish(reason: PhoneCallFailure?, callGeneration: Int) {
        if (callGeneration != generation || !isInProgress) return
        if (reason != null) failure = reason
        phase = Phase.Ended
        disconnectTranscription()
        transcription = TranscriptionStatus.Idle
        pendingFrames = mutableListOf()
        val timing = timing
        scope.launch {
            delay(timing.endedLinger)
            if (callGeneration != generation || phase != Phase.Ended) return@launch
            resetCall()
            phase = Phase.Idle
            onCallFinished?.invoke()
            delay(timing.historyRefreshDelay)
            loadHistory()
        }
    }

    private fun abort(reason: PhoneCallFailure, callGeneration: Int): Boolean {
        if (callGeneration != generation) return false
        resetCall()
        phase = Phase.Idle
        failure = reason
        return false
    }

    private fun resetCall() {
        // Not the running coroutine: a reset from inside an engine task must not cancel itself mid-way.
        engineTasks.forEach { it.cancel() }
        engineTasks.clear()
        disconnectTranscription()
        remoteNumber = null
        contactName = null
        callID = null
        connectedAt = null
        isMuted = false
        isSpeakerOn = false
        transcript = PhoneCallTranscript()
        transcription = TranscriptionStatus.Idle
        failure = null
        pendingFrames = mutableListOf()
        framesSent = 0
        socketAccepted = false
        showsCallScreen = false
    }

    companion object {
        /** The number Twilio's verification call comes from (Flutter shows the same). */
        const val VERIFICATION_CALLER_ID = "+1 (415) 723-4000"
        internal const val MAX_PENDING_FRAMES = 100
        internal const val MAX_RECONNECT_ATTEMPTS = 10

        internal fun detail(error: Throwable): PhoneCallErrorDetail? =
            (error as? APIError.Http)?.let { PhoneCallErrorDetail.from(it.body) }
    }
}

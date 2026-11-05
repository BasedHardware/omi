package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.audio.AudioSessionMonitoring
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.CaptureFailure
import com.friend.ios.service.DeviceTranscriptionEngine
import com.friend.ios.service.PhoneCaptureEngine
import com.friend.ios.service.PhoneCaptureStreams
import com.friend.ios.service.TranscriptionLanguage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.launch

/**
 * Port of `CaptureStore.swift` (and its `+Lifecycle`, `+Recovery`, `+Transcription` files).
 * Live capture: phone microphone, the Omi wearable or the watch -> `/v4/listen` -> live transcript
 * -> a finalized conversation. Mirrors the Flutter `capture_provider.dart` contract.
 *
 * Swift's `Task`s become jobs in [scope] (the main thread, like `@MainActor`); `Date`s are
 * epoch milliseconds from [clock].
 */
class CaptureStore(
    internal val api: APIClientProtocol,
    internal val engine: PhoneCaptureEngine,
    private val deviceEngine: DeviceTranscriptionEngine,
    internal val preferences: Preferences,
    private val defaultOnDevice: Boolean,
    internal val userID: () -> String?,
    internal val scope: CoroutineScope,
    internal val clock: () -> Long = System::currentTimeMillis,
    /** How often the health probe asks for the microphone back (iOS `healthTick`). */
    internal val healthTickMillis: Long = 3_000,
    /** The session signals the OS gives (`CaptureStoreInterruption.kt`; tests pass a fake). */
    internal val audioSession: AudioSessionMonitoring? = null,
) {
    enum class Source { Phone, Device, Watch }

    sealed interface Phase {
        data object Idle : Phase
        data object Starting : Phase
        data class Live(val sinceMillis: Long) : Phase
        data object Finishing : Phase
        data class Failed(val reason: String) : Phase
    }

    var phase: Phase by mutableStateOf(Phase.Idle)
        internal set
    var source: Source? by mutableStateOf(null)
        private set
    var segments: List<LiveSegment> by mutableStateOf(emptyList())
        internal set
    /** The on-device recognizer's current partial line (not yet final). */
    var partial: LiveSegment? by mutableStateOf(null)
        internal set
    /** The phone's recognizer only previews words; the server's segments are the transcript. */
    internal var previewOnly by mutableStateOf(false)
    /**
     * The phone's whole current line in preview mode; `partial` shows only what the server's
     * segments do not show yet.
     */
    internal var preview: LiveSegment? by mutableStateOf(null)
    /** When the phone's preview line last changed (it goes stale if recognition stops). */
    internal var previewUpdatedAt: Long? = null
    /** When this recording started, for the "first live words" line in the transcription log. */
    internal var startedAt: Long? = null
    var level: Float by mutableStateOf(0f)
        internal set
    var serverStatus: String? by mutableStateOf(null)
        private set
    var lastConversationID: String? by mutableStateOf(null)
        internal set
    /** The conversation being recorded (`conversation_session`), for naming voices live. */
    var liveConversationID: String? by mutableStateOf(null)
        private set
    /** Audio is held back while the conversation stays open (Flutter pause; for the Omi, its mute). */
    var isPaused: Boolean by mutableStateOf(false)
        internal set
    /** The live conversation gets a star when it ends (double tap set to star). */
    var starsConversation: Boolean by mutableStateOf(false)
        private set
    /**
     * Phone audio goes to a file on the phone instead of the socket: the connection dropped
     * (uploaded when the recording stops) or Transcribe later is on (uploaded when asked).
     */
    var isBuffering: Boolean by mutableStateOf(false)
        internal set
    /** A recording ended unexpectedly (Home shows it; `CaptureStoreRecovery.kt`). */
    var recovery: CaptureRecovery? by mutableStateOf(null)
        internal set
    /** Where buffered phone audio goes (the app: `SyncStorePhoneAudio` over `SyncStore`). */
    var phoneBuffer: PhoneAudioBuffering? = null
    /** The user's own speech-to-text provider (Settings > Listening > Advanced transcription). */
    var customSTT: com.friend.ios.service.customstt.CustomSTTSettings? = null
    var makeCustomTranscriber: ((com.friend.ios.network.customstt.CustomSTTConfig) -> com.friend.ios.service.customstt.CustomTranscribing)? = null
    internal var customTranscriber: com.friend.ios.service.customstt.CustomTranscribing? = null
    /** The phone's Opus decoder (the app's platform one), so the user's own provider hears the Omi. */
    var makeOpusDecoder: com.friend.ios.service.OpusDecoderFactory? = null
    /** The Omi's opus as PCM for the user's own provider, while one transcribes an Omi recording. */
    internal var opusToPCM: com.friend.ios.service.OpusPCM16Decoding? = null
    /** Transcription and capture events (Settings > Developer, the transcription log). */
    var log: ((level: LogLevel, tag: String, message: String) -> Unit)? = null
    /** Who transcribes the live recording (`CaptureStoreTranscription.kt`). */
    var transcriber: Transcriber by mutableStateOf(Transcriber.Omi)
        internal set
    /** The plan's minutes ran low or out (Flutter `freemium_threshold_reached`); null otherwise. */
    var transcriptionNotice: TranscriptionNotice? by mutableStateOf(null)
        internal set
    /** Store audio on phone is writing a copy of this recording. */
    internal var keepsCopy = false
    /** The options of the open socket (a switch to the phone's transcription reopens with them). */
    internal var listenOptionsInUse: ListenSocket.Options? = null
    /**
     * Omi audio that arrived while no socket was open (starting, finishing, reconnecting): it is
     * sent first once a socket opens (`CaptureStoreLifecycle.kt`).
     */
    internal var heldDeviceAudio = ArrayDeque<ByteArray>()
    internal var heldDeviceAudioBytes = 0
    /** The Omi's socket dropped and is being reopened with the same recording id. */
    internal var reconnectingDevice = false
    /** Waits before each attempt to reopen it (ms); the last one repeats until it opens. */
    internal var deviceReconnectDelays = listOf(1_000L, 2_000L, 5_000L, 10_000L, 30_000L)
    /** The phone's socket dropped and is being reopened with the same recording id. */
    internal var reconnectingPhone = false
    /** Waits before each attempt to reopen it (ms); the last one repeats until it opens. */
    internal var phoneReconnectDelays = listOf(1_000L, 2_000L, 5_000L, 10_000L, 30_000L)
    /**
     * The streams of the live phone engine. Kept across a suspension, so a take-back can carry on
     * with the same ones when the capture never stopped (`CaptureStoreInterruption.kt`).
     */
    internal var phoneStreams: PhoneCaptureStreams? = null
    /** The system has the microphone: the recording stays alive and the health loop keeps asking. */
    internal var suspendedBySystem = false
    /** A take-back is between "stop" and "running again": only one may be in flight at a time. */
    internal var takingMicrophoneBack = false
    /** The probe that takes the microphone back, every [healthTickMillis], while the phone records. */
    internal var healthJob: Job? = null
    /**
     * Why the phone capture is not running, when the reason came from outside the app (Home shows
     * it; `CaptureStoreInterruption.kt`).
     */
    var notice: CaptureNotice? by mutableStateOf(null)
        internal set

    enum class LogLevel { Info, Warning }

    internal fun log(level: LogLevel, tag: String, message: String) {
        log?.invoke(level, tag, message)
    }

    private var transcribesLaterState by mutableStateOf(preferences.bool(Key.BatchModeEnabled, false))
    private var usesParakeetState by mutableStateOf(preferences.string(Key.TranscriptionModel) == "parakeet")
    private var deviceMutedState by mutableStateOf(preferences.bool(NativeKey.DeviceMuted, false))
    private var conversationTimeoutState by mutableStateOf(preferences.integer(Key.ConversationSilenceDuration, 120))

    /** Record now, transcribe later: the phone writes a file instead of streaming (Flutter batch mode). */
    var transcribesLater: Boolean
        get() = transcribesLaterState
        set(value) {
            transcribesLaterState = value
            preferences.set(Key.BatchModeEnabled, value)
        }

    /** The server's speech model: `parakeet` (Omi Parakeet) or the backend's choice. */
    var usesParakeet: Boolean
        get() = usesParakeetState
        set(value) {
            usesParakeetState = value
            preferences.set(Key.TranscriptionModel, if (value) "parakeet" else "soniox")
        }

    /** The Omi stays muted across conversations and launches until unmuted. */
    var isDeviceMuted: Boolean
        get() = deviceMutedState
        set(value) {
            if (value == deviceMutedState) return
            deviceMutedState = value
            preferences.set(NativeKey.DeviceMuted, value)
            if (source == Source.Device && isLive) isPaused = value
        }

    /**
     * Seconds of silence that end a conversation (`conversation_timeout`; -1 is four hours).
     * Applies from the next conversation.
     */
    var conversationTimeout: Int
        get() = conversationTimeoutState
        set(value) {
            conversationTimeoutState = value
            preferences.set(Key.ConversationSilenceDuration, value)
        }

    private var onDeviceState by mutableStateOf(preferences.bool(NativeKey.OnDeviceTranscription, defaultOnDevice))

    /** Settings > Listening > Advanced: the phone's own recognizer transcribes instead of Omi's servers. */
    var transcribesOnDevice: Boolean
        get() = onDeviceState
        set(value) {
            onDeviceState = value
            preferences.set(NativeKey.OnDeviceTranscription, value)
        }

    /**
     * Android: the phone has an on-device recognizer that capture can feed (Android 13+ with an
     * offline model). iOS always has one; Settings disables the switch without it.
     */
    val canTranscribeOnDevice: Boolean
        get() = engine.supportsOnDevice

    /** Called after a conversation was finalized (refresh lists). */
    var onConversationFinished: (suspend () -> Unit)? = null
    /** A watch recording ended here (Stop in the app, or the watch's own stop): `WatchStore`. */
    var onWatchCaptureEnded: (() -> Unit)? = null
    /**
     * Where the recording starts (`LocationStore`), as the listen header's JSON; null without
     * location access.
     */
    var recordingLocation: (suspend () -> String?)? = null

    private var deviceFeed: ((ByteArray) -> Unit)? = null
    /** The wearable's codec while it streams, to start the next conversation after a double tap. */
    private var deviceCodec: Pair<ListenSocket.Options.Codec, Int>? = null
    internal var channel: LiveTranscriptionChannel? = null
    /** A socket was opened for this recording (its conversation is finalized at the end). */
    private var streamedToServer = false
    internal val tasks = mutableListOf<Job>()
    /** The phone microphone's streams: cancelled on pause, started again on resume. */
    internal val phoneTasks = mutableListOf<Job>()

    init {
        recovery = recoveredInterruption(preferences)
    }

    val isLive: Boolean
        get() = phase is Phase.Live || phase == Phase.Starting

    /**
     * Swift's `Task { await capture.stop() }` from a view: runs on the store's scope, so it outlives
     * the view that asked (the live bar and sheet leave composition when the recording ends).
     */
    fun perform(action: suspend CaptureStore.() -> Unit): Job = scope.launch { action() }

    val transcriptText: String
        get() = (segments + listOfNotNull(partial)).joinToString(" ") { it.text }

    /**
     * The newest words for one-line live displays (Home's live bar, the Omi card). With server
     * transcription the phone's own line is the freshest while it keeps updating; the server's
     * segments take over when the phone falls silent.
     */
    val liveWords: String
        get() {
            val preview = preview
            val updated = previewUpdatedAt
            if (previewOnly && preview != null && updated != null && clock() - updated < 3_000) return preview.text
            return transcriptText
        }

    // MARK: Phone

    suspend fun startPhone() {
        if (isLive) return
        val uid = userID() ?: return
        reset(Source.Phone)
        finalizeLeftoverConversation()
        if (phase != Phase.Starting || source != Source.Phone) return
        var plan = transcriptionPlan(laterRequested = transcribesLater && phoneBuffer != null, opus = true)
        val later = plan == Plan.Later
        val locate = if (later) null else recordingLocation
        val place = scope.async { locate?.invoke() }
        val streams: PhoneCaptureStreams
        try {
            val started = startPhoneStreams(plan)
            streams = started.first
            plan = started.second
        } catch (error: Exception) {
            place.cancel()
            engine.stop()
            phase = Phase.Failed(describe(error))
            return
        }
        if (later) {
            // Nothing is streamed: the file waits in Capture & Transcription until the user processes it.
            beginBuffering(manual = true)
            setLive()
            pipe(streams)
            return
        }
        try {
            val options = listenOptions(
                ListenSocket.Options(
                    codec = ListenSocket.Options.Codec.Pcm16, source = ListenSocket.Options.Source.Phone, language = language,
                    conversationTimeout = conversationTimeout, clientTranscription = plan != Plan.Omi,
                ),
            )
            options.geolocationHeader = place.await()
            val channel = api.openListenSocket(uid, options)
            this.channel = channel
            listenOptionsInUse = options
            streamedToServer = true
            setLive()
            beginTranscriber(plan)
            beginKeptCopy(KeptAudioSource.Phone)
            listen(channel, acceptServerSegments = plan == Plan.Omi)
            pipe(streams)
        } catch (error: Exception) {
            if (phoneBuffer != null) {
                // No connection: record on the phone and upload when the recording ends.
                log(LogLevel.Warning, "stt", "listen socket failed: $error")
                beginBuffering(manual = false)
                setLive()
                beginKeptCopy(KeptAudioSource.Phone)
                pipe(streams)
            } else {
                engine.stop()
                phase = Phase.Failed(describe(error))
            }
        }
    }

    // MARK: Device

    /**
     * Starts streaming the wearable's audio (called when the device reports its codec).
     * [codec] and [sampleRate]: the Omi's `OmiGATT.Codec` as the listen socket names it.
     */
    suspend fun startDevice(codec: ListenSocket.Options.Codec, sampleRate: Int = 16000) {
        if (isLive) return
        val uid = userID() ?: return
        reset(Source.Device)
        isPaused = isDeviceMuted
        deviceCodec = codec to sampleRate
        // Audio arriving meanwhile is held (`ingestDeviceAudio`) and sent once the socket is open.
        finalizeLeftoverConversation()
        if (phase != Phase.Starting || source != Source.Device) return
        // The phone's recognizer and custom providers need opus (all current Omi firmware); pcm
        // devices use the server.
        val opus = codec == ListenSocket.Options.Codec.OpusFS320 || codec == ListenSocket.Options.Codec.Opus
        var plan = transcriptionPlan(laterRequested = false, opus = opus)
        if (plan is Plan.Custom) {
            // The user's own provider takes PCM: the Omi's opus goes through the phone's decoder.
            opusToPCM = makeOpusDecoder?.invoke { pcm -> customTranscriber?.feed(pcm) }
            if (opusToPCM == null) plan = Plan.Omi
        }
        val onDevice = plan == Plan.Phone
        try {
            // Server transcription: the same recognizer as a live preview, when speech is allowed.
            val preview = plan == Plan.Omi && opus
            // The plan's own switch to the phone is best effort (speech permission); the user's is required.
            val transcription = if (onDevice || preview) startDevicePreview(required = onDevice && transcribesOnDevice) else null
            if (onDevice && transcription == null) {
                plan = Plan.Omi
                transcriptionNotice = TranscriptionNotice.MinutesRunningLow(0)
            }
            if (transcription != null) {
                previewOnly = preview
                deviceFeed = transcription.feed
                tasks += scope.launch { transcription.transcript.collect { applyOnDevice(it.segment, it.isFinal) } }
            }
            val options = listenOptions(
                ListenSocket.Options(
                    codec = codec, sampleRate = sampleRate, source = ListenSocket.Options.Source.Omi, language = language,
                    conversationTimeout = conversationTimeout, clientTranscription = plan != Plan.Omi,
                ),
            )
            options.geolocationHeader = recordingLocation?.invoke()
            val channel = api.openListenSocket(uid, options)
            this.channel = channel
            listenOptionsInUse = options
            streamedToServer = true
            setLive()
            beginTranscriber(plan)
            beginKeptCopy(KeptAudioSource.Device(codec))
            listen(channel, acceptServerSegments = plan == Plan.Omi)
            sendHeldDeviceAudio()
        } catch (error: Exception) {
            deviceEngine.stop()
            deviceFeed = null
            opusToPCM?.release()
            opusToPCM = null
            discardHeldDeviceAudio()
            phase = Phase.Failed(describe(error))
        }
    }

    private suspend fun startDevicePreview(required: Boolean): com.friend.ios.service.DeviceTranscription? {
        if (required) return deviceEngine.start()
        return try {
            deviceEngine.start()
        } catch (error: Exception) {
            // Words then only come from the server, seconds later: worth a line in the log.
            log(LogLevel.Warning, "stt", "live preview unavailable: ${describe(error)}")
            null
        }
    }

    /** One codec frame from the wearable. */
    fun ingestDeviceAudio(frame: ByteArray) {
        if (source != Source.Device || isPaused) return
        val channel = channel
        if (channel == null) {
            holdDeviceAudio(frame)
            return
        }
        channel.send(frame)
        deviceFeed?.invoke(frame)
        if (customTranscriber != null) opusToPCM?.decode(frame)
        if (keepsCopy) phoneBuffer?.appendKeptCopy(frame)
    }

    // MARK: Internals

    private val language: String
        get() = TranscriptionLanguage.current(preferences)

    private fun reset(source: Source) {
        this.source = source
        previewOnly = false
        transcriber = Transcriber.Omi
        transcriptionNotice = null
        preview = null
        previewUpdatedAt = null
        startedAt = clock()
        segments = emptyList()
        partial = null
        serverStatus = null
        isPaused = false
        notice = null
        suspendedBySystem = false
        takingMicrophoneBack = false
        reconnectingPhone = false
        liveConversationID = null
        phase = Phase.Starting
    }

    internal fun listen(channel: LiveTranscriptionChannel, acceptServerSegments: Boolean) {
        tasks += scope.launch {
            channel.events.collect { handle(it, acceptServerSegments) }
        }
    }

    // MARK: Stop

    /** Stops capture and finalizes the conversation (`POST v1/conversations`). */
    suspend fun stop() {
        if (!finish()) return
        discardHeldDeviceAudio()
        onConversationFinished?.invoke()
    }

    /**
     * Double tap on the Omi: finalize this conversation and keep listening in a new one. The
     * device stays connected, so no new codec (and no `onReady`) arrives to restart capture.
     */
    suspend fun endDeviceConversation() {
        if (source != Source.Device || !isLive || deviceCodec == null) return
        if (!finish()) return
        // Unless the Omi disconnected while finalizing; its next connect restarts capture.
        deviceCodec?.let { (codec, rate) -> startDevice(codec, rate) }
        onConversationFinished?.invoke()
    }

    /** Ends the live session and finalizes its conversation; false when nothing was live. */
    private suspend fun finish(): Boolean {
        if (!isLive) return false
        phase = Phase.Finishing
        // The microphone is ours to give back now: no probe may take it after this.
        stopCaptureHealth()
        if (source == Source.Phone) engine.stop()
        if (source == Source.Watch) onWatchCaptureEnded?.invoke()
        if (source == Source.Device) {
            deviceEngine.stop()
            deviceFeed = null
        }
        partial?.let { flushFinal(it) }
        endTranscriber()
        endKeptCopy()
        channel?.close("user_stop")
        channel = null
        reconnectingDevice = false
        reconnectingPhone = false
        phoneStreams = null
        cancelJobs(tasks)
        cancelJobs(phoneTasks)
        level = 0f
        isPaused = false
        endBuffering()
        markEnded()
        // A phone recording that never reached the server has no conversation to finalize.
        val finalizes = source != Source.Phone || streamedToServer
        val id = if (finalizes) finalizeOpenConversation() else null
        streamedToServer = false
        lastConversationID = id ?: lastConversationID
        applyStar(id)
        phase = Phase.Idle
        return true
    }

    /**
     * The wearable disconnected: keep what was said. The backend does not finalize an Omi
     * conversation when its socket closes, so it stays remembered and is finalized when capture
     * starts again (`finalizeLeftoverConversation`).
     */
    fun deviceDisconnected() {
        if (source != Source.Device) return
        deviceCodec = null
        discardHeldDeviceAudio()
        reconnectingDevice = false
        if (!isLive) return
        endTranscriber()
        endKeptCopy()
        channel?.close("device_disconnected")
        channel = null
        deviceEngine.stop()
        deviceFeed = null
        isPaused = false
        markEnded()
        streamedToServer = false
        phase = Phase.Idle
    }

    internal fun cancelJobs(jobs: MutableList<Job>) {
        val running = jobs.toList()
        jobs.clear()
        running.forEach { it.cancel() }
    }

    // MARK: Server events

    internal fun handle(event: ListenEvent, acceptServerSegments: Boolean) {
        when (event) {
            is ListenEvent.Segments -> if (acceptServerSegments) {
                event.segments.forEach(::upsert)
                if (previewOnly && event.segments.isNotEmpty()) partial = preview?.let(::previewTail)
            }
            is ListenEvent.Status -> {
                val status = event.status
                serverStatus = status
                val failed = status.startsWith("stt_failed") || status.startsWith("disconnected")
                log(if (failed) LogLevel.Warning else LogLevel.Info, "stt", status)
                if (status.startsWith("disconnected") && source == Source.Device) {
                    // The Omi still streams: reopen the socket, resuming the same conversation.
                    deviceSocketLost()
                    return
                }
                if (status.startsWith("disconnected") && isLive && source == Source.Phone && !isBuffering && phoneBuffer != null) {
                    // Keep recording and take the socket back: the gap goes to the phone's file.
                    phoneSocketLost()
                    return
                }
                if (failed && isLive && source == Source.Phone && transcriber == Transcriber.Omi) {
                    fail(status)
                }
            }
            is ListenEvent.ConversationStarted -> {
                liveConversationID = event.id
                rememberOpenConversation(event.id)
            }
            is ListenEvent.ProcessingStarted -> forgetOpenConversation(event.conversationID)
            is ListenEvent.ConversationCreated -> {
                forgetOpenConversation(event.id)
                lastConversationID = event.id
                liveConversationID = null
                segments = emptyList()
                scope.launch {
                    applyStar(event.id)
                    onConversationFinished?.invoke()
                }
            }
            is ListenEvent.SegmentsDeleted -> segments = segments.filterNot { it.id in event.ids }
            is ListenEvent.Translated -> applyTranslations(event.segments)
            is ListenEvent.FreemiumThreshold ->
                scope.launch { freemiumThresholdReached(event.remainingSeconds, event.requiresOnDevice) }
            is ListenEvent.Other -> {}
        }
    }

    // MARK: The phone engine and on-device words

    /**
     * With server transcription the phone's recognizer still runs as a live preview (words appear
     * as they are spoken; the server's segments replace them). Without speech permission the
     * recording simply runs without the preview.
     */
    internal suspend fun startPhoneEngine(onDevice: Boolean, preview: Boolean): PhoneCaptureStreams {
        if (!preview) return engine.start(transcribeOnDevice = onDevice)
        val streams = try {
            engine.start(transcribeOnDevice = true)
        } catch (error: Exception) {
            null
        }
        if (streams != null) {
            previewOnly = streams.transcript != null
            return streams
        }
        engine.stop()
        return engine.start(transcribeOnDevice = false)
    }

    internal fun pipe(streams: PhoneCaptureStreams) {
        phoneStreams = streams
        phoneTasks += scope.launch { streams.pcm16.collect { routePhoneAudio(it) } }
        phoneTasks += scope.launch { streams.level.collect { level = it } }
        streams.transcript?.let { transcript ->
            phoneTasks += scope.launch { transcript.collect { applyOnDevice(it.segment, it.isFinal) } }
        }
    }

    internal fun applyOnDevice(segment: LiveSegment, isFinal: Boolean) {
        val startedAt = startedAt
        if (startedAt != null && preview == null && partial == null && segments.isEmpty()) {
            log(LogLevel.Info, "stt", "first live words after ${clock() - startedAt} ms")
        }
        // Server transcription: the phone's words only show until the server's segment arrives.
        if (previewOnly) {
            preview = segment
            previewUpdatedAt = clock()
            partial = previewTail(segment)
            return
        }
        if (isFinal) flushFinal(segment) else partial = segment
    }

    /**
     * The words of the phone's line the server has not sent yet. The recognizer repeats its
     * whole line (up to ~50 s) with every update; without this the words the server already
     * shows would appear twice. Both clocks start with the recording.
     */
    internal fun previewTail(line: LiveSegment): LiveSegment? {
        val served = segments.filter { it.end > line.start + 0.3 }.sumOf { words(it.text).size }
        val words = words(line.text)
        if (served >= words.size) return null
        return line.copy(text = words.drop(served).joinToString(" "), translations = emptyList(), personID = null)
    }

    private fun words(text: String): List<String> = text.split(Regex("\\s+")).filter { it.isNotEmpty() }

    internal fun flushFinal(segment: LiveSegment) {
        partial = null
        upsert(segment)
        channel?.sendSuggestedTranscript(listOf(segment), provider = "apple_on_device")
    }

    internal fun upsert(segment: LiveSegment) {
        val index = segments.indexOfFirst { it.id == segment.id }
        segments = if (index >= 0) segments.toMutableList().also { it[index] = segment } else segments + segment
    }

    companion object {
        fun describe(error: Throwable): String = when (error) {
            CaptureFailure.MicrophonePermission -> "microphone"
            CaptureFailure.SpeechPermission -> "speech"
            CaptureFailure.SpeechUnavailable -> "speechUnavailable"
            else -> error.toString()
        }

        /** The choices Flutter offers: 2, 5, 10, 30 minutes and four hours. */
        val conversationTimeouts = listOf(120, 300, 600, 1800, -1)

        /** 100 ms of PCM16 per socket message, the phone mic's pacing, instead of one 1.5 s burst. */
        internal const val watchFrameBytes = 3200
    }

    // MARK: Watch

    /**
     * Starts a conversation from the watch microphone (16 kHz PCM16 relayed by `WatchStore`).
     * The server transcribes. On Android the watch is a Wear OS watch (`:wear`, the Data Layer).
     */
    suspend fun startWatch() {
        if (isLive) return
        val uid = userID() ?: return
        reset(Source.Watch)
        finalizeLeftoverConversation()
        if (phase != Phase.Starting || source != Source.Watch) return
        try {
            val options = listenOptions(
                ListenSocket.Options(codec = ListenSocket.Options.Codec.Pcm16, source = ListenSocket.Options.Source.AppleWatch, language = language),
            )
            options.geolocationHeader = recordingLocation?.invoke()
            val channel = api.openListenSocket(uid, options)
            this.channel = channel
            streamedToServer = true
            setLive()
            listen(channel, acceptServerSegments = true)
        } catch (error: Exception) {
            phase = Phase.Failed(describe(error))
        }
    }

    /** One chunk of watch audio; dropped unless a watch recording is live. */
    fun ingestWatchAudio(pcm: ByteArray) {
        if (source != Source.Watch || phase !is Phase.Live) return
        val channel = channel ?: return
        var offset = 0
        while (offset < pcm.size) {
            val end = minOf(offset + watchFrameBytes, pcm.size)
            channel.send(pcm.copyOfRange(offset, end))
            offset = end
        }
    }

    // MARK: Pause

    /**
     * Stops sending audio but keeps the conversation open (Flutter `phonePaused` / `pendantPaused`):
     * the phone releases its microphone; the Omi keeps streaming and its frames are dropped. For
     * the Omi this is its mute, which outlasts the conversation.
     */
    fun pause() {
        if (phase !is Phase.Live || isPaused) return
        isPaused = true
        if (source == Source.Device) isDeviceMuted = true
        if (source != Source.Phone) return
        // The user chose this: no banner, and the health loop stops asking for the microphone.
        notice = null
        suspendedBySystem = false
        engine.stop()
        phoneStreams = null
        cancelJobs(phoneTasks)
        level = 0f
        partial?.let { flushFinal(it) }
    }

    suspend fun resume() {
        if (phase !is Phase.Live || !isPaused) return
        isPaused = false
        if (source == Source.Device) isDeviceMuted = false
        if (source != Source.Phone || (channel == null && !isBuffering)) return
        // The user asks for the microphone back; the health loop's probe answers, so a refusal
        // (something else still has it) leaves the recording alive with the reason on screen
        // instead of ending a conversation whose words are already sent or on disk.
        suspendedBySystem = false
        notice = null
        takeMicrophoneBack()
    }

    // MARK: Star

    /** Double tap set to star: marks the live conversation (or takes the mark back). */
    fun toggleStar() {
        if (!isLive) return
        starsConversation = !starsConversation
    }

    /** A voice named in the live transcript (`LiveSpeakersStore`), after its REST assignment. */
    fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) {
        channel?.sendSpeakerAssigned(speakerID, personID, personName, segmentIDs)
    }

    private suspend fun applyStar(id: String?) {
        if (!starsConversation || id == null) return
        starsConversation = false
        runCatching { api.setConversationStarred(id, true) }
    }
}

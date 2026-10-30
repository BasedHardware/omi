package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.device.OmiGATT
import com.friend.ios.network.endpoints.VoiceMessageFile
import com.friend.ios.service.voice.LiveRecognizer
import com.friend.ios.service.voice.LiveSegment
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.time.Instant
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds

/**
 * Port of `AskOmiStore.swift`. Ask Omi from the wearable: a single press starts a question from
 * the Omi's audio, the next press, a pause after the words (or 15 s) ends it. The phone
 * transcribes the question while it is spoken (in the user's main language), so the words show at
 * once, and asks it like a typed question; where the phone cannot recognize the language the
 * recording goes to `v2/voice-message/transcribe` instead. The answer lands in the chat and is read
 * aloud when Settings > Assistant > Spoken replies allows it. Every wait ends: nothing heard and
 * no answer both come back as a `problem`. Older firmware holds the button instead. Mirrors
 * `capture_controller.dart` voice-command sessions.
 *
 * @param codec the Omi's codec while connected.
 * @param haptic a pulse on the Omi (recording started, answer arriving, nothing heard).
 * @param canAsk false while the Omi is muted or button actions are off.
 * @param voice reads answers aloud (as the reply mode allows); null keeps them silent.
 * @param recognizer transcribes the question on the phone; null sends the recording instead.
 * @param language the language the recognizer listens for (the user's main one).
 * @param makeDecoder the Omi's frames as 16 kHz PCM16 for the recognizer; null for a codec it cannot use.
 * @param sharedLine the line of a recognizer that already listens to the Omi (the capture's live
 *   words); null when none runs.
 * @param pauseToSend quiet after the last words that ends a pressed question by itself.
 * @param answerTimeout how long an answer may take before the question counts as unanswered.
 * @param now a monotonic clock in milliseconds (tests pass the virtual one).
 */
class AskOmiStore(
    private val chat: ChatStore,
    internal val scope: CoroutineScope,
    private val voice: VoicePlaybackStore? = null,
    private val codec: () -> OmiGATT.Codec?,
    private val haptic: (OmiGATT.Haptic) -> Unit,
    private val canAsk: () -> Boolean,
    private val recognizer: LiveRecognizer? = null,
    private val language: () -> String = { "en" },
    private val makeDecoder: (OmiGATT.Codec) -> ((ByteArray) -> ByteArray?)? = ::pcmDecoder,
    internal val sharedLine: () -> SharedLine? = { null },
    private val maxDuration: Duration = 15.seconds,
    private val autoSendGrace: Duration = 2.seconds,
    private val pauseToSend: Duration = 2.seconds,
    private val answerTimeout: Duration = 30.seconds,
    internal val now: () -> Long = { System.nanoTime() / 1_000_000 },
) : AskOmi {
    internal enum class Trigger { Toggle, Hold }

    /**
     * Where the question's words come from. [Shared]: the capture's recognizer already hears the
     * Omi; its line is read instead.
     */
    internal enum class Recognition { Off, Starting, Running, Shared, Unavailable }

    override var phase: AskOmi.Phase by mutableStateOf(AskOmi.Phase.Idle)
        private set
    override var lastExchange: AskOmi.Exchange? by mutableStateOf(null)
        private set
    /** The question's words so far, live while it is spoken (empty without the phone's recognizer). */
    override var question: String by mutableStateOf("")
        internal set
    override var problem: AskOmi.Problem? by mutableStateOf(null)
        private set
    /**
     * An answer that is not being read aloud (the app shows it as a notification, like Flutter,
     * which skips the answer push while it speaks).
     */
    var onAnswer: ((String) -> Unit)? = null
    /** The onboarding lesson: questions go through even with button actions turned off. */
    override var isPractice: Boolean = false

    private val frames = mutableListOf<ByteArray>()
    private var trigger: Trigger? = null
    private var timeoutJob: Job? = null
    private var pauseJob: Job? = null
    internal var wordsJob: Job? = null
    private var autoSentAt: Long? = null
    internal var lastWordsAt: Long? = null
    private var decode: ((ByteArray) -> ByteArray?)? = null
    internal var recognition = Recognition.Off
    private val pendingAudio = mutableListOf<ByteArray>()
    internal val segments = mutableListOf<LiveSegment>()
    /** Bumped per question: words from an earlier one are dropped. */
    internal var session = 0
    internal var sendJob: Job? = null
        private set

    val isListening: Boolean get() = phase is AskOmi.Phase.Listening

    override fun handle(action: ButtonAction) {
        when (action) {
            ButtonAction.AskToggle -> {
                val sentAt = autoSentAt
                if (isListening) {
                    send()
                } else if (sentAt != null && (now() - sentAt).milliseconds < autoSendGrace) {
                    // The press meant to stop a question that just sent itself.
                    autoSentAt = null
                } else {
                    start(Trigger.Toggle)
                }
            }
            ButtonAction.AskHoldStart -> if (!isListening) start(Trigger.Hold)
            ButtonAction.AskHoldEnd -> if (isListening && trigger == Trigger.Hold) send()
            ButtonAction.EndConversation, ButtonAction.ToggleStar, ButtonAction.ToggleMute -> Unit
        }
    }

    /** One codec frame from the Omi (header removed); kept only while a question is recorded. */
    fun ingest(frame: ByteArray) {
        if (!isListening) return
        frames += frame
        decode?.invoke(frame)?.let(::hear)
    }

    /** 16 kHz PCM16 for the recognizer only (the debug stand-in for the Omi's audio). */
    fun ingestPCM16(pcm16: ByteArray) {
        if (!isListening) return
        hear(pcm16)
    }

    /** Drops a question being recorded (button actions turned off, Omi disconnected). */
    fun cancel() {
        if (!isListening) return
        timeoutJob?.cancel()
        pauseJob?.cancel()
        stopRecognizing()
        wordsJob?.cancel()
        frames.clear()
        trigger = null
        phase = AskOmi.Phase.Idle
    }

    private val allowed: Boolean get() = isPractice || canAsk()

    private fun start(trigger: Trigger) {
        if (phase != AskOmi.Phase.Idle) return
        val codec = codec() ?: return
        if (!allowed) return
        // A new question cuts off the answer still being read (Flutter `newVoiceQuery`).
        voice?.stop()
        autoSentAt = null
        frames.clear()
        question = ""
        segments.clear()
        problem = null
        lastWordsAt = null
        session += 1
        this.trigger = trigger
        phase = AskOmi.Phase.Listening(System.currentTimeMillis())
        haptic(OmiGATT.Haptic.Short)
        timeoutJob?.cancel()
        timeoutJob = scope.launch {
            delay(maxDuration)
            if (!isListening) return@launch
            autoSentAt = now()
            send()
        }
        startRecognizing(codec)
    }

    // Words on the phone

    private fun startRecognizing(codec: OmiGATT.Codec) {
        val shared = sharedLine()
        val recognizer = recognizer
        val decode = makeDecoder(codec)
        if (shared != null) {
            readShared(shared.line)
        } else if (recognizer != null && decode != null) {
            recognize(recognizer, decode)
        } else {
            recognition = Recognition.Unavailable
            return
        }
        waitForThePause()
    }

    private fun recognize(recognizer: LiveRecognizer, decode: (ByteArray) -> ByteArray?) {
        this.decode = decode
        recognition = Recognition.Starting
        pendingAudio.clear()
        val session = session
        wordsJob = scope.launch {
            val words = recognizer.start(language())
            // Pressed again already counts (the words still come); cancelled does not.
            if (this@AskOmiStore.session != session || recognition != Recognition.Starting) {
                recognizer.stop()
                return@launch
            }
            if (words == null) {
                recognition = Recognition.Unavailable
                return@launch
            }
            recognition = Recognition.Running
            pendingAudio.forEach(recognizer::feed)
            pendingAudio.clear()
            words.takeWhile { this@AskOmiStore.session == session }.collect(::merge)
        }
    }

    private fun waitForThePause() {
        pauseJob = scope.launch {
            while (isActive) {
                delay(200)
                if (!isListening) return@launch
                // A pressed question ends by itself once the words have paused.
                val last = lastWordsAt
                if (trigger == Trigger.Toggle && question.isNotEmpty() && last != null && (now() - last).milliseconds >= pauseToSend) {
                    autoSentAt = now()
                    send()
                    return@launch
                }
            }
        }
    }

    private fun hear(pcm: ByteArray) {
        when (recognition) {
            Recognition.Running -> recognizer?.feed(pcm)
            Recognition.Starting -> pendingAudio += pcm
            Recognition.Off, Recognition.Shared, Recognition.Unavailable -> Unit
        }
    }

    private fun stopRecognizing() {
        pauseJob?.cancel()
        if (recognition != Recognition.Shared) recognizer?.stop()
        decode = null
        pendingAudio.clear()
        if (recognition != Recognition.Unavailable) recognition = Recognition.Off
    }

    // Sending

    private fun send() {
        val listening = phase as? AskOmi.Phase.Listening ?: return
        timeoutJob?.cancel()
        pauseJob?.cancel()
        trigger = null
        val recorded = frames.toList()
        frames.clear()
        // Button actions turned off (or the Omi muted) while recording: nothing is sent.
        if (!allowed) {
            stopRecognizing()
            phase = AskOmi.Phase.Idle
            return
        }
        val codec = codec()
        val listens = recognition in setOf(Recognition.Running, Recognition.Starting, Recognition.Shared)
        if (!listens && recorded.isEmpty()) {
            phase = AskOmi.Phase.Idle
            problem = AskOmi.Problem.NothingHeard
            nothingHeard()
            return
        }
        phase = AskOmi.Phase.Sending
        sendJob = scope.launch {
            // A recognizer still starting decides first whether the words come from the phone.
            repeat(20) {
                if (recognition != Recognition.Starting) return@repeat
                delay(50)
            }
            val recognized = recognition == Recognition.Running || recognition == Recognition.Shared
            val text = if (recognized) finalWords() else ""
            if (!recognized) stopRecognizing()
            val answer = if (text.isNotEmpty()) {
                answerWithin(answerTimeout) { chat.ask(text) { haptic(OmiGATT.Haptic.Medium) } }
            } else if (!recognized && codec != null && recorded.isNotEmpty()) {
                // The phone could not listen: the backend transcribes the recording.
                askServer(recorded, codec, Instant.ofEpochMilli(listening.sinceMillis))
            } else {
                ChatStore.VoiceAnswer.NoSpeech
            }
            finish(answer, text)
        }
    }

    private fun finish(answer: ChatStore.VoiceAnswer?, text: String) {
        phase = AskOmi.Phase.Idle
        when (answer) {
            is ChatStore.VoiceAnswer.Answered -> answered(answer.text, text)
            ChatStore.VoiceAnswer.NoSpeech -> {
                problem = AskOmi.Problem.NothingHeard
                nothingHeard()
            }
            ChatStore.VoiceAnswer.Failed, null -> {
                // The same two buzzes: whoever wears the Omi knows no answer is coming.
                problem = AskOmi.Problem.NoAnswer
                nothingHeard()
            }
        }
    }

    private suspend fun askServer(recorded: List<ByteArray>, codec: OmiGATT.Codec, since: Instant): ChatStore.VoiceAnswer? {
        val (name, data) = VoiceMessageFile.file(
            recorded, codec.listenValue, codec.sampleRate,
            frameSamples = if (codec == OmiGATT.Codec.OpusFS320) 320 else 160, startedAt = since,
        )
        return answerWithin(answerTimeout) { chat.ask(name, data) { haptic(OmiGATT.Haptic.Medium) } }
    }

    /** Ends recognition and gives the last words a moment to arrive. */
    private suspend fun finalWords(): String {
        stopRecognizing()
        delay(500)
        session += 1
        wordsJob?.cancel()
        return question.trim()
    }

    private fun answered(text: String, asked: String) {
        val reply = chat.messages.lastOrNull { it.sender == com.friend.ios.core.models.ChatMessage.Sender.Omi && it.text == text }
        val spokenQuestion = reply?.let { r ->
            chat.messages.lastOrNull { it.sender == com.friend.ios.core.models.ChatMessage.Sender.User && !it.createdAt.isAfter(r.createdAt) && it.id.startsWith("voice-") }
        }
        lastExchange = AskOmi.Exchange(question = asked.ifEmpty { spokenQuestion?.text ?: "" }, answer = text)
        val spoken = reply?.let { voice?.answerArrived(it) ?: false } ?: false
        if (!spoken) onAnswer?.invoke(text)
    }

    /** Two short buzzes: nothing was heard (`_playVoiceQuestionFailureHaptic`). */
    private fun nothingHeard() {
        haptic(OmiGATT.Haptic.Short)
        scope.launch {
            delay(80)
            haptic(OmiGATT.Haptic.Short)
        }
    }
}

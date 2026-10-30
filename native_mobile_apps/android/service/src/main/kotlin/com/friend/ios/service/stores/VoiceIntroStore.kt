package com.friend.ios.service.stores

import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.service.voice.GapSentence
import com.friend.ios.service.voice.LiveRecognizer
import com.friend.ios.service.voice.LiveSegment
import com.friend.ios.service.voice.LiveTranscriptionChannel
import com.friend.ios.service.voice.PCM16
import com.friend.ios.service.voice.VoiceInput
import com.friend.ios.service.voice.VoiceProgress
import com.friend.ios.service.voice.openVoiceChannel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream

/**
 * Port of `VoiceIntroStore.swift`. Onboarding's "say something" and voice sample. One session runs
 * from the first whisper to the saved voice; nothing said here becomes a conversation. The live
 * words come from the phone's own recognizer (instant, works offline); the server's
 * transcription-only socket stands in when the phone cannot recognize the language, and a
 * watchdog hands over to the other one when speech keeps arriving without words. The training
 * part also records the audio that becomes the user's voice profile, one gap sentence at a time.
 *
 * The chat's dictation uses the same store (`start(source = Phone)`, `transcript`, `stop()`).
 */
class VoiceIntroStore(
    internal val api: APIClientProtocol,
    internal val recognizer: LiveRecognizer,
    private val phoneInput: VoiceInput,
    private val deviceInput: () -> VoiceInput,
    private val scope: CoroutineScope,
    /** The transcription-only socket (iOS reads `api.openTranscribeStream`); null keeps the server out (tests). */
    private val openTranscribeStream: (suspend (language: String) -> LiveTranscriptionChannel)? = { api.openVoiceChannel(it) },
    private val clock: () -> Long = System::currentTimeMillis,
) {
    enum class Source { Phone, Device }

    /** Where the live words come from right now. */
    enum class WordSource {
        OnDevice, Server,
        /** Neither produced words: the sentences move on by speech alone. */
        None,
    }

    sealed interface Phase {
        data object Idle : Phase
        data object Starting : Phase
        data object Listening : Phase
        data object Saving : Phase
        data object Saved : Phase
        data class Failed(val failure: Failure) : Phase
    }

    enum class Failure {
        /** Microphone or Bluetooth audio could not start. */
        Input,
        /** The upload failed; the recording is kept for a retry. */
        Upload,
    }

    /** One finished sentence of the introduction. */
    data class Answer(val id: Int, val text: String)

    var phase: Phase by mutableStateOf(Phase.Idle)
        private set
    var source: Source by mutableStateOf(Source.Phone)
        private set
    var wordSource: WordSource by mutableStateOf(WordSource.None)
        internal set
    var segments: List<LiveSegment> by mutableStateOf(emptyList())
        private set
    var level: Float by mutableStateOf(0f)
        private set
    var isTraining: Boolean by mutableStateOf(false)
        private set
    var promptIndex: Int by mutableStateOf(0)
        private set
    var answers: List<Answer> by mutableStateOf(emptyList())
        private set
    /** Seconds of speech in the voice sample so far. */
    var spokenSeconds: Double by mutableStateOf(0.0)
        private set
    /** Every sentence was said but the sample is too short: one more, free sentence. */
    var needsMore: Boolean by mutableStateOf(false)
        private set
    /** Speech heard since listening began, words or not (recognition can be unavailable). */
    var heardSeconds: Double by mutableStateOf(0.0)
        private set
    /** The current sentence laid over what was said for it. */
    var match: GapSentence.Match? by mutableStateOf(null)
        private set
    /** Milliseconds from the first speech to the first words of this session (the log has it too). */
    var firstWordsLatency: Int? by mutableStateOf(null)
        private set
    private var promptSeconds: Double by mutableStateOf(0.0)
    private var sentences: List<GapSentence> by mutableStateOf(emptyList())
    /** Asked for when the three sentences gave too little speech ("Today I ___."). */
    private var extraSentence = GapSentence.free

    /** The user said something: words arrived, or at least a second of speech. */
    val heardSomething: Boolean get() = transcript.isNotEmpty() || heardSeconds >= 1

    /** Speech on the current sentence so far (shows "Omi hears you" before words arrive). */
    val hearsSpeech: Boolean get() = promptSeconds >= 0.5

    /** The current sentence was spoken, even when no words could be recognized. */
    val canAdvance: Boolean get() = currentAnswer.isNotEmpty() || promptSeconds >= 1.5

    val transcript: String get() = segments.joinToString(" ") { it.text }.trim()

    /** What was said since the current sentence began. */
    val currentAnswer: String get() = segments.drop(promptStart).joinToString(" ") { it.text }.trim()

    val isListening: Boolean get() = phase == Phase.Listening

    /**
     * Enough speech for the profile: measured by loudness, or by the words recognized (a
     * whisper can stay under the speech level while every word is understood).
     */
    val canSave: Boolean get() = sampleSeconds >= MINIMUM_SECONDS

    /** Seconds of speech in the voice sample, the larger of both measures. */
    val sampleSeconds: Double
        get() {
            val words = (answers.map { it.text } + currentAnswer).sumOf { GapSentence.wordCount(it) }
            return maxOf(spokenSeconds, words * SECONDS_PER_WORD)
        }

    /** The sentence being spoken: one of the prompts, or the extra one asked for at the end. */
    val sentence: GapSentence?
        get() = if (needsMore) extraSentence else sentences.getOrNull(promptIndex)

    /**
     * The current sentence counts as said: it matches, or plenty of words were said for it
     * (people paraphrase, recognizers mishear) after a moment of speech.
     */
    internal val sentenceSaid: Boolean
        get() {
            val match = match ?: return false
            if (match.isComplete) return true
            val words = GapSentence.wordCount(currentAnswer)
            val wanted = maxOf(4, match.fixedTotal / 2 + match.blanks.size)
            return words >= wanted && promptSeconds >= 1.5
        }

    /** 0...1 along the sentences: a finished sentence is a full step. */
    val progress: Double get() = VoiceProgress.fraction(promptIndex, sentences.size, match?.progress ?: 0.0)

    private var input: VoiceInput? = null
    internal var channel: LiveTranscriptionChannel? = null
    internal var language = "en"
    private val jobs = mutableListOf<Job>()
    internal var wordsJob: Job? = null
    internal var switches = 0
    internal var switching = false
    /** The current word source brought words at least once. */
    internal var sourceGaveWords = false
    /** Recent chunk levels and their length, for the noise floor. */
    private val recentLevels = ArrayDeque<Pair<Float, Double>>()
    private var advancing = false
    private var sample = ByteArrayOutputStream()
    internal var recent = ByteArray(0)
    private var promptStart = 0
    /** Speech since the last new words: the watchdog's measure. */
    internal var speechWithoutWords = 0.0
    /** Quiet since the last speech, counted in audio and, when audio stops coming, in time. */
    private var silence = 0.0
    private var lastChunk = 0L
    private var firstSpeech: Long? = null

    /** Starts listening (idempotent while the same source runs in the same language). */
    suspend fun start(source: Source, language: String) {
        if ((phase == Phase.Listening || phase == Phase.Starting) && this.source == source && this.language == language) return
        stop()
        this.source = source
        this.language = language
        firstSpeech = null
        firstWordsLatency = null
        silence = 0.0
        phase = Phase.Starting
        val input = if (source == Source.Device) deviceInput() else phoneInput
        val audio: Flow<ByteArray> = try {
            input.start()
        } catch (e: Exception) {
            input.stop()
            phase = Phase.Failed(Failure.Input)
            return
        }
        this.input = input
        phase = Phase.Listening
        jobs += scope.launch { audio.collect { ingest(it) } }
        // Audio from a file (or a quiet Omi) can stop coming: pauses still count.
        jobs += scope.launch {
            while (isActive) {
                delay(200)
                evaluate()
            }
        }
        if (!startOnDevice() && !startServer()) wordSource = WordSource.None
    }

    // Sentences

    /**
     * From here on the audio also goes into the voice sample, sentence by sentence.
     * [templates] are the localized gap sentences ("My name is ___ and ..."); [extra] is asked for
     * when they gave too little speech.
     */
    fun beginTraining(templates: List<String>, extra: String? = null) {
        if (isTraining) return
        isTraining = true
        sentences = templates.map { GapSentence(it) }
        extraSentence = extra?.let { GapSentence(it) } ?: GapSentence.free
        sample = ByteArrayOutputStream()
        spokenSeconds = 0.0
        promptIndex = 0
        answers = emptyList()
        needsMore = false
        newSentence()
    }

    /**
     * Keeps what was said for this sentence and moves to the next one (the Next button, or on
     * its own once the sentence is complete and the user paused).
     */
    fun nextPrompt() {
        val text = currentAnswer
        if (text.isNotEmpty()) answers = answers + Answer(answers.size, text)
        if (!needsMore) promptIndex = minOf(promptIndex + 1, sentences.size)
        newSentence()
    }

    private fun newSentence() {
        promptStart = segments.size
        promptSeconds = 0.0
        match = sentence?.match("")
        if (wordSource == WordSource.OnDevice) recognizer.startNewUtterance()
    }

    /**
     * Ends listening and uploads the voice sample. With too little speech it keeps listening
     * and asks for one more sentence instead. Answers stay for the review.
     */
    suspend fun saveVoice() {
        nextPrompt()
        if (!canSave) {
            needsMore = true
            match = extraSentence.match("")
            return
        }
        needsMore = false
        stop(keepingSample = true)
        upload()
    }

    /** The same recording again, after a failed upload. */
    suspend fun retryUpload() = upload()

    private suspend fun upload() {
        phase = Phase.Saving
        phase = try {
            api.uploadSpeechProfile(PCM16.wav(sample.toByteArray()))
            Phase.Saved
        } catch (e: Exception) {
            Phase.Failed(Failure.Upload)
        }
    }

    /** The answers become memories ("My name is..."), as Flutter keeps them by default. */
    suspend fun saveAnswers() {
        for (answer in answers) runCatching { api.createMemory(answer.text, "system") }
    }

    fun stop() = stop(keepingSample = false)

    private fun stop(keepingSample: Boolean) {
        jobs.forEach { it.cancel() }
        jobs.clear()
        input?.stop()
        input = null
        stopWords()
        switches = 0
        recent = ByteArray(0)
        recentLevels.clear()
        speechWithoutWords = 0.0
        level = 0f
        if (!keepingSample && (phase == Phase.Listening || phase == Phase.Starting)) {
            phase = Phase.Idle
            isTraining = false
        }
    }

    // Audio

    internal fun ingest(chunk: ByteArray, now: Long = clock()) {
        send(chunk)
        val keep = (REPLAY_SECONDS * 32000).toInt()
        recent = (recent + chunk).let { if (it.size > keep) it.copyOfRange(it.size - keep, it.size) else it }
        val chunkLevel = PCM16.level(chunk)
        val seconds = chunk.size / 32000.0
        val isSpeech = chunkLevel > maxOf(SPEECH_LEVEL, noiseFloor(chunkLevel, seconds) * 2)
        level = level * 0.6f + chunkLevel * 0.4f
        lastChunk = now
        if (isSpeech) {
            if (firstSpeech == null) firstSpeech = now
            heardSeconds += seconds
            promptSeconds += seconds
            speechWithoutWords += seconds
            silence = 0.0
        } else {
            silence += seconds
        }
        if (isTraining && sample.size() / 32000.0 < MAXIMUM_SECONDS) {
            sample.write(chunk)
            if (isSpeech) spokenSeconds += seconds
        }
        evaluate(now)
    }

    /** The quietest of the last seconds of audio, capped so speech always counts. */
    private fun noiseFloor(level: Float, seconds: Double): Float {
        recentLevels.addLast(level to seconds)
        var total = recentLevels.sumOf { it.second }
        while (total > NOISE_WINDOW_SECONDS && recentLevels.size > 1) total -= recentLevels.removeFirst().second
        return minOf(MAXIMUM_NOISE_FLOOR, recentLevels.minOfOrNull { it.first } ?: 0f)
    }

    /** The watchdog and the automatic move to the next sentence. */
    internal fun evaluate(now: Long = clock()) {
        if (phase != Phase.Listening) return
        val patience = if (sourceGaveWords) WATCHDOG_AFTER_WORDS_SECONDS else WATCHDOG_SECONDS
        if (wordSource != WordSource.None && speechWithoutWords >= patience) switchSource()
        if (!isTraining || advancing || match == null) return
        val quiet = silence + maxOf(0.0, (now - lastChunk) / 1000.0 - 0.25)
        // No words for this sentence from a source that never gave any, with no other left.
        val noWords = wordSource == WordSource.None || switches >= MAXIMUM_SWITCHES && !sourceGaveWords
        val blind = noWords && segments.size == promptStart
        var said = if (blind) promptSeconds >= BLIND_SENTENCE_SECONDS else sentenceSaid
        // The extra sentence goes on until the sample is long enough.
        if (needsMore) said = said && canSave
        if (!said || quiet < PAUSE_SECONDS) return
        advancing = true
        scope.launch {
            try {
                if (needsMore || promptIndex >= sentences.size - 1) saveVoice() else nextPrompt()
            } finally {
                advancing = false
            }
        }
    }

    /** Segments are re-sent when refined; the same id replaces the earlier text. */
    internal fun merge(new: List<LiveSegment>) {
        var changed = false
        val list = segments.toMutableList()
        for (segment in new) {
            if (segment.text.isBlank()) continue
            val index = list.indexOfFirst { it.id == segment.id }
            if (index >= 0) {
                if (list[index].text == segment.text) continue
                list[index] = segment
            } else {
                list += segment
            }
            changed = true
        }
        if (!changed) return
        segments = list
        speechWithoutWords = 0.0
        sourceGaveWords = true
        if (firstWordsLatency == null) {
            val latency = (clock() - (firstSpeech ?: clock())).toInt()
            firstWordsLatency = latency
            log("first words $latency ms after speech ($wordSource)")
        }
        if (isTraining) match = sentence?.match(currentAnswer)
    }

    // Words (`VoiceIntroStore+Words.swift`): the phone's recognizer first, the server's
    // transcription-only socket when the phone cannot, and the watchdog's hand-over between them.

    internal suspend fun startOnDevice(): Boolean {
        val words = recognizer.start(language)
        if (words == null) {
            log("on-device recognition unavailable for $language")
            return false
        }
        wordSource = WordSource.OnDevice
        wordsJob = scope.launch { words.collect { merge(listOf(it)) } }
        return true
    }

    internal suspend fun startServer(): Boolean {
        val open = openTranscribeStream
        val channel = open?.let { runCatching { it(language) }.getOrNull() }
        if (channel == null) {
            log("server transcription unavailable")
            return false
        }
        this.channel = channel
        wordSource = WordSource.Server
        wordsJob = scope.launch {
            try {
                channel.events.collect { event ->
                    if (event is LiveTranscriptionChannel.Event.Segments) merge(event.segments)
                    if (event is LiveTranscriptionChannel.Event.Status &&
                        (event.status == "stt_failed" || event.status.startsWith("disconnected"))
                    ) throw StopCollecting()
                }
            } catch (_: StopCollecting) {
            }
            // The server stopped transcribing while we still listen: the other source takes over.
            if (phase == Phase.Listening && this@VoiceIntroStore.channel === channel) switchSource(failed = true)
        }
        return true
    }

    private class StopCollecting : RuntimeException()

    /**
     * The current source produced no words for a while (or failed): try the other one, and
     * replay the last seconds of audio into it. Over and back at most; after that the last
     * source keeps listening (a working recognizer is never dropped for good), and only when
     * none ever started do the sentences go by speech alone.
     */
    internal fun switchSource(failed: Boolean = false) {
        if (switching || wordSource == WordSource.None || phase != Phase.Listening) return
        speechWithoutWords = 0.0
        if (switches >= MAXIMUM_SWITCHES) {
            // A source that failed outright cannot stay; a quiet one can.
            if (failed) stopWords()
            return
        }
        val from = wordSource
        log("no words from $from; switching")
        stopWords()
        switches += 1
        switching = true
        scope.launch {
            try {
                val started = if (from == WordSource.OnDevice) startServer() else startOnDevice()
                if (!started) return@launch
                if (phase != Phase.Listening) return@launch stopWords()
                replay(recent)
            } finally {
                switching = false
            }
        }
    }

    internal fun stopWords() {
        wordsJob?.cancel()
        wordsJob = null
        channel?.close("onboarding")
        channel = null
        recognizer.stop()
        wordSource = WordSource.None
        sourceGaveWords = false
    }

    internal fun replay(audio: ByteArray) {
        var offset = 0
        while (offset < audio.size) {
            val end = minOf(offset + 3200, audio.size)
            send(audio.copyOfRange(offset, end))
            offset = end
        }
    }

    internal fun send(chunk: ByteArray) {
        when (wordSource) {
            WordSource.OnDevice -> recognizer.feed(chunk)
            WordSource.Server -> channel?.send(chunk)
            WordSource.None -> Unit
        }
    }

    private fun log(message: String) {
        runCatching { Log.i("omi.voice", message) }
    }

    companion object {
        /** Speech the profile wants before it is saved; the server accepts 5 s and more. */
        const val MINIMUM_SECONDS = 8.0
        const val MAXIMUM_SECONDS = 170.0
        /** Above this level a chunk counts as speech. */
        const val SPEECH_LEVEL = 0.008f
        /** Speech without a single word before the other source gets its turn. */
        const val WATCHDOG_SECONDS = 2.5
        /**
         * The same, once the source has brought words: recognizers lag and rest between sentences,
         * so a working one is not dropped for a short silence of its own.
         */
        const val WATCHDOG_AFTER_WORDS_SECONDS = 8.0
        /**
         * The quietest audio of the last seconds sets how loud speech has to be (a noisy Omi
         * microphone still has pauses); never above this, so speech always counts.
         */
        const val MAXIMUM_NOISE_FLOOR = 0.03f
        const val NOISE_WINDOW_SECONDS = 4.0
        /** A recognized word stands for about this much speech in the voice sample. */
        const val SECONDS_PER_WORD = 0.3
        /** The pause after a finished sentence before the next one comes up. */
        const val PAUSE_SECONDS = 0.7
        /** Without words, a sentence counts as said after this much speech and a pause. */
        const val BLIND_SENTENCE_SECONDS = 2.5
        /** Audio kept to replay into the next source, so words said during the hand-over are not lost. */
        const val REPLAY_SECONDS = 3.0
        const val MAXIMUM_SWITCHES = 2
    }
}

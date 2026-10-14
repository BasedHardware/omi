package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.supervisorScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.text.BreakIterator

/**
 * What reads Omi's answers aloud (`SpeechAudioPlaying` in `SpeechPlayer.swift`): audio from the
 * backend voice, or the system voice. The app supplies Android's TextToSpeech.
 */
interface SpeechAudioPlaying {
    /** Plays encoded audio (mp3) to the end. */
    suspend fun play(audio: ByteArray)
    /** The system voice reads [text] to the end. */
    suspend fun speak(text: String)
    fun stop()
}

/**
 * Port of `VoicePlaybackStore.swift`: Omi's answers read aloud with the backend voice
 * (`POST v2/tts/synthesize`), as Flutter's `OmiVoicePlaybackService`: finished answers on their
 * own when the reply mode allows (in the chat and for questions asked with the Omi's button), any
 * answer from its "Read aloud" action, the voice preview in Settings > Assistant and the
 * spoken-reply preview in onboarding.
 */
class VoicePlaybackStore(
    private val preferences: Preferences,
    private val player: SpeechAudioPlaying,
    private val scope: CoroutineScope,
    private val synthesize: (suspend (text: String, voiceID: String?) -> ByteArray)? = null,
    private val headphonesConnected: () -> Boolean = { false },
) {
    /** Settings > Assistant > Spoken replies (Flutter `voiceResponseMode`). */
    enum class ReplyMode(val rawValue: Int) {
        Off(0), HeadphonesOnly(1), Always(2);

        companion object {
            fun from(raw: Int): ReplyMode? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    /** What is playing: a message id, or `preview:<voice>`. */
    var playingID: String? by mutableStateOf(null)
        private set
    /** Waiting for the first audio. */
    var isLoading: Boolean by mutableStateOf(false)
        private set
    /** The last preview could not be played (no system-voice stand-in for a voice preview). */
    var previewFailed: Boolean by mutableStateOf(false)
        private set

    private var job: Job? = null

    val replyMode: ReplyMode
        get() = ReplyMode.from(preferences.integer(Key.VoiceResponseMode, 1)) ?: ReplyMode.HeadphonesOnly

    /** The same preference as Settings > Assistant > Spoken replies. */
    fun setReplyMode(mode: ReplyMode) = preferences.set(Key.VoiceResponseMode, mode.rawValue)

    /**
     * A finished answer arrived (chat on screen, or a question from the Omi's button). Returns
     * whether it is being read aloud; an answer already playing is not started twice.
     */
    fun answerArrived(message: ChatMessage): Boolean {
        if (playingID == message.id) return true
        if (!isSpeakable(message) || !readsAloud(replyMode, headphonesConnected())) return false
        play(message)
        return true
    }

    /** "Read aloud": plays this answer, or stops it when it is the one playing. */
    fun toggle(message: ChatMessage) {
        if (playingID == message.id) {
            stop()
        } else if (isSpeakable(message)) {
            play(message)
        }
    }

    /**
     * Onboarding's spoken-reply preview: [text] in the chosen voice whatever the reply mode, with
     * the system voice standing in when the backend voice is unavailable (Flutter `playPreview`).
     */
    fun previewReply(text: String) {
        if (playingID == REPLY_PREVIEW_ID) return stop()
        start(REPLY_PREVIEW_ID, speakableText(text), voiceID = null, systemFallback = true)
    }

    /** Settings > Assistant: a sample in [voiceID], or stop when that preview is playing. */
    fun preview(voiceID: String, sample: String) {
        val id = "preview:$voiceID"
        if (playingID == id) return stop()
        previewFailed = false
        start(id, sample, voiceID, systemFallback = false)
    }

    fun stop() {
        job?.cancel()
        job = null
        player.stop()
        playingID = null
        isLoading = false
    }

    private fun play(message: ChatMessage) = start(message.id, speakableText(message.text), voiceID = null, systemFallback = true)

    private fun start(id: String, text: String, voiceID: String?, systemFallback: Boolean) {
        stop()
        val chunks = chunks(text)
        if (chunks.isEmpty()) return
        playingID = id
        isLoading = true
        job = scope.launch {
            speak(chunks, voiceID, systemFallback)
            if (!isActive) return@launch
            playingID = null
            isLoading = false
        }
    }

    /**
     * Fetches the next piece while the current one plays. When the backend voice is unavailable
     * (quota, rate limit, offline) the rest of an answer is read by the system voice.
     */
    private suspend fun speak(chunks: List<String>, voiceID: String?, systemFallback: Boolean): Unit = supervisorScope {
        fun fetch(index: Int): Deferred<ByteArray> = async {
            synthesize?.invoke(chunks[index], voiceID) ?: throw IllegalStateException("no backend voice")
        }
        var next: Deferred<ByteArray>? = fetch(0)
        try {
            for (index in chunks.indices) {
                val pending = next ?: return@supervisorScope
                val audio = try {
                    pending.await()
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    isLoading = false
                    if (systemFallback) player.speak(chunks.drop(index).joinToString(" ")) else previewFailed = true
                    return@supervisorScope
                }
                next = if (index + 1 < chunks.size) fetch(index + 1) else null
                isLoading = false
                try {
                    player.play(audio)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    if (systemFallback) player.speak(chunks.drop(index).joinToString(" "))
                    return@supervisorScope
                }
            }
        } finally {
            next?.cancel()
        }
    }

    companion object {
        fun isSpeakable(message: ChatMessage): Boolean =
            message.sender == ChatMessage.Sender.Omi && message.failure == null &&
                !ChatStreamEvent.isServiceFailure(message.text) && speakableText(message.text).isNotEmpty()

        /** What [previewReply] plays under. */
        const val REPLY_PREVIEW_ID = "preview:reply"
        /** One request stays well under the backend's 5,000 characters, and short first audio starts sooner. */
        const val CHUNK_LIMIT = 600

        /** Off never speaks, headphones only speaks into private listening. */
        fun readsAloud(mode: ReplyMode, headphones: Boolean): Boolean = when (mode) {
            ReplyMode.Off -> false
            ReplyMode.HeadphonesOnly -> headphones
            ReplyMode.Always -> true
        }

        /**
         * The words of a Markdown answer: no code, link targets, URLs or emphasis markers (Flutter
         * `_cleanedPlaybackText`).
         */
        fun speakableText(markdown: String): String {
            var text = markdown
            val rules = listOf(
                "```[\\s\\S]*?```" to " ",
                "`[^`]*`" to " ",
                "\\[([^\\]]+)\\]\\([^)]+\\)" to "$1",
                "https?://\\S+" to " ",
                "\\*\\*|__" to "",
                "(?<!\\*)\\*(?!\\*)" to "",
                "(?m)^\\s*(#+|>|[-•]\\s)" to " ",
                "\\|" to " ",
                "\\s+" to " ",
            )
            for ((pattern, template) in rules) text = text.replace(Regex(pattern), template)
            return text.trim()
        }

        /** Sentence-sized pieces of at most [limit] characters. */
        fun chunks(text: String, limit: Int = CHUNK_LIMIT): List<String> {
            val chunks = mutableListOf<String>()
            var current = ""
            val iterator = BreakIterator.getSentenceInstance()
            iterator.setText(text)
            var start = iterator.first()
            var end = iterator.next()
            while (end != BreakIterator.DONE) {
                val sentence = text.substring(start, end).trim()
                start = end
                end = iterator.next()
                if (sentence.isEmpty()) continue
                if (current.isNotEmpty() && current.length + sentence.length + 1 > limit) {
                    chunks += current
                    current = ""
                }
                var rest = sentence
                while (rest.length > limit) {
                    chunks += rest.take(limit)
                    rest = rest.drop(limit)
                }
                current = if (current.isEmpty()) rest else "$current $rest"
            }
            if (current.isNotEmpty()) chunks += current
            return chunks
        }
    }
}

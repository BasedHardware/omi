package com.friend.ios.service.stores

import com.friend.ios.device.OmiGATT
import com.friend.ios.service.voice.LiveSegment
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.time.Duration

/*
 * Port of `AskOmiStore+Support.swift`: Ask Omi's helpers: the question's words from a recognizer
 * that already runs, the Omi's frames as PCM for the recognizer, and a wait that always ends.
 */

/**
 * The capture already transcribes the Omi on the phone: the question is what its line says after
 * the press (the rest of a line that was running, then the new ones).
 */
internal fun AskOmiStore.readShared(baseline: LiveSegment?) {
    recognition = AskOmiStore.Recognition.Shared
    val session = session
    val before = baseline?.let { questionWords(it.text).size } ?: 0
    wordsJob = scope.launch {
        while (this@readShared.session == session) {
            sharedLine()?.line?.let { found ->
                val line = if (found.id == baseline?.id) found.copy(text = questionWords(found.text).drop(before).joinToString(" ")) else found
                merge(line)
            }
            delay(150)
        }
    }
}

internal fun questionWords(text: String): List<String> = text.split(Regex("\\s+")).filter { it.isNotEmpty() }

/** The recognizer re-sends a line while it grows (same id) and starts a new id per utterance. */
internal fun AskOmiStore.merge(segment: LiveSegment) {
    if (segment.text.isBlank()) return
    val index = segments.indexOfFirst { it.id == segment.id }
    if (index >= 0) {
        if (segments[index].text == segment.text) return
        segments[index] = segment
    } else {
        segments += segment
    }
    question = segments.joinToString(" ") { it.text }
    lastWordsAt = now()
}

/** The answer, or null when it did not come in time (the request is cancelled then). */
internal suspend fun answerWithin(limit: Duration, work: suspend () -> ChatStore.VoiceAnswer): ChatStore.VoiceAnswer? =
    withTimeoutOrNull(limit) { work() }

/**
 * The Omi's frames as 16 kHz PCM16 for the recognizer; null for a codec it cannot use. Opus needs
 * the platform decoder, which the app supplies (`makeDecoder`); here only PCM16 passes.
 */
fun pcmDecoder(codec: OmiGATT.Codec): ((ByteArray) -> ByteArray?)? = when (codec) {
    OmiGATT.Codec.Pcm16 -> { frame -> frame }
    OmiGATT.Codec.Opus, OmiGATT.Codec.OpusFS320, OmiGATT.Codec.Pcm8 -> null
}

/** A recognizer that already listens to the Omi: its newest line (null while it has none yet). */
data class SharedLine(val line: LiveSegment?)

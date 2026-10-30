package com.friend.ios.voice

import com.friend.ios.service.voice.LiveRecognizer
import com.friend.ios.service.voice.LiveSegment
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Debug builds (`--es omiAskTranscript "..."`): a stand-in recognizer that says a fixed question,
 * one word every 300 ms, so Ask Omi runs on the emulator without speech (iOS `ScriptedSpeech`,
 * paced by time here instead of by the audio's level).
 */
class ScriptedRecognizer(private val script: String) : LiveRecognizer {
    override suspend fun start(language: String): Flow<LiveSegment> = flow {
        val words = script.split(" ").filter { it.isNotBlank() }
        for (count in 1..words.size) {
            delay(300)
            emit(LiveSegment(id = "scripted-0", text = words.take(count).joinToString(" ")))
        }
    }

    override fun feed(pcm16: ByteArray) = Unit
    override fun startNewUtterance() = Unit
    override fun stop() = Unit
}

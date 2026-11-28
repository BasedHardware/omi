package com.friend.ios.service.stores

import com.friend.ios.core.models.ChatContext
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.core.models.DeviceToolResult
import com.friend.ios.device.OmiGATT
import com.friend.ios.network.endpoints.AgentAPI
import com.friend.ios.network.endpoints.ChatAPI
import com.friend.ios.network.endpoints.ChatStreamEvent
import com.friend.ios.network.endpoints.VoiceMessagesAPI
import com.friend.ios.persistence.Preferences
import com.friend.ios.service.freshPreferences
import com.friend.ios.service.voice.LiveRecognizer
import com.friend.ios.service.voice.LiveSegment
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
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
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds

/** The chat's API with the transcription and the device tool result post (one client in the app). */
class AskFakeAPI(val chat: FakeChatAPI = FakeChatAPI()) :
    ChatAPI by chat,
    VoiceMessagesAPI,
    AgentAPI by HomeFakeAPI.unimplemented() {
    var transcript = ""
    val voiceUploads = mutableListOf<Pair<String, ByteArray>>()
    val declaredTools = mutableListOf<List<String>>()
    val results = mutableListOf<Pair<String, DeviceToolResult>>()

    override fun sendChatMessage(text: String, fileIDs: List<String>, context: ChatContext?, sessionID: String?, deviceTools: List<String>): Flow<ChatStreamEvent> {
        declaredTools += deviceTools
        return chat.sendChatMessage(text, fileIDs, context, sessionID, deviceTools)
    }

    override suspend fun transcribeVoiceMessage(filename: String, audio: ByteArray): String {
        voiceUploads += filename to audio
        return transcript
    }

    override suspend fun synthesizeSpeech(text: String, voiceID: String?): ByteArray = throw NotImplementedError()

    override suspend fun sendDeviceToolResult(callID: String, result: DeviceToolResult) {
        results += callID to result
    }
}

/** Live words on demand: the test sends segments, the store merges them. */
class FakeRecognizer(private val available: Boolean = true) : LiveRecognizer {
    val words = Channel<LiveSegment>(Channel.UNLIMITED)
    val fed = mutableListOf<ByteArray>()
    var stopped = 0
    override suspend fun start(language: String): Flow<LiveSegment>? = if (available) words.receiveAsFlow() else null
    override fun feed(pcm16: ByteArray) {
        fed += pcm16
    }
    override fun startNewUtterance() = Unit
    override fun stop() {
        stopped += 1
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class AskOmiStoreTest {
    class Harness {
        val api = AskFakeAPI()
        val haptics = mutableListOf<OmiGATT.Haptic>()
        var allowed = true
        val answers = mutableListOf<String>()
        var codec: OmiGATT.Codec? = OmiGATT.Codec.OpusFS320
    }

    private fun TestScope.make(
        harness: Harness,
        recognizer: LiveRecognizer? = null,
        voice: VoicePlaybackStore? = null,
        prefs: Preferences = freshPreferences(),
    ): Pair<AskOmiStore, ChatStore> {
        val chat = ChatStore(harness.api, prefs, this)
        val store = AskOmiStore(
            chat = chat, scope = this, voice = voice,
            codec = { harness.codec }, haptic = { harness.haptics += it }, canAsk = { harness.allowed },
            recognizer = recognizer, makeDecoder = { { it } },
            pauseToSend = 300.milliseconds, now = { testScheduler.currentTime },
        )
        store.onAnswer = { harness.answers += it }
        return store to chat
    }

    /** Press, speak, press: without the phone's recognizer the Omi's frames go to the backend in Flutter's file format. */
    @Test
    fun pressRecordsAndSecondPressSends() = runTest {
        val harness = Harness()
        harness.api.transcript = "What's next?"
        harness.api.chat.stream = listOf(ChatStreamEvent.Delta("Your 3 pm call."))
        val (store, chat) = make(harness)
        store.ingest(byteArrayOf(9))
        store.handle(ButtonAction.AskToggle)
        assertTrue(store.isListening)
        store.ingest(byteArrayOf(0xAA.toByte(), 0xBB.toByte()))
        store.ingest(byteArrayOf(0xCC.toByte()))
        store.handle(ButtonAction.AskToggle)
        store.sendJob?.join()
        val upload = harness.api.voiceUploads.single()
        assertTrue(upload.first.startsWith("audio_omi_opus_fs320_16000_1_fs320_"))
        assertArrayEquals(byteArrayOf(2, 0, 0, 0, 0xAA.toByte(), 0xBB.toByte(), 1, 0, 0, 0, 0xCC.toByte()), upload.second)
        assertEquals(listOf(OmiGATT.Haptic.Short, OmiGATT.Haptic.Medium), harness.haptics)
        assertEquals(listOf("Your 3 pm call."), harness.answers)
        assertEquals(listOf("What's next?", "Your 3 pm call."), chat.messages.takeLast(2).map { it.text })
        assertEquals(AskOmi.Phase.Idle, store.phase)
        assertEquals(AskOmi.Exchange("What's next?", "Your 3 pm call."), store.lastExchange)
    }

    @Test
    fun nothingRecordedSendsNothing() = runTest {
        val harness = Harness()
        val (store, _) = make(harness)
        store.handle(ButtonAction.AskToggle)
        store.handle(ButtonAction.AskToggle)
        advanceTimeBy(100)
        assertTrue(harness.api.voiceUploads.isEmpty())
        assertEquals(List(3) { OmiGATT.Haptic.Short }, harness.haptics)
        assertEquals(AskOmi.Problem.NothingHeard, store.problem)
    }

    @Test
    fun noSpeechLeavesTheChatAlone() = runTest {
        val harness = Harness()
        harness.api.transcript = ""
        val (store, chat) = make(harness)
        store.handle(ButtonAction.AskToggle)
        store.ingest(byteArrayOf(1))
        store.handle(ButtonAction.AskToggle)
        store.sendJob?.join()
        assertTrue(chat.messages.none { it.id.startsWith("voice-") || it.id.startsWith("pending-") })
        assertTrue(harness.answers.isEmpty())
        assertEquals(AskOmi.Problem.NothingHeard, store.problem)
    }

    @Test
    fun heldPressSendsOnRelease() = runTest {
        val harness = Harness()
        harness.api.transcript = "Hi"
        harness.api.chat.stream = listOf(ChatStreamEvent.Delta("Hello"))
        val (store, _) = make(harness)
        // A plain release (sent after every tap) does not end a toggled question.
        store.handle(ButtonAction.AskToggle)
        store.handle(ButtonAction.AskHoldEnd)
        assertTrue(store.isListening)
        store.handle(ButtonAction.AskToggle)
        advanceUntilIdle()
        store.handle(ButtonAction.AskHoldStart)
        store.ingest(byteArrayOf(1))
        store.handle(ButtonAction.AskHoldEnd)
        store.sendJob?.join()
        assertEquals(1, harness.api.voiceUploads.size)
    }

    @Test
    fun mutedOrDisabledOmiAsksNothing() = runTest {
        val harness = Harness()
        harness.allowed = false
        val (store, _) = make(harness)
        store.handle(ButtonAction.AskToggle)
        assertFalse(store.isListening)
        harness.allowed = true
        store.handle(ButtonAction.AskToggle)
        store.ingest(byteArrayOf(1))
        harness.allowed = false
        store.handle(ButtonAction.AskToggle)
        advanceUntilIdle()
        assertTrue(harness.api.voiceUploads.isEmpty())
        assertEquals(AskOmi.Phase.Idle, store.phase)
    }

    @Test
    fun practiceAsksEvenWithButtonActionsOff() = runTest {
        val harness = Harness()
        harness.allowed = false
        val (store, _) = make(harness)
        store.isPractice = true
        store.handle(ButtonAction.AskToggle)
        assertTrue(store.isListening)
    }

    @Test
    fun disconnectCancelsTheQuestion() = runTest {
        val harness = Harness()
        val (store, _) = make(harness)
        store.handle(ButtonAction.AskToggle)
        store.ingest(byteArrayOf(1))
        store.cancel()
        assertEquals(AskOmi.Phase.Idle, store.phase)
        advanceUntilIdle()
        assertTrue(harness.api.voiceUploads.isEmpty())
    }

    /** With the phone's recognizer: the words show live and a pause sends the question by itself. */
    @Test
    fun wordsOnThePhoneAndAPauseSends() = runTest {
        val harness = Harness()
        harness.api.chat.stream = listOf(ChatStreamEvent.Delta("At 3 pm."))
        val recognizer = FakeRecognizer()
        val (store, chat) = make(harness, recognizer)
        store.handle(ButtonAction.AskToggle)
        store.ingest(byteArrayOf(5, 6))
        runCurrent()
        recognizer.words.trySend(LiveSegment("s1", "When is"))
        recognizer.words.trySend(LiveSegment("s1", "When is my call"))
        runCurrent()
        assertEquals("When is my call", store.question)
        assertEquals(listOf(5.toByte(), 6.toByte()), recognizer.fed.single().toList())
        advanceTimeBy(1.seconds)
        store.sendJob?.join()
        assertTrue(harness.api.voiceUploads.isEmpty())
        assertEquals(listOf("When is my call"), harness.api.chat.sent)
        assertEquals("At 3 pm.", chat.messages.last().text)
        assertEquals(AskOmi.Exchange("When is my call", "At 3 pm."), store.lastExchange)
        // The press right after a question sent itself only stops it.
        store.handle(ButtonAction.AskToggle)
        assertFalse(store.isListening)
    }

    /** Words that keep coming every 300 ms are one question; the 2 s pause after the last one sends it. */
    @Test
    fun steadyWordsAreOneQuestion() = runTest {
        val harness = Harness()
        harness.api.chat.stream = listOf(ChatStreamEvent.Delta("Nothing today."))
        val recognizer = object : LiveRecognizer {
            override suspend fun start(language: String): Flow<LiveSegment> = flow {
                val words = "What is on my calendar today".split(" ")
                for (count in 1..words.size) {
                    kotlinx.coroutines.delay(300)
                    emit(LiveSegment("s", words.take(count).joinToString(" ")))
                }
            }
            override fun feed(pcm16: ByteArray) = Unit
            override fun startNewUtterance() = Unit
            override fun stop() = Unit
        }
        val chat = ChatStore(harness.api, freshPreferences(), this)
        val store = AskOmiStore(
            chat = chat, scope = this, codec = { harness.codec }, haptic = {}, canAsk = { true },
            recognizer = recognizer, makeDecoder = { { it } }, now = { testScheduler.currentTime },
        )
        store.handle(ButtonAction.AskToggle)
        advanceTimeBy(5.seconds)
        store.sendJob?.join()
        assertEquals(listOf("What is on my calendar today"), harness.api.chat.sent)
    }

    @Test
    fun unansweredQuestionEndsAsNoAnswer() = runTest {
        val harness = Harness()
        harness.api.chat.streamFlow = flow { awaitCancellation() }
        val recognizer = FakeRecognizer()
        val (store, _) = make(harness, recognizer)
        store.handle(ButtonAction.AskToggle)
        runCurrent()
        recognizer.words.trySend(LiveSegment("s1", "Hello there"))
        runCurrent()
        store.handle(ButtonAction.AskToggle)
        advanceTimeBy(31.seconds)
        runCurrent()
        assertEquals(AskOmi.Problem.NoAnswer, store.problem)
        assertEquals(AskOmi.Phase.Idle, store.phase)
        assertTrue(harness.answers.isEmpty())
    }

    @Test
    fun answerReadAloudIsNotNotified() = runTest {
        val harness = Harness()
        harness.api.transcript = "Hi"
        harness.api.chat.stream = listOf(ChatStreamEvent.Delta("Hello"))
        val prefs = freshPreferences()
        val player = RecordingPlayer()
        val voice = VoicePlaybackStore(prefs, player, this, synthesize = { _, _ -> byteArrayOf(1) })
        voice.setReplyMode(VoicePlaybackStore.ReplyMode.Always)
        val (store, _) = make(harness, voice = voice, prefs = prefs)
        store.handle(ButtonAction.AskToggle)
        store.ingest(byteArrayOf(1))
        store.handle(ButtonAction.AskToggle)
        store.sendJob?.join()
        advanceUntilIdle()
        assertTrue(harness.answers.isEmpty())
        assertEquals(1, player.played.size)
        assertNull(voice.playingID)
    }
}

/** Records what would sound. */
class RecordingPlayer(private val failPlay: Boolean = false) : SpeechAudioPlaying {
    val played = mutableListOf<ByteArray>()
    val spoken = mutableListOf<String>()
    var stops = 0
    val gate: CompletableDeferred<Unit>? = null
    override suspend fun play(audio: ByteArray) {
        if (failPlay) throw IllegalStateException("bad audio")
        played += audio
        gate?.await()
    }
    override suspend fun speak(text: String) {
        spoken += text
    }
    override fun stop() {
        stops += 1
    }
}

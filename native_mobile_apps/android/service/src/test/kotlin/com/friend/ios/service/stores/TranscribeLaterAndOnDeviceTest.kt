package com.friend.ios.service.stores

import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.SyncUpload
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.CaptureFailure
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.PhoneAudioFile
import com.friend.ios.service.PhoneCaptureEngine
import com.friend.ios.service.PhoneCaptureStreams
import com.friend.ios.service.TranscriptUpdate
import com.friend.ios.service.UnavailableDeviceTranscriptionEngine
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * Port of the phone-buffering and on-device cases of `CaptureStoreTests` / `SyncStoreTests`:
 * Transcribe later writes the Flutter WAL format to the sync queue, uploads only when asked;
 * an offline recording uploads by itself; on-device mode turns the phone's recognizer into the
 * transcript and sends it to the socket as `suggested_transcript`.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TranscribeLaterAndOnDeviceTest {
    private class FakeChannel : LiveTranscriptionChannel {
        val incoming = Channel<ListenEvent>(Channel.UNLIMITED)
        override val events: Flow<ListenEvent> = incoming.receiveAsFlow()
        val audio = mutableListOf<ByteArray>()
        val suggested = mutableListOf<Pair<List<LiveSegment>, String>>()

        override fun send(audio: ByteArray) {
            this.audio += audio
        }

        override fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String) {
            suggested += segments to provider
        }

        override fun close(reason: String) {
            incoming.close()
        }

        override fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) = Unit
    }

    /** A microphone with an optional recognizer: chunks and recognizer lines pushed by the test. */
    private class Engine(private val recognizer: Boolean) : PhoneCaptureEngine {
        var pcm = Channel<ByteArray>(Channel.UNLIMITED)
        var transcript = Channel<TranscriptUpdate>(Channel.UNLIMITED)
        override val supportsOnDevice: Boolean get() = recognizer

        override suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams {
            if (transcribeOnDevice && !recognizer) throw CaptureFailure.SpeechUnavailable
            pcm = Channel(Channel.UNLIMITED)
            transcript = Channel(Channel.UNLIMITED)
            return PhoneCaptureStreams(pcm.receiveAsFlow(), Channel<Float>().receiveAsFlow(), if (transcribeOnDevice) transcript.receiveAsFlow() else null)
        }

        override fun stop() = Unit
    }

    private val uploads = mutableListOf<String>()

    private fun api(sockets: MutableList<FakeChannel>, options: MutableList<ListenSocket.Options>, online: Boolean = true): FakeAPI = fakeAPI {
        "openListenSocket" does { args ->
            if (!online) throw APIError.Transport("offline")
            options += args[1] as ListenSocket.Options
            FakeChannel().also { sockets += it }
        }
        "finalizeInProgressConversation" returns "c1"
        "subscription" throws APIError.Transport("offline")
        "uploadOfflineRecording" does { args ->
            uploads += args[0] as String
            SyncUpload(null, "completed")
        }
    }

    private fun directory(): File = Files.createTempDirectory("phone-audio").toFile()

    private fun TestScope.scope() = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[kotlinx.coroutines.Job]!!)

    @Test
    fun phoneAudioFileWritesWholeTenMillisecondFrames() {
        val dir = directory()
        val file = PhoneAudioFile(dir, PhoneAudioFile.Kind.Phone(manual = true), "alice", 1_760_000_000.0)
        assertFalse(file.append(ByteArray(1000) { 1 }))
        file.close()
        assertEquals("audio_omibatchphone_pcm16_16000_1_fs160_1760000000.bin", file.recording.filename)
        assertEquals(3, file.recording.frames)
        assertEquals(true, file.recording.manual)
        val bytes = File(dir, file.recording.filename).readBytes()
        assertEquals(3 * (4 + 320), bytes.size)
        assertEquals(listOf(320, 320, 320), syncFrames(bytes).map { it.size })
        assertTrue(file.recording.isPhone)
        assertTrue(file.recording.isPCM)
    }

    @Test
    fun transcribeLaterRecordsToTheQueueAndUploadsOnlyWhenAsked() = runTest(UnconfinedTestDispatcher()) {
        val sockets = mutableListOf<FakeChannel>()
        val api = api(sockets, mutableListOf())
        val sync = SyncStore(api.client, directory(), scope(), userID = { "alice" })
        val preferences = freshPreferences()
        val engine = Engine(recognizer = false)
        val capture = CaptureStore(
            api.client, engine, UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        capture.phoneBuffer = SyncStorePhoneAudio(sync, nowSeconds = { 1_760_000_100.0 })
        capture.transcribesLater = true
        assertTrue(preferences.bool(Key.BatchModeEnabled))

        capture.startPhone()
        assertTrue(capture.isLive)
        assertTrue(capture.isBuffering)
        assertTrue(sockets.isEmpty())
        assertNotNull(sync.files.state.phoneOpen)
        engine.pcm.send(ByteArray(32_000 * 3) { 2 })
        capture.stop()

        assertFalse(capture.isBuffering)
        val recording = sync.phoneRecordings.single()
        assertTrue(recording.filename.startsWith("audio_omibatchphone_pcm16_16000_1_fs160_"))
        assertEquals(300, recording.frames)
        assertEquals(true, recording.manual)
        assertNull(sync.files.state.phoneOpen)
        // Nothing reached the server: no conversation to finalize, nothing uploaded by itself.
        assertTrue(api.called("finalizeInProgressConversation").isEmpty())
        sync.uploadPending()
        assertTrue(uploads.isEmpty())

        // The WAV to play or share.
        val wav = sync.audioWav(recording.filename)!!
        assertEquals(44 + 96_000, wav.size)

        sync.process(recording.filename)
        assertEquals(listOf(recording.filename), uploads)
        assertTrue(sync.phoneRecordings.isEmpty())
    }

    @Test
    fun offlineRecordingUploadsByItselfWhenItEnds() = runTest(UnconfinedTestDispatcher()) {
        val api = api(mutableListOf(), mutableListOf(), online = false)
        val sync = SyncStore(api.client, directory(), scope(), userID = { "alice" })
        val engine = Engine(recognizer = false)
        val capture = CaptureStore(
            api.client, engine, UnavailableDeviceTranscriptionEngine(), freshPreferences(), defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        capture.phoneBuffer = SyncStorePhoneAudio(sync)
        capture.startPhone()
        assertTrue(capture.isBuffering)
        engine.pcm.send(ByteArray(6400))
        capture.stop()
        val uploaded = uploads.single()
        assertTrue(uploaded.startsWith("audio_phonemic_pcm16_16000_1_fs160_"))
        assertTrue(sync.recordings.isEmpty())
    }

    @Test
    fun keptCopyStaysOnThePhoneAndNeverUploads() = runTest(UnconfinedTestDispatcher()) {
        val sockets = mutableListOf<FakeChannel>()
        val api = api(sockets, mutableListOf())
        val sync = SyncStore(api.client, directory(), scope(), userID = { "alice" })
        val preferences = freshPreferences()
        preferences.set(Key.UnlimitedLocalStorageEnabled, true)
        val engine = Engine(recognizer = false)
        val capture = CaptureStore(
            api.client, engine, UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        capture.phoneBuffer = SyncStorePhoneAudio(sync)
        capture.startPhone()
        engine.pcm.send(ByteArray(3200))
        capture.stop()
        assertEquals(3200, sockets.single().audio.sumOf { it.size })
        val kept = sync.recordings.single()
        assertTrue(kept.isKept)
        assertEquals(10, kept.frames)
        sync.uploadPending()
        assertTrue(uploads.isEmpty())
    }

    @Test
    fun onDeviceModeTranscribesOnThePhoneAndSuggestsTheTranscript() = runTest(UnconfinedTestDispatcher()) {
        val sockets = mutableListOf<FakeChannel>()
        val options = mutableListOf<ListenSocket.Options>()
        val api = api(sockets, options)
        val preferences = freshPreferences()
        val engine = Engine(recognizer = true)
        val capture = CaptureStore(
            api.client, engine, UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        assertTrue(capture.canTranscribeOnDevice)
        capture.transcribesOnDevice = true
        assertTrue(preferences.bool(NativeKey.OnDeviceTranscription, false))

        capture.startPhone()
        assertTrue(options.single().clientTranscription)
        assertEquals(Transcriber.Phone, capture.transcriber)
        val line = LiveSegment("ondevice-1", "Hello", "SPEAKER_00", 0, true, 0.0, 1.0)
        engine.transcript.send(TranscriptUpdate(line, isFinal = false))
        assertEquals("Hello", capture.partial?.text)
        engine.transcript.send(TranscriptUpdate(line.copy(text = "Hello there"), isFinal = true))
        assertNull(capture.partial)
        assertEquals(listOf("Hello there"), capture.segments.map { it.text })
        val (suggested, provider) = sockets.single().suggested.single()
        assertEquals("Hello there", suggested.single().text)
        assertEquals("apple_on_device", provider)
        // The server's own segments are not the transcript in this mode.
        sockets.single().incoming.trySend(ListenEvent.Segments(listOf(LiveSegment("s9", "server", "SPEAKER_00", 0, true, 0.0, 1.0))))
        assertEquals(listOf("Hello there"), capture.segments.map { it.text })
        capture.stop()
    }

    @Test
    fun withoutARecognizerTheSwitchIsUnavailableAndTheServerTranscribes() = runTest(UnconfinedTestDispatcher()) {
        val options = mutableListOf<ListenSocket.Options>()
        val api = api(mutableListOf(), options)
        val capture = CaptureStore(
            api.client, Engine(recognizer = false), UnavailableDeviceTranscriptionEngine(), freshPreferences(), defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        assertFalse(capture.canTranscribeOnDevice)
        capture.startPhone()
        assertFalse(options.single().clientTranscription)
        assertEquals(Transcriber.Omi, capture.transcriber)
        capture.stop()
    }
}

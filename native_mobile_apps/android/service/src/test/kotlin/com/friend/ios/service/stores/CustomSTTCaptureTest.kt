package com.friend.ios.service.stores

import com.friend.ios.network.APIError
import com.friend.ios.network.customstt.CustomSTTConfig
import com.friend.ios.network.customstt.CustomSTTProvider
import com.friend.ios.network.customstt.CustomSTTSocket
import com.friend.ios.network.customstt.CustomSTTTransport
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.LiveTranscriptionChannel
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.persistence.Preferences.NativeKey
import com.friend.ios.service.PhoneCaptureEngine
import com.friend.ios.service.PhoneCaptureStreams
import com.friend.ios.service.UnavailableDeviceTranscriptionEngine
import com.friend.ios.service.customstt.CustomSTTSettings
import com.friend.ios.service.customstt.CustomTranscriber
import com.friend.ios.service.customstt.MemorySecretStore
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import okhttp3.Request
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of the custom STT cases of `CaptureStoreTests` and `CustomSTTSettings`: your own provider transcribes the phone mic. */
@OptIn(ExperimentalCoroutinesApi::class)
class CustomSTTCaptureTest {
    private class FakeChannel : LiveTranscriptionChannel {
        override val events: Flow<ListenEvent> = Channel<ListenEvent>(Channel.UNLIMITED).receiveAsFlow()
        val suggested = mutableListOf<Pair<List<LiveSegment>, String>>()
        override fun send(audio: ByteArray) = Unit
        override fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String) {
            suggested += segments to provider
        }
        override fun close(reason: String) = Unit
        override fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) = Unit
    }

    private class Engine : PhoneCaptureEngine {
        var pcm = Channel<ByteArray>(Channel.UNLIMITED)
        override val supportsOnDevice: Boolean get() = false
        override suspend fun start(transcribeOnDevice: Boolean): PhoneCaptureStreams {
            if (transcribeOnDevice) throw com.friend.ios.service.CaptureFailure.SpeechUnavailable
            pcm = Channel(Channel.UNLIMITED)
            return PhoneCaptureStreams(pcm.receiveAsFlow(), Channel<Float>().receiveAsFlow(), null)
        }
        override fun stop() = Unit
    }

    /** Answers every upload with one segment; records what was sent. */
    private class Transport(var status: Int = 200) : CustomSTTTransport {
        val requests = mutableListOf<Request>()
        override suspend fun send(request: Request): Pair<String, Int> {
            requests += request
            return """{"segments":[{"start":0.5,"end":1.0,"text":"Hallo"}]}""" to status
        }
        override fun openSocket(request: Request): CustomSTTSocket = error("not live")
    }

    private fun TestScope.scope() = CoroutineScope(UnconfinedTestDispatcher(testScheduler) + backgroundScope.coroutineContext[kotlinx.coroutines.Job]!!)

    @Test
    fun aCompleteProviderTranscribesThePhoneAndSuggestsTheTranscript() = runTest(UnconfinedTestDispatcher()) {
        val sockets = mutableListOf<FakeChannel>()
        val options = mutableListOf<ListenSocket.Options>()
        val api = fakeAPI {
            "openListenSocket" does { args ->
                options += args[1] as ListenSocket.Options
                FakeChannel().also { sockets += it }
            }
            "finalizeInProgressConversation" returns "c1"
            "subscription" throws APIError.Transport("offline")
        }
        val preferences = freshPreferences()
        val settings = CustomSTTSettings(preferences, MemorySecretStore())
        settings.save(CustomSTTConfig(CustomSTTProvider.OpenAI, apiKey = " sk-1 ", language = "de"))
        val transport = Transport()
        val engine = Engine()
        val capture = CaptureStore(
            api.client, engine, UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        capture.customSTT = settings
        capture.makeCustomTranscriber = { config -> CustomTranscriber(config, transport, scope()) }

        capture.startPhone()
        assertTrue(options.single().clientTranscription)
        assertEquals(Transcriber.Custom("openai"), capture.transcriber)
        engine.pcm.send(ByteArray(32_000))
        advanceTimeBy(3_100)
        runCurrent()
        assertEquals("Bearer sk-1", transport.requests.single().header("Authorization"))
        assertEquals(listOf("Hallo"), capture.segments.map { it.text })
        val (suggested, provider) = sockets.single().suggested.single()
        assertEquals("Hallo", suggested.single().text)
        assertEquals("openai", provider)
        capture.stop()
    }

    /** A decoder that answers each frame with its bytes doubled, at once (the app's runs on a worker). */
    private class FakeDecoder(private val onPCM: (ByteArray) -> Unit) : com.friend.ios.service.OpusPCM16Decoding {
        val frames = mutableListOf<ByteArray>()
        var released = false
        override fun decode(frame: ByteArray) {
            frames += frame
            onPCM(frame + frame)
        }
        override fun release() {
            released = true
        }
    }

    /** A provider that records the PCM it was fed. */
    private class RecordingTranscriber : com.friend.ios.service.customstt.CustomTranscribing {
        override val providerName = "openai"
        val fed = mutableListOf<ByteArray>()
        var stopped = false
        override fun start(): Flow<LiveSegment> = Channel<LiveSegment>().receiveAsFlow()
        override fun feed(pcm16: ByteArray) {
            fed += pcm16
        }
        override fun stop() {
            stopped = true
        }
    }

    /** iOS `opusToPCM`: the user's own provider hears an Omi recording, decoded on the phone. */
    @Test
    fun theProviderTranscribesTheOmiThroughThePhonesDecoder() = runTest(UnconfinedTestDispatcher()) {
        val options = mutableListOf<ListenSocket.Options>()
        val sockets = mutableListOf<FakeChannel>()
        val api = fakeAPI {
            "openListenSocket" does { args ->
                options += args[1] as ListenSocket.Options
                FakeChannel().also { sockets += it }
            }
            "finalizeInProgressConversation" returns "c1"
            "subscription" throws APIError.Transport("offline")
        }
        val preferences = freshPreferences()
        val settings = CustomSTTSettings(preferences, MemorySecretStore())
        settings.save(CustomSTTConfig(CustomSTTProvider.OpenAI, apiKey = "sk-1"))
        val capture = CaptureStore(
            api.client, Engine(), UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        val transcriber = RecordingTranscriber()
        var decoder: FakeDecoder? = null
        capture.customSTT = settings
        capture.makeCustomTranscriber = { transcriber }
        capture.makeOpusDecoder = { onPCM -> FakeDecoder(onPCM).also { decoder = it } }

        capture.startDevice(ListenSocket.Options.Codec.OpusFS320)
        assertTrue(options.single().clientTranscription)
        assertEquals(Transcriber.Custom("openai"), capture.transcriber)
        capture.ingestDeviceAudio(byteArrayOf(1, 2))
        assertEquals(listOf(listOf<Byte>(1, 2, 1, 2)), transcriber.fed.map { it.toList() })
        capture.stop()
        assertTrue(transcriber.stopped)
        assertTrue(decoder!!.released)
    }

    /** No decoder on this phone: an Omi recording stays with Omi's transcription. */
    @Test
    fun withoutADecoderTheOmiStaysWithOmisTranscription() = runTest(UnconfinedTestDispatcher()) {
        val options = mutableListOf<ListenSocket.Options>()
        val api = fakeAPI {
            "openListenSocket" does { args ->
                options += args[1] as ListenSocket.Options
                FakeChannel()
            }
            "subscription" throws APIError.Transport("offline")
        }
        val preferences = freshPreferences()
        val settings = CustomSTTSettings(preferences, MemorySecretStore())
        settings.save(CustomSTTConfig(CustomSTTProvider.OpenAI, apiKey = "sk-1"))
        val capture = CaptureStore(
            api.client, Engine(), UnavailableDeviceTranscriptionEngine(), preferences, defaultOnDevice = false,
            userID = { "alice" }, scope = scope(),
        )
        capture.customSTT = settings
        capture.makeCustomTranscriber = { RecordingTranscriber() }
        capture.makeOpusDecoder = { null }
        capture.startDevice(ListenSocket.Options.Codec.OpusFS320)
        assertFalse(options.single().clientTranscription)
        assertEquals(Transcriber.Omi, capture.transcriber)
    }

    @Test
    fun theKeyStaysOutOfPreferencesAndAFlutterKeyMoves() {
        val preferences = freshPreferences()
        val secrets = MemorySecretStore()
        preferences.set(Key.CustomSttConfig, """{"provider":"deepgramLive","api_key":"dg-key","language":"multi"}""")
        val settings = CustomSTTSettings(preferences, secrets)
        assertEquals(CustomSTTProvider.DeepgramLive, settings.config?.provider)
        assertEquals("dg-key", settings.config?.apiKey)
        assertEquals("dg-key", secrets.secret("customStt.apiKey"))
        assertFalse(preferences.string(Key.CustomSttConfig)!!.contains("dg-key"))
        assertEquals(
            """{"language":"multi","provider":"deepgramLive","request_type":"streaming","send_raw_audio_to_omi":true}""",
            preferences.string(Key.CustomSttConfig),
        )
        settings.save(null)
        assertNull(settings.config)
        assertNull(secrets.secret("customStt.apiKey"))
    }

    @Test
    fun flutterOnDeviceWhisperTurnsOnThePhonesRecognizer() {
        val preferences = freshPreferences()
        preferences.set(Key.CustomSttConfig, """{"provider":"onDeviceWhisper"}""")
        val settings = CustomSTTSettings(preferences, MemorySecretStore())
        assertNull(settings.config)
        assertTrue(preferences.bool(NativeKey.OnDeviceTranscription, false))
    }
}

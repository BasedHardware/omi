package com.friend.ios.network.endpoints

import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.HttpCore
import com.friend.ios.network.listen.ListenEvent
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveSegment
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okio.ByteString
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.URI
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

class ListenSocketTest {
    private lateinit var server: MockWebServer
    private lateinit var api: ListenAPI

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val configuration = AppConfiguration(AppConfiguration.Profile.LocalDev, URI(server.url("/").toString()), null, "1.0", "1")
        api = ListenEndpoints(HttpCore(configuration, { "token" }))
    }

    @After
    fun tearDown() = server.shutdown()

    /** The server side of one socket: what the app sent, and the server's handle to answer. */
    private class ServerSide : WebSocketListener() {
        val texts = LinkedBlockingQueue<String>()
        val binaries = LinkedBlockingQueue<ByteString>()
        val opened = LinkedBlockingQueue<WebSocket>()

        override fun onOpen(webSocket: WebSocket, response: Response) {
            opened.put(webSocket)
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            texts.put(text)
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            binaries.put(bytes)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, null)
        }
    }

    private fun <T> LinkedBlockingQueue<T>.next(): T = poll(5, TimeUnit.SECONDS) ?: error("timed out")

    @Test
    fun opensWithTheIOSQueryAndBearer() = runBlocking {
        val side = ServerSide()
        server.enqueue(MockResponse().withWebSocketUpgrade(side))
        val options = ListenSocket.Options(
            codec = ListenSocket.Options.Codec.Pcm16, source = ListenSocket.Options.Source.Phone, language = "multi",
            conversationTimeout = 300, clientConversationID = "rec-1", sttService = "parakeet", vadGate = true,
            geolocationHeader = """{"latitude":1}""",
        )
        val channel = api.openListenSocket("alice", options)
        side.opened.next()
        val request = server.takeRequest()
        val url = request.requestUrl!!
        assertEquals("/v4/listen", url.encodedPath)
        assertEquals("multi", url.queryParameter("language"))
        assertEquals("16000", url.queryParameter("sample_rate"))
        assertEquals("pcm16", url.queryParameter("codec"))
        assertEquals("alice", url.queryParameter("uid"))
        assertEquals("true", url.queryParameter("include_speech_profile"))
        assertEquals("300", url.queryParameter("conversation_timeout"))
        assertEquals("phone", url.queryParameter("source"))
        assertEquals("rec-1", url.queryParameter("client_conversation_id"))
        assertEquals("enabled", url.queryParameter("speaker_auto_assign"))
        assertEquals("true", url.queryParameter("create_speakers"))
        assertEquals("parakeet", url.queryParameter("stt_service"))
        assertEquals("enabled", url.queryParameter("vad_gate"))
        assertNull(url.queryParameter("custom_stt"))
        assertEquals("Bearer token", request.getHeader("Authorization"))
        assertEquals("""{"latitude":1}""", request.getHeader("X-Omi-Conversation-Geolocation"))
        assertEquals("""{"type":"client_state","foreground":true,"transcript_visible":true}""", side.texts.next())
        channel.close("user_stop")
    }

    @Test
    fun streamsAudioAnswersPingsParsesEventsAndClosesWithAReason() = runBlocking {
        val side = ServerSide()
        server.enqueue(MockResponse().withWebSocketUpgrade(side))
        val channel = api.openListenSocket("alice", ListenSocket.Options(ListenSocket.Options.Codec.Pcm16, source = ListenSocket.Options.Source.Phone))
        val serverSocket = side.opened.next()
        side.texts.next() // client_state

        channel.send(ByteArray(3200) { 1 })
        channel.send(ByteArray(2)) // too short: dropped, as on iOS
        assertEquals(3200, side.binaries.next().size)

        serverSocket.send("ping")
        assertEquals("pong", side.texts.next())

        serverSocket.send("""{"type":"conversation_session","conversation_id":"c1"}""")
        serverSocket.send("""[{"id":"s1","text":"Hello there","speaker":"SPEAKER_00","speaker_id":0,"is_user":true,"start":0.5,"end":1.5}]""")
        serverSocket.send("""{"type":"service_status","status":"ready"}""")
        val events = withTimeout(5000) { channel.events.take(3).toList() }
        assertEquals(ListenEvent.ConversationStarted("c1"), events[0])
        assertEquals(
            ListenEvent.Segments(listOf(LiveSegment("s1", "Hello there", "SPEAKER_00", 0, true, 0.5, 1.5))),
            events[1],
        )
        assertEquals(ListenEvent.Status("ready"), events[2])

        channel.sendSpeakerAssigned(1, "p1", "Anna", listOf("s1"))
        assertEquals("""{"type":"speaker_assigned","person_id":"p1","person_name":"Anna","segment_ids":["s1"],"speaker_id":1}""", side.texts.next())

        channel.close("user_stop")
        assertEquals("""{"type":"finalization_reason","reason":"user_stop"}""", side.texts.next())
    }

    @Test
    fun aDroppedSocketReportsDisconnected() = runBlocking {
        val side = ServerSide()
        server.enqueue(MockResponse().withWebSocketUpgrade(side))
        val channel = api.openListenSocket("alice", ListenSocket.Options(ListenSocket.Options.Codec.Pcm16, source = ListenSocket.Options.Source.Phone))
        side.opened.next().close(1001, "going away")
        val event = withTimeout(5000) { channel.events.first() }
        assertTrue(event.toString(), (event as ListenEvent.Status).status.startsWith("disconnected"))
    }

    @Test
    fun parsesEveryEventKind() {
        assertNull(ListenEvent.parse("ping"))
        assertEquals(ListenEvent.Status("stt_failed"), ListenEvent.parse("""{"type":"service_status","status":"stt_failed"}"""))
        assertEquals(ListenEvent.FreemiumThreshold(0, true), ListenEvent.parse("""{"type":"service_status","status":"freemium_threshold_reached","action":"setup_on_device_stt"}"""))
        assertEquals(ListenEvent.FreemiumThreshold(120, false), ListenEvent.parse("""{"type":"freemium_threshold_reached","remaining_seconds":120}"""))
        assertEquals(ListenEvent.ProcessingStarted("c1"), ListenEvent.parse("""{"type":"memory_processing_started","conversation_id":"c1"}"""))
        assertEquals(ListenEvent.ConversationCreated("c2"), ListenEvent.parse("""{"type":"memory_created","memory":{"id":"c2"}}"""))
        assertEquals(ListenEvent.SegmentsDeleted(listOf("a", "b")), ListenEvent.parse("""{"type":"segments_deleted","segment_ids":["a","b"]}"""))
        val translated = ListenEvent.parse("""{"type":"translating","segments":[{"id":"s1","text":"Hola","translations":[{"lang":"en","text":"Hello"}]}]}""")
        assertEquals(listOf(LiveSegment.Translation("en", "Hello")), (translated as ListenEvent.Translated).segments.single().translations)
        assertEquals(ListenEvent.Other("photo_processing"), ListenEvent.parse("""{"type":"photo_processing"}"""))
        // Missing fields: the id falls back, end follows start, an empty person is none.
        val segment = (ListenEvent.parse("""[{"text":"x","start":2,"person_id":""}]""") as ListenEvent.Segments).segments.single()
        assertEquals(2.0, segment.end, 0.0)
        assertNull(segment.personID)
        assertEquals(false, segment.isUser)
    }

    @Test
    fun finalizesTheInProgressConversation() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"conversation":{"id":"c9"}}"""))
        assertEquals("c9", api.finalizeInProgressConversation())
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/v1/conversations", request.path)
        assertEquals("{}", request.body.readUtf8())
        // 404: the server already finalized it on its silence timeout.
        server.enqueue(MockResponse().setResponseCode(404))
        assertNull(api.finalizeInProgressConversation())
        server.enqueue(MockResponse().setBody("""[{"id":"c3","status":"in_progress"}]"""))
        assertEquals("c3", api.inProgressConversationID())
        server.takeRequest()
        assertEquals("/v1/conversations?statuses=in_progress&limit=1", server.takeRequest().path)
        server.enqueue(MockResponse().setBody("{}"))
        api.finalizeConversation("c3")
        assertEquals("/v1/conversations/c3/finalize", server.takeRequest().path)
    }
}

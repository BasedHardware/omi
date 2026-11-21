package com.friend.ios.network.endpoints

import com.friend.ios.core.AppConfiguration
import com.friend.ios.core.models.ChatChart
import com.friend.ios.core.models.ChatEvidence
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.net.URI
import java.util.Base64

class ChatEndpointsTest {
    private lateinit var server: MockWebServer
    private lateinit var chat: ChatAPI

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val configuration = AppConfiguration(
            AppConfiguration.Profile.LocalDev, URI(server.url("/").toString()), null, "1.0", "1",
        )
        chat = ChatEndpoints(HttpCore(configuration, { "token" }))
    }

    @After
    fun tearDown() = server.shutdown()

    private val doneJSON = """
        {"id":"m1","text":"Line one\nLine two","sender":"ai","created_at":"2026-10-08T10:00:00.123456",
         "memories":[{"id":"c1","created_at":"2026-10-08T09:00:00Z","structured":{"title":"Q4 roadmap","emoji":"🗺️"}}],
         "rating":1,"content_blocks":[{"type":"followUp","text":"What about Anna?"}],
         "chart_data":{"chart_type":"line","title":"Steps","datasets":[{"label":"Mon","data_points":[{"label":"a","value":3}]}]},
         "files":[{"id":"f1","name":"r.jpg","mime_type":"image/jpeg","thumbnail":"https://x/t.jpg"}],
         "evidence":{"references":[{"id":"e1","kind":"conversation_segment","state":"available","conversation_id":"c1","start_ms":754000}]}}
    """.trimIndent()

    @Test
    fun parsesEveryFrameKind() {
        assertEquals(ChatStreamEvent.Delta("a\nb"), ChatStreamEvent.parse("data: a__CRLF__b"))
        assertEquals(ChatStreamEvent.Step("Searching the web"), ChatStreamEvent.parse("think: Searching the web|app_id:abc"))
        assertEquals(ChatStreamEvent.MemorySaved, ChatStreamEvent.parse("memory: x"))
        assertEquals(ChatStreamEvent.Failed("boom"), ChatStreamEvent.parse("error: {\"message\":\"boom\"}"))
        assertEquals(ChatStreamEvent.Failed("plain"), ChatStreamEvent.parse("error: plain"))
        assertEquals("quota_exceeded", ChatStreamEvent.errorCode("error: {\"error\":\"quota_exceeded\",\"message\":\"x\"}"))
        assertNull(ChatStreamEvent.parse("unknown: x"))
        val encoded = Base64.getEncoder().encodeToString(doneJSON.toByteArray())
        val done = ChatStreamEvent.parse("done: $encoded") as ChatStreamEvent.Done
        val message = done.message
        assertEquals("m1", message.id)
        assertEquals("m1", message.serverID)
        assertEquals(ChatMessage.Sender.Omi, message.sender)
        assertEquals("Line one\nLine two", message.text)
        assertEquals(1, message.rating)
        assertEquals("What about Anna?", message.followUp)
        assertEquals(ChatChart.Kind.Line, message.chart?.kind)
        assertEquals("Q4 roadmap", message.references.single().title)
        assertEquals("https://x/t.jpg", message.files.single().thumbnailURL)
        assertEquals(ChatEvidence.Kind.ConversationSegment, message.evidence.single().kind)
        assertEquals(754000, message.evidence.single().startMs)
        assertTrue(ChatStreamEvent.isServiceFailure("  The response took too long. Please try again. "))
    }

    @Test
    fun streamsLinesAsEventsAndSendsTheContract() = runTest {
        val encoded = Base64.getEncoder().encodeToString(doneJSON.toByteArray())
        server.enqueue(
            MockResponse().setBody(
                "think: Searching|app_id:x\n\n: keep-alive\ndata: Hel\ndata: lo__CRLF__there\nerror: {\"error\":\"timeout\"}\ndone: $encoded\n",
            ),
        )
        val events = chat.sendChatMessage("Hi", listOf("f1"), null, "s1", emptyList()).toList()
        assertEquals(
            listOf(ChatStreamEvent.Step("Searching"), ChatStreamEvent.Delta("Hel"), ChatStreamEvent.Delta("lo\nthere"), ChatStreamEvent.Failed("timeout")),
            events.dropLast(1),
        )
        assertTrue(events.last() is ChatStreamEvent.Done)
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/v2/messages?chat_session_id=s1", request.path)
        assertEquals("1", request.getHeader("X-Omi-Chat-Failure-Protocol"))
        assertEquals("Bearer token", request.getHeader("Authorization"))
        val body = request.body.readUtf8()
        assertTrue(body, body.contains("\"text\":\"Hi\"") && body.contains("\"file_ids\":[\"f1\"]") && body.contains("time_zone"))
    }

    @Test
    fun httpErrorsThrowBeforeAnyEvent() = runTest {
        server.enqueue(MockResponse().setResponseCode(402))
        try {
            chat.sendChatMessage("Hi", emptyList(), null, null, emptyList()).toList()
            fail("expected 402")
        } catch (e: APIError.Http) {
            assertEquals(402, e.status)
        }
    }

    @Test
    fun historyIsReturnedOldestFirstAndSessionsDecode() = runTest {
        server.enqueue(MockResponse().setBody("""[{"id":"b","text":"new","sender":"ai"},{"id":"a","text":"old","sender":"human"}]"""))
        val history = chat.chatHistory(50, 0, "s1")
        assertEquals(listOf("a", "b"), history.map { it.id })
        assertEquals(ChatMessage.Sender.User, history.first().sender)
        assertEquals("/v2/messages?limit=50&offset=0&chat_session_id=s1", server.takeRequest().path)

        server.enqueue(MockResponse().setBody("""[{"id":"s1","title":"Omi"},{"id":"s2"}]"""))
        assertEquals(listOf("s1" to "Omi", "s2" to ""), chat.chatSessions())

        server.enqueue(MockResponse().setBody("""{"id":"new"}"""))
        assertEquals("new", chat.createChatSession("Omi"))
    }
}

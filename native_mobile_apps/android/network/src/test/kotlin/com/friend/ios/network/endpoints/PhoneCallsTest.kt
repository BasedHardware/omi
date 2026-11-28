package com.friend.ios.network.endpoints

import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.network.listen.PhoneCallSocket
import com.friend.ios.network.listen.PhoneCallSocketEvent
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
import okio.ByteString.Companion.toByteString
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.URI
import java.time.Instant
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/** Port of `PhoneCallsTests.swift` (contract) and the parsing half of `PhoneCallTests.swift`. */
class PhoneCallsTest {
    private lateinit var server: MockWebServer
    private lateinit var api: PhoneCallsAPI

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val configuration = AppConfiguration(AppConfiguration.Profile.LocalDev, URI(server.url("/").toString()), null, "1.0", "1")
        api = PhoneCallsEndpoints(HttpCore(configuration, { "token" }))
    }

    @After
    fun tearDown() = server.shutdown()

    /** Flutter `buildPhoneCallWebSocketUrl`: two channels, 48 kHz PCM, the call id the Twilio leg carries. */
    @Test
    fun callSocketURLMatchesFlutter() {
        val url = PhoneCallSocket.url(URI("https://api.omi.me/"), "u1", "1759800000000", "multi")
        assertEquals("wss", url.scheme)
        assertEquals("/v4/listen", url.path)
        val items = url.query.split("&").associate { it.substringBefore("=") to it.substringAfter("=") }
        assertEquals(
            mapOf(
                "source" to "phone_call", "call_id" to "1759800000000", "uid" to "u1", "sample_rate" to "48000",
                "codec" to "pcm", "language" to "multi", "channels" to "2",
            ),
            items,
        )
        assertEquals("ws", PhoneCallSocket.url(URI("http://127.0.0.1:8000/"), "u", "c", "en").scheme)
    }

    /** `verified_at` is Python `isoformat()` with microseconds and an offset. */
    @Test
    fun verifiedDatesParse() {
        val plain = parsePhoneDate("2026-10-01T10:00:00+00:00")
        assertEquals(Instant.ofEpochSecond(1_790_848_800), plain)
        val micro = parsePhoneDate("2026-10-01T10:00:00.123456+00:00")!!
        assertTrue(kotlin.math.abs(micro.epochSecond - plain!!.epochSecond) < 1)
        assertNull(parsePhoneDate("yesterday"))
    }

    @Test
    fun socketFramesParseLikeFlutter() {
        assertNull(PhoneCallSocketEvent.parse("ping"))
        assertEquals(
            PhoneCallSocketEvent.Segments(listOf(LiveSegment("s1", "Hi", null, null, true, 0.5, 1.0))),
            PhoneCallSocketEvent.parse("""[{"id":"s1","text":"Hi","is_user":true,"start":0.5,"end":1.0}]"""),
        )
        val translating = """{"type":"translating","segments":[{"id":"s1","translations":[{"lang":"en","text":"Hello"}]}]}"""
        assertEquals(PhoneCallSocketEvent.Translations(mapOf("s1" to listOf("Hello"))), PhoneCallSocketEvent.parse(translating))
        assertEquals(PhoneCallSocketEvent.Status("ready"), PhoneCallSocketEvent.parse("""{"type":"service_status","status":"ready"}"""))
    }

    @Test
    fun errorBodiesCarryTheReason() {
        assertEquals(
            PhoneCallErrorDetail.Message("Phone number already verified"),
            PhoneCallErrorDetail.from("""{"detail":"Phone number already verified"}"""),
        )
        assertEquals(
            PhoneCallErrorDetail.QuotaExceeded(3),
            PhoneCallErrorDetail.from("""{"detail":{"error":"phone_call_quota_exceeded","monthly_limit":3}}"""),
        )
        assertNull(PhoneCallErrorDetail.from("Internal Server Error"))
    }

    @Test
    fun numbersTokenAndQuotaDecode() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"numbers":[{"id":"n1","phone_number":"+15551112222","verified_at":"2026-10-01T10:00:00.5+00:00","is_primary":true},{"id":"bad"}]}"""))
        val numbers = api.verifiedPhoneNumbers()
        assertEquals(listOf("+15551112222"), numbers.map { it.phoneNumber })
        assertTrue(numbers[0].isPrimary)
        assertEquals("/v1/phone/numbers", server.takeRequest().path)

        server.enqueue(MockResponse().setBody("""{"access_token":"tw","ttl":600,"identity":"u1"}"""))
        assertEquals(PhoneCallToken("tw", 600, "u1"), api.phoneCallToken())
        assertEquals("POST", server.takeRequest().method)

        server.enqueue(MockResponse().setBody("""{"phone_call_quota":{"has_access":true,"is_paid":false,"monthly_limit":3,"monthly_used":1,"remaining":2,"max_duration_seconds":600}}"""))
        assertEquals(PhoneCallQuota(true, false, 3, 1, 2, 600), api.phoneCallQuota())

        server.enqueue(MockResponse().setBody("""{"phone_number":"+4915112345678","validation_code":"","status":"pending"}"""))
        assertEquals(PhoneVerification("+4915112345678", null, "pending"), api.startPhoneVerification("+4915112345678"))
        assertEquals("""{"phone_number":"+4915112345678"}""", server.let { it.takeRequest(); it.takeRequest() }.body.readUtf8())

        server.enqueue(MockResponse().setResponseCode(402).setBody("""{"detail":{"error":"phone_call_quota_exceeded"}}"""))
        val error = runCatching { api.phoneCallToken() }.exceptionOrNull() as APIError.Http
        assertEquals(PhoneCallErrorDetail.QuotaExceeded(null), PhoneCallErrorDetail.from(error.body))
    }

    private class ServerSide : WebSocketListener() {
        val binaries = LinkedBlockingQueue<ByteString>()
        val opened = LinkedBlockingQueue<WebSocket>()

        override fun onOpen(webSocket: WebSocket, response: Response) {
            opened.put(webSocket)
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
    fun theCallSocketOpensWithTheCallQuerySendsFramesAndReportsADrop() = runBlocking {
        val side = ServerSide()
        server.enqueue(MockResponse().withWebSocketUpgrade(side))
        val channel = api.openPhoneCallSocket("alice", "1759800000000", "de")
        val serverSocket = side.opened.next()
        val request = server.takeRequest()
        val url = request.requestUrl!!
        assertEquals("/v4/listen", url.encodedPath)
        assertEquals("phone_call", url.queryParameter("source"))
        assertEquals("1759800000000", url.queryParameter("call_id"))
        assertEquals("2", url.queryParameter("channels"))
        assertEquals("48000", url.queryParameter("sample_rate"))
        assertEquals("Bearer token", request.getHeader("Authorization"))

        channel.send(byteArrayOf(1, 7, 7))
        channel.send(byteArrayOf(2)) // a channel byte alone: dropped
        assertEquals(byteArrayOf(1, 7, 7).toByteString(), side.binaries.next())

        serverSocket.send("ping")
        serverSocket.send("""[{"id":"s1","text":"Hallo","is_user":false,"start":0,"end":1}]""")
        val events = withTimeout(5000) { channel.events.take(2).toList() }
        assertEquals(PhoneCallSocketEvent.Status("ping"), events[0])
        assertEquals("Hallo", (events[1] as PhoneCallSocketEvent.Segments).segments.single().text)

        serverSocket.close(1001, "going away")
        val closed = withTimeout(5000) { channel.events.first() }
        assertTrue(closed is PhoneCallSocketEvent.Closed)
    }
}

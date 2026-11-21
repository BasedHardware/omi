package com.friend.ios.network.endpoints

import com.friend.ios.core.AppConfiguration
import com.friend.ios.core.models.DeviceContact
import com.friend.ios.core.models.DeviceToolRequest
import com.friend.ios.core.models.DeviceToolResult
import com.friend.ios.network.HttpCore
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.URI
import java.time.Instant
import java.util.Base64

class DeviceToolsEndpointsTest {
    private lateinit var server: MockWebServer
    private lateinit var http: HttpCore

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val configuration = AppConfiguration(AppConfiguration.Profile.LocalDev, URI(server.url("/").toString()), null, "1.0", "1")
        http = HttpCore(configuration, { "token" })
    }

    @After
    fun tearDown() = server.shutdown()

    @Test
    fun toolFrameParsesArguments() {
        val frame = DeviceToolFrame.encode("c1", "propose_message", mapOf("to" to listOf("+49 170", ""), "text" to "Hi", "subject" to ""))
        val event = ChatStreamEvent.parse("tool: $frame") as ChatStreamEvent.DeviceTool
        assertEquals(DeviceToolRequest(id = "c1", toolName = "propose_message", recipients = listOf("+49 170"), text = "Hi"), event.request)
        assertEquals(DeviceToolRequest.Tool.ProposeMessage, event.request.tool)
    }

    @Test
    fun singleRecipientLimitAndPermission() {
        val search = DeviceToolFrame.parse(DeviceToolFrame.encode("c2", "search_contacts", mapOf("query" to " Anna ", "limit" to 500)))!!
        assertEquals("Anna", search.query)
        assertEquals(50, search.limit)
        val message = DeviceToolFrame.parse(DeviceToolFrame.encode("c3", "propose_message", mapOf("to" to "anna@x.de")))!!
        assertEquals(listOf("anna@x.de"), message.recipients)
        val permission = DeviceToolFrame.parse(DeviceToolFrame.encode("c4", "request_permission", mapOf("type" to "contacts")))!!
        assertEquals("contacts", permission.permission)
    }

    @Test
    fun malformedFrameKeepsTheCallID() {
        val noTool = Base64.getEncoder().encodeToString("""{"call_id":"c9"}""".toByteArray())
        assertEquals(DeviceToolRequest(id = "c9", toolName = ""), DeviceToolFrame.parse(noTool))
        assertNull(DeviceToolFrame.parse("not base64 !!"))
        assertNull(DeviceToolFrame.parse(Base64.getEncoder().encodeToString("""{"tool":"x"}""".toByteArray())))
    }

    @Test
    fun resultPayloadCarriesContacts() {
        val anna = DeviceContact("a1", "Anna", listOf(DeviceContact.Handle("mobile", "+49")), emptyList(), "+49")
        val payload = DeviceToolFrame.payload(DeviceToolResult(ok = true, query = "Anna", contacts = listOf(anna)))
        assertEquals("1", payload["count"]!!.jsonPrimitive.content)
        val contact = payload["contacts"]!!.jsonArray.first().jsonObject
        assertEquals("+49", contact["preferred_messaging_handle"]!!.jsonPrimitive.content)
        assertEquals("mobile", contact["phone_numbers"]!!.jsonArray.first().jsonObject["label"]!!.jsonPrimitive.content)
        assertNull(payload["status"])
    }

    @Test
    fun resultIsPostedUnderResult() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        AgentEndpoints(http).sendDeviceToolResult("c1", DeviceToolResult(ok = false, status = "cancelled", reason = "declined"))
        val request = server.takeRequest()
        assertEquals("/v2/messages/device-tool/c1/result", request.path)
        val body = Json.parseToJsonElement(request.body.readUtf8()).jsonObject["result"] as JsonObject
        assertEquals("false", body["ok"]!!.jsonPrimitive.content)
        assertEquals("cancelled", body["status"]!!.jsonPrimitive.content)
    }

    @Test
    fun voiceFileIsLengthPrefixed() {
        val (name, data) = VoiceMessageFile.file(
            listOf(byteArrayOf(0xAA.toByte(), 0xBB.toByte()), byteArrayOf(0xCC.toByte())), "opus_fs320", 16000, 320, Instant.ofEpochSecond(1700),
        )
        assertEquals("audio_omi_opus_fs320_16000_1_fs320_1700.bin", name)
        assertArrayEquals(byteArrayOf(2, 0, 0, 0, 0xAA.toByte(), 0xBB.toByte(), 1, 0, 0, 0, 0xCC.toByte()), data)
    }

    @Test
    fun transcribeAndSynthesize() = runTest {
        server.enqueue(MockResponse().setBody("""{"transcript":" What's next? "}"""))
        server.enqueue(MockResponse().setBody(Buffer().write(byteArrayOf(1, 2, 3))).setHeader("Content-Type", "audio/mpeg"))
        val api = VoiceMessagesEndpoints(http)
        assertEquals("What's next?", api.transcribeVoiceMessage("q.bin", byteArrayOf(1)))
        assertTrue(server.takeRequest().body.readUtf8().contains("name=\"files\"; filename=\"q.bin\""))
        assertArrayEquals(byteArrayOf(1, 2, 3), api.synthesizeSpeech("Hello", "v1"))
        val synth = server.takeRequest()
        assertEquals("/v2/tts/synthesize", synth.path)
        assertEquals("audio/mpeg", synth.getHeader("Accept"))
        assertTrue(synth.body.readUtf8().contains("\"voice_id\":\"v1\""))
    }
}

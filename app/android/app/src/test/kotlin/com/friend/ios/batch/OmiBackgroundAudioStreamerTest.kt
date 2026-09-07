package com.friend.ios.batch

import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.junit.Assert.*
import org.junit.Test

class OmiBackgroundAudioStreamerTest {
    private class Preferences : NativeBlePreferences {
        val values = mutableMapOf<String, Any>(
            "nativeBleStreamingEnabled" to true,
            "nativeBleStreamConfig" to """{"deviceId":"device","serviceUuid":"service","characteristicUuid":"audio","deviceType":"omi"}""",
            "uid" to "account-a", "nativeAuthToken" to "token-a",
        )
        override fun string(key: String, defaultValue: String) = values[key] as? String ?: defaultValue
        override fun boolean(key: String, defaultValue: Boolean) = values[key] as? Boolean ?: defaultValue
        override fun integer(key: String, defaultValue: Int) = values[key] as? Int ?: defaultValue
    }

    private class Socket(private val request: Request, val listener: WebSocketListener) : WebSocket {
        val frames = mutableListOf<ByteString>()
        var closed = false
        var accept = true
        override fun request() = request
        override fun queueSize() = 0L
        override fun send(text: String): Boolean = error("not used")
        override fun send(bytes: ByteString): Boolean { if (accept) frames.add(bytes); return accept }
        override fun close(code: Int, reason: String?): Boolean { closed = true; return true }
        override fun cancel() { closed = true }
        fun open() = listener.onOpen(this, Response.Builder().request(request).protocol(Protocol.HTTP_1_1)
            .code(101).message("Switching Protocols").build())
        fun values() = frames.map { it[0].toInt() }
    }

    private class Harness {
        val prefs = Preferences()
        var foreground = false
        var time = 10_000L
        val sockets = mutableListOf<Socket>()
        val streamer = OmiBackgroundAudioStreamer(prefs,
            { request, listener -> Socket(request, listener).also { sockets.add(it) } },
            { foreground }, { time }, { _, _ -> })
        fun frame(value: Int = 1) = streamer.handleCharacteristic("device", "service", "audio", byteArrayOf(0, 0, 0, value.toByte()))
    }

    @Test fun `unchanged frames reuse parsed config and socket`() {
        val h = Harness()
        val reader = NativeBleStreamSettingsReader(h.prefs)
        assertSame(reader.config(), reader.config())
        h.frame()
        h.sockets.single().open()
        repeat(1000) { h.frame() }
        assertEquals(1, h.sockets.size)
        assertEquals(1001, h.sockets.single().frames.size)
    }

    @Test fun `token refresh uses fresh auth and retains buffered audio`() {
        val h = Harness()
        h.frame(1)
        val original = h.sockets.single()
        h.prefs.values["nativeAuthToken"] = "token-b"
        h.frame(2)
        val refreshed = h.sockets.last()
        assertTrue(original.closed)
        assertEquals("Bearer token-b", refreshed.request().header("Authorization"))
        original.open()
        assertTrue(original.frames.isEmpty())
        refreshed.open()
        assertEquals(listOf(1, 2), refreshed.values())
    }

    @Test fun `account switch clears audio and cached or late transcripts`() {
        OmiBackgroundAudioStreamer.drainCachedTranscriptMessages()
        val h = Harness()
        h.frame(1)
        val original = h.sockets.single()
        original.listener.onMessage(original, "{\"text\":\"old\"}")
        h.prefs.values["uid"] = "account-b"
        h.prefs.values["nativeAuthToken"] = "token-b"
        h.frame(2)
        original.open()
        original.listener.onMessage(original, "{\"text\":\"late\"}")
        h.sockets.last().open()
        assertTrue(original.frames.isEmpty())
        assertEquals(listOf(2), h.sockets.last().values())
        assertTrue(OmiBackgroundAudioStreamer.drainCachedTranscriptMessages().isEmpty())
    }

    @Test fun `custom stt changes fail closed and recovery drops revoked frames`() {
        val h = Harness()
        h.frame(1)
        val original = h.sockets.single()
        h.prefs.values["customSttConfig"] = """{"provider":"deepgram","send_raw_audio_to_omi":false}"""
        h.frame(2)
        assertTrue(original.closed)
        h.prefs.values["customSttConfig"] = "malformed"
        h.frame(3)
        assertEquals(1, h.sockets.size)
        h.prefs.values.remove("customSttConfig")
        h.frame(4)
        h.sockets.last().open()
        assertEquals(listOf(4), h.sockets.last().values())
    }

    @Test fun `missing credentials stop forwarding and legacy auth still works`() {
        for (key in listOf("uid", "nativeAuthToken")) {
            val h = Harness()
            h.frame()
            h.prefs.values.remove(key)
            h.frame()
            assertTrue(h.sockets.single().closed)
            h.prefs.values[key] = "replacement"
            h.frame()
            assertEquals(2, h.sockets.size)
        }
        val h = Harness()
        h.prefs.values.remove("nativeAuthToken")
        h.prefs.values["authToken"] = "legacy-token"
        h.frame()
        assertEquals("Bearer legacy-token", h.sockets.single().request().header("Authorization"))
    }

    @Test fun `foreground gate and settings changes apply before next send`() {
        val h = Harness()
        h.frame()
        h.foreground = true
        h.prefs.values["nativeBleForegroundReady"] = true
        h.frame()
        assertTrue(h.sockets.single().closed)
        h.foreground = false
        h.prefs.values.putAll(mapOf("hasSetPrimaryLanguage" to true, "userPrimaryLanguage" to "fr",
            "vadGateEnabled" to true, "conversationSilenceDuration" to 45,
            "transcriptionModel3" to "deepgram", "deviceIdHash" to "hash-b"))
        h.frame()
        val request = h.sockets.last().request()
        assertEquals("fr", request.url.queryParameter("language"))
        assertEquals("enabled", request.url.queryParameter("vad_gate"))
        assertEquals("45", request.url.queryParameter("conversation_timeout"))
        assertEquals("deepgram", request.url.queryParameter("stt_service"))
        assertEquals("hash-b", request.header("X-Device-Id-Hash"))
        h.prefs.values["nativeBleStreamConfig"] = "broken"
        h.frame()
        assertTrue(h.sockets.last().closed)
    }

    @Test fun `failure backoff and failed drain retain unsent audio`() {
        val h = Harness()
        h.frame(1)
        val original = h.sockets.single()
        original.listener.onFailure(original, IllegalStateException("offline"), null)
        h.time += 1000
        h.frame(2)
        assertEquals(1, h.sockets.size)
        h.time += 2000
        h.frame(3)
        val retry = h.sockets.last()
        retry.accept = false
        retry.open()
        assertTrue(retry.frames.isEmpty())
        retry.listener.onFailure(retry, IllegalStateException("offline again"), null)
        h.time += 3000
        h.frame(4)
        h.sockets.last().open()
        assertEquals(listOf(1, 2, 3, 4), h.sockets.last().values())
    }
    @Test fun `geolocation metadata refresh preserves buffered frames`() {
        val h = Harness()
        h.frame(1)
        val raw = h.prefs.values["nativeBleStreamConfig"] as String
        h.prefs.values["nativeBleStreamConfig"] = raw.dropLast(1) + ",\"geolocation\":{\"latitude\":1,\"longitude\":2}}"
        h.frame(2)
        assertEquals(2, h.sockets.size)
        h.sockets.last().open()
        assertEquals(listOf(1, 2), h.sockets.last().values())
    }

    @Test fun `policy revoked before onOpen cannot drain queued audio`() {
        val h = Harness()
        h.frame()
        h.prefs.values["nativeBleStreamingEnabled"] = false
        h.sockets.single().open()
        assertTrue(h.sockets.single().closed)
        assertTrue(h.sockets.single().frames.isEmpty())
    }

    @Test fun `auth refreshed before onOpen reconnects and preserves queue`() {
        val h = Harness()
        h.frame(1)
        h.prefs.values["nativeAuthToken"] = "token-b"
        h.sockets.single().open()
        assertEquals(2, h.sockets.size)
        h.sockets.last().open()
        assertEquals(listOf(1), h.sockets.last().values())
    }

    @Test fun `disabling streaming preserves already received same account transcripts`() {
        OmiBackgroundAudioStreamer.drainCachedTranscriptMessages()
        val h = Harness()
        h.frame()
        val socket = h.sockets.single()
        socket.listener.onMessage(socket, "{\"text\":\"captured\"}")
        h.prefs.values["nativeBleStreamingEnabled"] = false
        h.frame()
        assertEquals(listOf("{\"text\":\"captured\"}"), OmiBackgroundAudioStreamer.drainCachedTranscriptMessages())
    }

}

package com.friend.ios.batch

import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class OmiBackgroundAudioStreamerTest {
    private class Preferences : NativeBlePreferences {
        val values = ConcurrentHashMap<String, Any>(mapOf(
            "nativeBleStreamingEnabled" to true,
            "nativeBleStreamConfig" to """{"deviceId":"device","serviceUuid":"service","characteristicUuid":"audio","deviceType":"omi"}""",
            "uid" to "account-a", "nativeAuthToken" to "token-a",
        ))
        @Volatile var afterBooleanRead: ((String) -> Unit)? = null
        override fun string(key: String, defaultValue: String) = values[key] as? String ?: defaultValue
        override fun boolean(key: String, defaultValue: Boolean): Boolean {
            val result = values[key] as? Boolean ?: defaultValue
            afterBooleanRead?.invoke(key)
            return result
        }
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
        val stateLock = Any()
        var foreground = false
        var time = 10_000L
        val sockets = mutableListOf<Socket>()
        val streamer = OmiBackgroundAudioStreamer(prefs,
            { request, listener -> Socket(request, listener).also { sockets.add(it) } },
            { foreground }, { time }, { _, _ -> }, stateLock)
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

    @Test fun `inactive gates never wait for streamer state lock`() {
        for (foreground in listOf(false, true)) {
            val h = Harness()
            h.foreground = foreground
            h.prefs.values["nativeBleForegroundReady"] = foreground
            h.prefs.values["nativeBleStreamingEnabled"] = foreground
            h.streamer.stop("prime")
            val executor = Executors.newSingleThreadExecutor()
            try {
                synchronized(h.stateLock) {
                    executor.submit { repeat(1000) { h.frame() } }.get(5, TimeUnit.SECONDS)
                }
                assertTrue(h.sockets.isEmpty())
            } finally { executor.shutdownNow() }
        }
    }

    @Test fun `activation rechecks gates after waiting for state lock`() {
        val h = Harness()
        val read = CountDownLatch(1)
        h.prefs.afterBooleanRead = { key ->
            if (key == "nativeBleStreamingEnabled") {
                h.prefs.afterBooleanRead = null
                read.countDown()
            }
        }
        val executor = Executors.newSingleThreadExecutor()
        try {
            val future = synchronized(h.stateLock) {
                val pending = executor.submit { h.frame() }
                assertTrue(read.await(5, TimeUnit.SECONDS))
                h.prefs.values["nativeBleStreamingEnabled"] = false
                h.frame() // inactive and no state yet, so this need not wait for pending activation
                pending
            }
            future.get(5, TimeUnit.SECONDS)
            assertTrue(h.sockets.isEmpty())
        } finally { executor.shutdownNow() }
    }

    @Test fun `stale inactive gate does not stop newly enabled session`() {
        val h = Harness()
        h.prefs.values["nativeBleStreamingEnabled"] = false
        h.prefs.afterBooleanRead = { key ->
            if (key == "nativeBleStreamingEnabled") {
                h.prefs.afterBooleanRead = null
                h.prefs.values["nativeBleStreamingEnabled"] = true
                h.frame(2)
            }
        }
        h.frame(1)
        assertFalse(h.sockets.single().closed)
        h.sockets.single().open()
        assertEquals(listOf(2), h.sockets.single().values())
    }

    @Test fun `inactive gate clears queued native frames during reconnect backoff`() {
        val h = Harness()
        h.frame(1)
        h.sockets.single().listener.onFailure(h.sockets.single(), IllegalStateException("offline"), null)
        h.time += 1000
        h.frame(2)
        h.prefs.values["nativeBleStreamingEnabled"] = false
        h.frame(3)
        h.prefs.values["nativeBleStreamingEnabled"] = true
        h.time += 3000
        h.frame(4)
        h.sockets.last().open()
        assertEquals(listOf(4), h.sockets.last().values())
    }

    @Test fun `every stop reason clears cached transcripts after account change`() {
        for (reason in listOf("service_destroyed", "foreground_ready", "disabled")) {
            OmiBackgroundAudioStreamer.drainCachedTranscriptMessages()
            val h = Harness()
            h.frame()
            val socket = h.sockets.single()
            socket.listener.onMessage(socket, "{\"text\":\"old\"}")
            h.prefs.values["uid"] = "account-b"
            h.streamer.stop(reason)
            assertTrue(OmiBackgroundAudioStreamer.drainCachedTranscriptMessages().isEmpty())
        }
    }

    @Test fun `inactive gate clears previous account transcripts without native state`() {
        OmiBackgroundAudioStreamer.drainCachedTranscriptMessages()
        val h = Harness()
        h.frame()
        val socket = h.sockets.single()
        socket.listener.onMessage(socket, "{\"text\":\"old\"}")
        h.streamer.stop("service_destroyed") // still same UID: retain legitimate transcript
        h.prefs.values["uid"] = "account-b"
        h.prefs.values["nativeBleStreamingEnabled"] = false
        val executor = Executors.newSingleThreadExecutor()
        try {
            synchronized(h.stateLock) { executor.submit { h.frame() }.get(5, TimeUnit.SECONDS) }
            assertTrue(OmiBackgroundAudioStreamer.drainCachedTranscriptMessages().isEmpty())
        } finally { executor.shutdownNow() }
    }

}

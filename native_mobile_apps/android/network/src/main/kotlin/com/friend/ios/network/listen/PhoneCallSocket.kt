package com.friend.ios.network.listen

import com.friend.ios.network.endpoints.JsonAccess
import com.friend.ios.network.endpoints.objects
import com.friend.ios.network.endpoints.string
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.net.URI
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/** Server -> client on a phone call's transcription socket. */
sealed interface PhoneCallSocketEvent {
    /** Segments, re-sent with the same id when refined (upsert by id). */
    data class Segments(val segments: List<LiveSegment>) : PhoneCallSocketEvent

    /** `translating`: segment id -> its translated texts (live interpreter on calls). */
    data class Translations(val translations: Map<String, List<String>>) : PhoneCallSocketEvent

    /** Any other server message (`service_status`, the session, `ping`): the socket is accepted. */
    data class Status(val status: String) : PhoneCallSocketEvent

    /** The socket closed (server, network); the store reconnects while the call lasts. */
    data class Closed(val reason: String?) : PhoneCallSocketEvent

    companion object {
        /** Parses one text frame (Flutter `PhoneCallProvider._handleTranscriptionMessage`); `ping` is null. */
        fun parse(text: String): PhoneCallSocketEvent? {
            if (text == "ping") return null
            if (text.firstOrNull() == '[') {
                val array = JsonAccess.parse(text) as? JsonArray ?: return null
                return Segments(array.mapNotNull { it as? JsonObject }.map(LiveSegment::from))
            }
            val item = JsonAccess.parse(text) as? JsonObject ?: return null
            val type = item.string("type")
            if (type != "translating") return Status(item.string("status") ?: type ?: "message")
            val translated = LinkedHashMap<String, List<String>>()
            for (segment in item.objects("segments")) {
                val id = segment.string("id") ?: continue
                val texts = segment.objects("translations").mapNotNull { it.string("text") }
                if (texts.isNotEmpty()) translated[id] = texts
            }
            return Translations(translated)
        }
    }
}

/** One phone call's transcription stream as the phone-call store sees it (real socket or test fake). */
interface PhoneCallTranscriptChannel {
    /** Every message the server sent; finishes after [PhoneCallSocketEvent.Closed]. */
    val events: Flow<PhoneCallSocketEvent>

    /** One binary frame: a channel byte (`0x01` you, `0x02` the other side) then PCM16 at 48 kHz. */
    fun send(frame: ByteArray)

    fun close()
}

/**
 * Port of `PhoneCallSocket.swift`: `/v4/listen` for a call, `source=phone_call`, `channels=2`, the
 * call id the Twilio leg carries. Contract: backend `routers/listen` (`build_channel_config('phone_call')`)
 * and Flutter `buildPhoneCallWebSocketUrl` (`app/lib/backend/http/api/phone_calls.dart`).
 */
class PhoneCallSocket internal constructor(
    private val request: Request,
    private val client: OkHttpClient,
) : PhoneCallTranscriptChannel {
    private val channel = Channel<PhoneCallSocketEvent>(256, BufferOverflow.DROP_OLDEST)
    override val events: Flow<PhoneCallSocketEvent> = channel.receiveAsFlow()

    @Volatile
    private var socket: WebSocket? = null

    @Volatile
    private var closed = false

    internal fun open() {
        socket = client.newWebSocket(request, Listener())
    }

    override fun send(frame: ByteArray) {
        if (frame.size <= 1 || closed) return
        socket?.send(frame.toByteString())
    }

    override fun close() {
        closed = true
        socket?.close(1000, null)
        channel.close()
    }

    private inner class Listener : WebSocketListener() {
        override fun onMessage(webSocket: WebSocket, text: String) {
            // Flutter counts every message, `ping` included, as the server having accepted the socket.
            channel.trySend(PhoneCallSocketEvent.parse(text) ?: PhoneCallSocketEvent.Status(if (text == "ping") "ping" else "message"))
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {}

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, null)
            lost("closed $code $reason".trim())
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            lost("closed $code $reason".trim())
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            lost(t.message ?: t.toString())
        }

        private fun lost(description: String) {
            if (closed) return
            closed = true
            channel.trySend(PhoneCallSocketEvent.Closed(description))
            channel.close()
        }
    }

    companion object {
        const val SAMPLE_RATE = 48000

        /**
         * No read timeout on a socket that stays open for the whole call; Flutter's IOWebSocketChannel
         * pings every 20 s so idle calls (hold music) do not drop.
         */
        fun socketClient(base: OkHttpClient): OkHttpClient = base.newBuilder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .callTimeout(0, TimeUnit.MILLISECONDS)
            .pingInterval(20, TimeUnit.SECONDS)
            .build()

        /** The `/v4/listen` query of a call (OkHttp upgrades the http(s) URL to ws(s) itself). */
        fun query(uid: String, callID: String, language: String): List<Pair<String, String>> = listOf(
            "source" to "phone_call",
            "call_id" to callID,
            "uid" to uid,
            "sample_rate" to SAMPLE_RATE.toString(),
            "codec" to "pcm",
            "language" to language,
            "channels" to "2",
        )

        /** `PhoneCallSocket.url(base:...)`: the ws(s) URL the request is upgraded to. */
        fun url(base: URI, uid: String, callID: String, language: String): URI {
            val scheme = if (base.scheme == "https") "wss" else "ws"
            val path = base.path.trimEnd('/') + "/v4/listen"
            val queryText = query(uid, callID, language).joinToString("&") { (name, value) ->
                "$name=${URLEncoder.encode(value, "UTF-8")}"
            }
            val port = if (base.port >= 0) ":${base.port}" else ""
            return URI("$scheme://${base.host}$port$path?$queryText")
        }
    }
}

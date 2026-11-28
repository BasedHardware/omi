package com.friend.ios.network.listen

import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.UUID
import java.util.concurrent.TimeUnit

/** A live transcription session as the capture layer sees it (real socket or test fake). */
interface LiveTranscriptionChannel {
    /** Server events, for one collector; ends when the socket closes. */
    val events: Flow<ListenEvent>

    fun send(audio: ByteArray)

    fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String)

    fun close(reason: String = "user_stop")

    /** A voice was named during capture (after the REST assignment): the session picks it up. */
    fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) {}
}

/**
 * The capture stream to `/v4/listen`. One instance per recording session.
 * Contract: backend `routers/transcribe.py` + Flutter `transcription_service.dart`.
 * iOS runs it on `URLSessionWebSocketTask`; here OkHttp's WebSocket.
 */
class ListenSocket internal constructor(
    private val request: Request,
    private val client: OkHttpClient,
    private val kind: Kind = Kind.Listen,
) : LiveTranscriptionChannel {
    data class Options(
        var codec: Codec,
        var sampleRate: Int = 16000,
        var source: Source,
        var language: String = "en",
        var conversationTimeout: Int = 120,
        /** The client supplies transcripts itself (`suggested_transcript`), e.g. on-device STT. */
        var clientTranscription: Boolean = false,
        /** The server's speech model (`stt_service`, e.g. `parakeet`); null lets the backend choose. */
        var sttService: String? = null,
        /** `vad_gate=enabled`: the backend only transcribes speech (developer setting). */
        var vadGate: Boolean = false,
        /**
         * Where the recording starts (`X-Omi-Conversation-Geolocation`, the compact JSON of iOS
         * `GeolocationSnapshot.headerValue`); null without location access.
         */
        var geolocationHeader: String? = null,
        /**
         * The recording's id (`client_conversation_id`). A socket reopened with the same id resumes
         * the recording's conversation instead of starting a new one.
         */
        var clientConversationID: String = UUID.randomUUID().toString().lowercase(),
    ) {
        enum class Codec(val rawValue: String) {
            Pcm16("pcm16"), OpusFS320("opus_fs320"), Opus("opus"), Pcm8("pcm8");

            companion object {
                fun from(raw: String): Codec? = entries.firstOrNull { it.rawValue == raw }
            }
        }

        /** Backend `ConversationSource` values (`models/conversation_enums.py`). */
        enum class Source(val rawValue: String) { Phone("phone"), Omi("omi"), AppleWatch("apple_watch") }
    }

    /** `/v4/listen` captures conversations; `/v2/voice-message/transcribe-stream` only transcribes. */
    enum class Kind { Listen, TranscribeOnly }

    private val channel = Channel<ListenEvent>(256, BufferOverflow.DROP_OLDEST)
    override val events: Flow<ListenEvent> = channel.receiveAsFlow()

    @Volatile
    private var socket: WebSocket? = null

    @Volatile
    private var closed = false

    internal fun open() {
        socket = client.newWebSocket(request, Listener())
        if (kind == Kind.Listen) sendText("""{"type":"client_state","foreground":true,"transcript_visible":true}""")
    }

    /** One binary message per audio chunk (PCM16 chunk or one opus packet). */
    override fun send(audio: ByteArray) {
        if (audio.size <= 2 || closed) return
        socket?.send(audio.toByteString())
    }

    /** Client-side transcript (custom STT mode). Shape from backend `fakes/stt.py`. */
    override fun sendSuggestedTranscript(segments: List<LiveSegment>, provider: String) {
        val payload = buildJsonObject {
            put("type", "suggested_transcript")
            put("stt_provider", provider)
            put("segments", buildJsonArray {
                segments.forEach { segment ->
                    add(buildJsonObject {
                        put("id", segment.id)
                        put("text", segment.text)
                        put("speaker", segment.speaker ?: "SPEAKER_00")
                        put("speaker_id", segment.speakerID ?: 0)
                        put("is_user", segment.isUser)
                        put("start", segment.start)
                        put("end", segment.end)
                    })
                }
            })
        }
        sendText(payload.toString())
    }

    /** Flutter `assignSpeakerToConversation`; backend `receiver.py` `_handle_speaker_assigned`. */
    override fun sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: List<String>) {
        val payload = buildJsonObject {
            put("type", "speaker_assigned")
            put("person_id", personID)
            put("person_name", personName)
            put("segment_ids", buildJsonArray { segmentIDs.forEach { add(JsonPrimitive(it)) } })
            if (speakerID != null) put("speaker_id", speakerID)
        }
        sendText(payload.toString())
    }

    override fun close(reason: String) {
        sendText(if (kind == Kind.Listen) """{"type":"finalization_reason","reason":"$reason"}""" else "finalize")
        closed = true
        socket?.close(1000, null)
        channel.close()
    }

    private fun sendText(text: String) {
        socket?.send(text)
    }

    private inner class Listener : WebSocketListener() {
        override fun onMessage(webSocket: WebSocket, text: String) {
            if (text == "ping") {
                webSocket.send("pong")
                return
            }
            ListenEvent.parse(text)?.let { channel.trySend(it) }
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {}

        /** The server closes: answer the close handshake and report the session as lost. */
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
            channel.trySend(ListenEvent.Status("disconnected: $description"))
            channel.close()
        }
    }

    companion object {
        /** No read timeout on a socket that stays open for hours; the server pings. */
        fun socketClient(base: OkHttpClient): OkHttpClient = base.newBuilder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .callTimeout(0, TimeUnit.MILLISECONDS)
            .build()

        /** The `/v4/listen` query (OkHttp upgrades the http(s) URL to ws(s) itself). */
        fun query(uid: String, options: Options): List<Pair<String, String>> = buildList {
            add("language" to options.language)
            add("sample_rate" to options.sampleRate.toString())
            add("codec" to options.codec.rawValue)
            add("uid" to uid)
            add("include_speech_profile" to "true")
            add("conversation_timeout" to options.conversationTimeout.toString())
            add("source" to options.source.rawValue)
            add("client_conversation_id" to options.clientConversationID)
            add("speaker_auto_assign" to "enabled")
            add("create_speakers" to "true")
            if (options.clientTranscription) add("custom_stt" to "enabled")
            options.sttService?.takeIf { it.isNotEmpty() }?.let { add("stt_service" to it) }
            if (options.vadGate) add("vad_gate" to "enabled")
        }
    }
}

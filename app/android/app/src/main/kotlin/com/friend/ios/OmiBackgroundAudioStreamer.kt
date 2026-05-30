package com.friend.ios

import android.content.Context
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.net.URLEncoder
import java.util.ArrayDeque
import java.util.Locale
import java.util.concurrent.TimeUnit

class OmiBackgroundAudioStreamer(private val context: Context) {
    companion object {
        private const val TAG = "OmiBle.BgAudio"
        private const val FLUTTER_PREFS = "FlutterSharedPreferences"
        private const val DEFAULT_API_BASE_URL = "https://api.omiapi.com/"
        private const val MAX_PENDING_FRAMES = 200
        private const val RECONNECT_BACKOFF_MS = 3_000L
        private const val MAX_CACHED_TRANSCRIPT_MESSAGES = 200
        private val transcriptCacheLock = Any()
        private val cachedTranscriptMessages = ArrayDeque<String>()

        fun drainCachedTranscriptMessages(): List<String> =
            synchronized(transcriptCacheLock) {
                if (cachedTranscriptMessages.isEmpty()) {
                    emptyList()
                } else {
                    val messages = cachedTranscriptMessages.toList()
                    cachedTranscriptMessages.clear()
                    messages
                }
            }
    }

    private data class Config(
        val deviceId: String,
        val codec: String,
        val sampleRate: Int,
        val source: String,
        val apiBaseUrl: String,
        val serviceUuid: String,
        val characteristicUuid: String,
        val deviceType: String
    )

    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .connectTimeout(15, TimeUnit.SECONDS)
        .build()
    private val lock = Any()
    private val pendingFrames = ArrayDeque<ByteArray>()
    private var socket: WebSocket? = null
    private var connecting = false
    private var connected = false
    private var activeUrl: String? = null
    private var activeConfig: Config? = null
    private var sentFrames = 0
    @Volatile
    private var lastFailureAtMs = 0L

    // Per-device byte accumulator. Used by device types whose audio payload
    // straddles BLE notifications (Bee: ADTS-framed AAC; Plaud: 80-byte chunking
    // of variable-length opus payloads). Reset whenever the active config
    // changes or the socket is torn down so we never mix bytes from two
    // sessions. Other device types (omi/openglass/friendPendant/fieldy) ignore
    // this buffer and remain pure transforms.
    private val rxBuffer = ArrayDeque<Byte>()

    fun isConfiguredFor(address: String): Boolean {
        val config = loadConfig() ?: return false
        return config.deviceId.equals(address, ignoreCase = true)
    }

    fun configuredAudioTargetFor(address: String): Pair<String, String>? {
        val config = loadConfig() ?: return null
        if (!config.deviceId.equals(address, ignoreCase = true)) return null
        return config.serviceUuid to config.characteristicUuid
    }

    fun stop(reason: String) {
        var socketToClose: WebSocket? = null
        synchronized(lock) {
            socketToClose = socket
            if (socketToClose != null) {
                Log.i(TAG, "Stopping background transcription websocket ($reason)")
            }
            socket = null
            connecting = false
            connected = false
            activeUrl = null
            activeConfig = null
            pendingFrames.clear()
            rxBuffer.clear()
        }
        socketToClose?.close(1000, reason)
    }

    fun handleCharacteristic(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray) {
        val config = loadConfig()
        if (config == null) {
            if (socket != null) stop("disabled")
            return
        }
        if (OmiBleManager.isFlutterAlive && boolPref("nativeBleForegroundReady", false)) {
            if (socket != null) stop("foreground_ready")
            return
        }
        if (!config.deviceId.equals(address, ignoreCase = true)) return
        if (!matches(config, serviceUuid, characteristicUuid)) return

        val frames = transformFrames(config, value)
        if (frames.isEmpty()) return

        ensureSocket(config)

        for (frame in frames) {
            sendOrQueue(frame)
        }
    }

    private fun matches(config: Config, serviceUuid: String, characteristicUuid: String): Boolean =
        config.serviceUuid.equals(serviceUuid, ignoreCase = true) &&
            config.characteristicUuid.equals(characteristicUuid, ignoreCase = true)

    private fun transformFrames(config: Config, value: ByteArray): List<ByteArray> =
        when (config.deviceType) {
            "omi", "openglass" -> {
                if (value.size <= 3) emptyList() else listOf(value.copyOfRange(3, value.size))
            }
            "friendPendant" -> {
                if (value.size <= 5) {
                    emptyList()
                } else {
                    val payload = value.copyOfRange(0, value.size - 5)
                    val frames = mutableListOf<ByteArray>()
                    var offset = 0
                    while (offset + 30 <= payload.size) {
                        frames.add(payload.copyOfRange(offset, offset + 30))
                        offset += 30
                    }
                    frames
                }
            }
            // Fieldy: each notification carries N back-to-back 40-byte Opus
            // frames (typically 6 → 240 bytes). Mirrors FieldyDeviceConnection
            // .performGetBleAudioBytesListener — split on 40-byte boundaries,
            // forward any final partial frame only if it starts with the
            // expected Opus TOC byte 0xb8 (avoids forwarding stray bytes).
            "fieldy" -> {
                val frames = mutableListOf<ByteArray>()
                var offset = 0
                while (offset + 40 <= value.size) {
                    frames.add(value.copyOfRange(offset, offset + 40))
                    offset += 40
                }
                if (offset < value.size && value[offset] == 0xb8.toByte()) {
                    frames.add(value.copyOfRange(offset, value.size))
                }
                frames
            }
            // Bee: notifications carry a 2-byte transport header followed by
            // ADTS-framed AAC. Frames straddle notifications, so we accumulate
            // into rxBuffer and slice on each complete ADTS frame. Mirrors
            // BeeDeviceConnection.processAudioPacket exactly: scan for the
            // sync word (0xFF + high-nibble 0xF), read the 13-bit ADTS frame
            // length from bytes 3-5, emit when the buffer holds the full
            // frame. Drop a single byte on resync mismatch.
            "bee" -> {
                if (value.size < 2) {
                    emptyList()
                } else {
                    for (i in 2 until value.size) rxBuffer.addLast(value[i])
                    val frames = mutableListOf<ByteArray>()
                    while (rxBuffer.size >= 7) {
                        val b0 = rxBuffer.elementAt(0).toInt() and 0xFF
                        val b1 = rxBuffer.elementAt(1).toInt() and 0xFF
                        if (b0 != 0xFF || (b1 and 0xF0) != 0xF0) {
                            rxBuffer.removeFirst()
                            continue
                        }
                        val b3 = rxBuffer.elementAt(3).toInt() and 0xFF
                        val b4 = rxBuffer.elementAt(4).toInt() and 0xFF
                        val b5 = rxBuffer.elementAt(5).toInt() and 0xFF
                        val frameLength = ((b3 and 0x03) shl 11) or (b4 shl 3) or ((b5 and 0xE0) ushr 5)
                        // Sanity-check the frame length against ADTS constraints
                        // before consuming. Out-of-range values mean we're
                        // mid-stream of noise — resync by one byte.
                        if (frameLength < 7 || frameLength > 8192) {
                            rxBuffer.removeFirst()
                            continue
                        }
                        if (rxBuffer.size < frameLength) break
                        val frame = ByteArray(frameLength) { rxBuffer.removeFirst() }
                        frames.add(frame)
                    }
                    frames
                }
            }
            // Plaud: notify characteristic carries both command responses and
            // audio. Audio packets start with type byte 0x02; everything else
            // is dropped (responses can't reach the WS — they're not audio).
            // Layout: [0]=type, [1..4]=metadata, [5..8]=position (LE uint32,
            // 0xFFFFFFFF = end-of-stream sentinel), [9]=length, [10..10+len]
            // =audio payload. The payload is then re-chunked into 80-byte
            // frames before sending — matches PlaudDeviceConnection's
            // accumulator (the backend expects opus_fs320 in fixed chunks).
            "plaud" -> {
                if (value.size < 10 || (value[0].toInt() and 0xFF) != 2) {
                    emptyList()
                } else {
                    val posB0 = value[5].toInt() and 0xFF
                    val posB1 = value[6].toInt() and 0xFF
                    val posB2 = value[7].toInt() and 0xFF
                    val posB3 = value[8].toInt() and 0xFF
                    val isEndMarker = posB0 == 0xFF && posB1 == 0xFF && posB2 == 0xFF && posB3 == 0xFF
                    if (isEndMarker) {
                        emptyList()
                    } else {
                        val length = value[9].toInt() and 0xFF
                        if (length == 0 || 10 + length > value.size) {
                            emptyList()
                        } else {
                            for (i in 10 until 10 + length) rxBuffer.addLast(value[i])
                            val frames = mutableListOf<ByteArray>()
                            while (rxBuffer.size >= 80) {
                                val chunk = ByteArray(80) { rxBuffer.removeFirst() }
                                frames.add(chunk)
                            }
                            frames
                        }
                    }
                }
            }
            else -> {
                Log.w(TAG, "Unsupported background BLE audio device type: ${config.deviceType}")
                emptyList()
            }
        }

    private fun ensureSocket(config: Config) {
        val now = System.currentTimeMillis()
        if (now - lastFailureAtMs < RECONNECT_BACKOFF_MS) return

        val url = buildUrl(config) ?: return
        val request = buildRequest(url) ?: return

        synchronized(lock) {
            if ((connecting || connected) && activeUrl == url && activeConfig == config && socket != null) {
                return
            }

            socket?.close(1000, "reconfigure")
            socket = null
            connecting = true
            connected = false
            activeUrl = url
            activeConfig = config
            sentFrames = 0
            rxBuffer.clear()

            Log.i(TAG, "Opening background transcription websocket (codec=${config.codec}, source=${config.source})")
            socket = client.newWebSocket(request, listener())
        }
    }

    private fun listener(): WebSocketListener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            val queued = mutableListOf<ByteArray>()
            synchronized(lock) {
                if (webSocket != socket) return
                connecting = false
                connected = true
                while (pendingFrames.isNotEmpty()) {
                    queued.add(pendingFrames.removeFirst())
                }
            }
            Log.i(TAG, "Background transcription socket connected")
            for (frame in queued) {
                sendFrame(webSocket, frame)
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            cacheTranscriptMessage(text)
            Log.d(TAG, "Background transcription message received (${text.length} chars)")
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, reason)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            synchronized(lock) {
                if (webSocket != socket) return
                socket = null
                connecting = false
                connected = false
            }
            Log.i(TAG, "Background transcription socket closed (code=$code)")
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            synchronized(lock) {
                if (webSocket != socket) return
                socket = null
                connecting = false
                connected = false
                lastFailureAtMs = System.currentTimeMillis()
            }
            Log.w(TAG, "Background transcription socket failed: ${t.message}")
        }
    }

    private fun sendOrQueue(frame: ByteArray) {
        var target: WebSocket? = null
        synchronized(lock) {
            target = if (connected) socket else null
            if (target == null) {
                queueFrameLocked(frame)
                return
            }
        }
        val webSocket = target ?: return
        if (!sendFrame(webSocket, frame)) {
            synchronized(lock) {
                queueFrameLocked(frame)
            }
        }
    }

    private fun sendFrame(webSocket: WebSocket, frame: ByteArray): Boolean {
        val sent = webSocket.send(frame.toByteString())
        if (sent) {
            val totalSent = synchronized(lock) {
                sentFrames += 1
                sentFrames
            }
            if (totalSent % 100 == 0) {
                Log.i(TAG, "Sent $totalSent background BLE audio frames")
            }
        }
        return sent
    }

    private fun cacheTranscriptMessage(text: String) {
        val trimmed = text.trimStart()
        if (!trimmed.startsWith("[") && !trimmed.startsWith("{")) return

        synchronized(transcriptCacheLock) {
            if (cachedTranscriptMessages.size >= MAX_CACHED_TRANSCRIPT_MESSAGES) {
                cachedTranscriptMessages.removeFirst()
            }
            cachedTranscriptMessages.addLast(text)
        }
    }

    private fun queueFrameLocked(frame: ByteArray) {
        if (pendingFrames.size >= MAX_PENDING_FRAMES) {
            pendingFrames.removeFirst()
        }
        pendingFrames.addLast(frame.copyOf())
    }

    private fun loadConfig(): Config? {
        if (!boolPref("nativeBleStreamingEnabled", false)) return null
        val raw = stringPref("nativeBleStreamConfig")
        if (raw.isEmpty()) return null

        return try {
            val json = JSONObject(raw)
            val deviceId = json.optString("deviceId")
            val serviceUuid = json.optString("serviceUuid").lowercase(Locale.US)
            val characteristicUuid = json.optString("characteristicUuid").lowercase(Locale.US)
            if (deviceId.isEmpty() || serviceUuid.isEmpty() || characteristicUuid.isEmpty()) return null

            Config(
                deviceId = deviceId,
                codec = json.optString("codec", "pcm8"),
                sampleRate = json.optInt("sampleRate", 16000),
                source = json.optString("source"),
                apiBaseUrl = json.optString("apiBaseUrl"),
                serviceUuid = serviceUuid,
                characteristicUuid = characteristicUuid,
                deviceType = json.optString("deviceType")
            )
        } catch (e: Exception) {
            Log.w(TAG, "Invalid native BLE stream config: ${e.message}")
            null
        }
    }

    private fun buildRequest(url: String): Request? {
        val token = stringPref("authToken")
        if (token.isEmpty()) {
            Log.w(TAG, "Cannot open background transcription socket without auth token")
            return null
        }

        return Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $token")
            .header("X-Request-Start-Time", (System.currentTimeMillis().toDouble() / 1000.0).toString())
            .header("X-App-Platform", "android")
            .header("X-Device-Id-Hash", stringPref("deviceIdHash"))
            .header("X-App-Version", BuildConfig.VERSION_NAME)
            .build()
    }

    private fun buildUrl(config: Config): String? {
        val uid = stringPref("uid")
        if (uid.isEmpty()) {
            Log.w(TAG, "Cannot open background transcription socket without uid")
            return null
        }

        val language = if (boolPref("hasSetPrimaryLanguage", false)) {
            stringPref("userPrimaryLanguage", "multi").ifEmpty { "multi" }
        } else {
            "multi"
        }
        val sttService = stringPref("transcriptionModel3", "soniox").ifEmpty { "soniox" }
        val timeout = intPref("conversationSilenceDuration", 120).takeIf { it > 0 } ?: 120
        val base = normalizeBaseUrl(config.apiBaseUrl.ifEmpty { DEFAULT_API_BASE_URL })

        val params = mutableListOf(
            "language=${enc(language)}",
            "sample_rate=${config.sampleRate}",
            "codec=${enc(config.codec)}",
            "uid=${enc(uid)}",
            "include_speech_profile=true",
            "stt_service=${enc(sttService)}",
            "conversation_timeout=$timeout"
        )
        if (config.source.isNotEmpty()) {
            params.add("source=${enc(config.source)}")
        }
        params.add("speaker_auto_assign=enabled")
        if (boolPref("vadGateEnabled", false)) {
            params.add("vad_gate=enabled")
        }

        return "${base}v4/listen?${params.joinToString("&")}"
    }

    private fun normalizeBaseUrl(value: String): String {
        var base = value.trim().ifEmpty { DEFAULT_API_BASE_URL }
        val lowerBase = base.lowercase(Locale.US)
        if (lowerBase.startsWith("wss://") || lowerBase.startsWith("ws://")) {
            base = lowerBase.substringBefore("://") + "://" + base.substringAfter("://")
            return if (base.endsWith("/")) base else "$base/"
        }
        base = when {
            lowerBase.startsWith("https://") -> "wss://" + base.substring("https://".length)
            lowerBase.startsWith("http://") -> "ws://" + base.substring("http://".length)
            else -> "wss://$base"
        }
        return if (base.endsWith("/")) base else "$base/"
    }

    private fun prefs() = context.getSharedPreferences(FLUTTER_PREFS, Context.MODE_PRIVATE)

    private fun prefValue(key: String): Any? = prefs().all["flutter.$key"]

    private fun stringPref(key: String, defaultValue: String = ""): String =
        when (val value = prefValue(key)) {
            is String -> value
            null -> defaultValue
            else -> value.toString()
        }

    private fun boolPref(key: String, defaultValue: Boolean): Boolean =
        when (val value = prefValue(key)) {
            is Boolean -> value
            is String -> value.toBooleanStrictOrNull() ?: defaultValue
            else -> defaultValue
        }

    private fun intPref(key: String, defaultValue: Int): Int =
        when (val value = prefValue(key)) {
            is Int -> value
            is Long -> value.toInt()
            is String -> value.toIntOrNull() ?: defaultValue
            else -> defaultValue
        }

    private fun enc(value: String): String = URLEncoder.encode(value, "UTF-8")
}

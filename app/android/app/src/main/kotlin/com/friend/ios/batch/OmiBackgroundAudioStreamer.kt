package com.friend.ios.batch

import com.friend.ios.BuildConfig

import com.friend.ios.ble.OmiBleManager

import android.content.Context
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString.Companion.toByteString
import java.net.URLEncoder
import java.util.ArrayDeque
import java.util.Locale
import java.util.concurrent.TimeUnit

class OmiBackgroundAudioStreamer internal constructor(
    private val preferences: NativeBlePreferences,
    private val openSocket: (Request, WebSocketListener) -> WebSocket,
    private val flutterAlive: () -> Boolean,
    private val nowMs: () -> Long,
    private val log: (Int, String) -> Unit,
    private val lock: Any = Any(),
) {
    constructor(context: Context) : this(
        SharedPreferencesValues(context.getSharedPreferences(FLUTTER_PREFS, Context.MODE_PRIVATE)),
        OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).connectTimeout(15, TimeUnit.SECONDS)
            .build().let { client -> { request, listener -> client.newWebSocket(request, listener) } },
        { OmiBleManager.isFlutterAlive },
        System::currentTimeMillis,
        { priority, message -> Log.println(priority, TAG, message) },
    )
    companion object {
        private const val TAG = "OmiBle.BgAudio"
        private const val FLUTTER_PREFS = "FlutterSharedPreferences"
        private const val DEFAULT_API_BASE_URL = "https://api.omiapi.com/"
        private const val MAX_PENDING_FRAMES = 200
        private const val RECONNECT_BACKOFF_MS = 3_000L
        private const val MAX_CACHED_TRANSCRIPT_MESSAGES = 200
        private val transcriptCacheLock = Any()
        private val cachedTranscriptMessages = ArrayDeque<String>()
        @Volatile
        private var cachedTranscriptUid: String? = null

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

    private val settingsReader = NativeBleStreamSettingsReader(preferences)

    @Volatile
    private var hasNativeState = false
    private val pendingFrames = ArrayDeque<ByteArray>()
    private var socket: WebSocket? = null
    private var connecting = false
    private var connected = false
    private var activeSettings: NativeBleStreamSettings? = null
    private var sentFrames = 0
    @Volatile
    private var lastFailureAtMs = 0L

    fun isConfiguredFor(address: String): Boolean {
        val config = settingsReader.config() ?: return false
        return config.deviceId.equals(address, ignoreCase = true)
    }

    fun configuredAudioTargetFor(address: String): Pair<String, String>? {
        val config = settingsReader.config() ?: return null
        if (!config.deviceId.equals(address, ignoreCase = true)) return null
        return config.serviceUuid to config.characteristicUuid
    }

    fun stop(reason: String) {
        var socketToClose: WebSocket? = null
        synchronized(lock) {
            socketToClose = socket
            if (socketToClose != null) {
                log(Log.INFO, "Stopping background transcription websocket ($reason)")
            }
            socket = null
            connecting = false
            connected = false
            activeSettings = null
            pendingFrames.clear()
            clearTranscriptsIfAccountChanged()
            hasNativeState = false
        }
        socketToClose?.close(1000, reason)
    }

    fun handleCharacteristic(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray) {
        val inactiveReason = when {
            flutterAlive() && preferences.boolean("nativeBleForegroundReady") -> "foreground_ready"
            !preferences.boolean("nativeBleStreamingEnabled") -> "disabled"
            else -> null
        }
        if (inactiveReason != null) {
            clearTranscriptsIfAccountChanged()
            if (hasNativeState) {
                synchronized(lock) {
                    // A stale gate read must not tear down a newly enabled session.
                    if (flutterAlive() && preferences.boolean("nativeBleForegroundReady")) {
                        stop("foreground_ready")
                    } else if (!preferences.boolean("nativeBleStreamingEnabled")) {
                        stop("disabled")
                    }
                }
            }
            return
        }
        synchronized(lock) {
            // Publish activation before re-reading gates. A racing disabled callback either
            // stops this state, or this callback observes the gate before opening a socket.
            hasNativeState = true
            if (flutterAlive() && preferences.boolean("nativeBleForegroundReady")) {
                stop("foreground_ready")
                return
            }
            val settings = settingsReader.settings()
            if (settings == null) {
                stop("disabled")
                return
            }
            val config = settings.config
            if (!config.deviceId.equals(address, ignoreCase = true) ||
                !matches(config, serviceUuid, characteristicUuid)) {
                hasNativeState = activeSettings != null
                return
            }

            val frames = transformFrames(config, value)
            if (frames.isEmpty()) {
                hasNativeState = activeSettings != null
                return
            }
            ensureSocket(settings)
            for (frame in frames) sendOrQueue(frame)
        }
    }

    private fun clearTranscriptsIfAccountChanged() {
        val uid = preferences.string("uid")
        if (cachedTranscriptUid == uid) return
        synchronized(transcriptCacheLock) {
            if (cachedTranscriptUid != uid) {
                cachedTranscriptMessages.clear()
                cachedTranscriptUid = uid
            }
        }
    }

    private fun matches(config: NativeBleStreamConfig, serviceUuid: String, characteristicUuid: String): Boolean =
        config.serviceUuid.equals(serviceUuid, ignoreCase = true) &&
            config.characteristicUuid.equals(characteristicUuid, ignoreCase = true)

    private fun transformFrames(config: NativeBleStreamConfig, value: ByteArray): List<ByteArray> =
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
            else -> {
                log(Log.WARN, "Unsupported background BLE audio device type: ${config.deviceType}")
                emptyList()
            }
        }

    // Caller holds lock, including forwarding, so reconfiguration cannot leak queued frames.
    private fun ensureSocket(settings: NativeBleStreamSettings) {
        if (activeSettings != settings) {
            val previous = activeSettings
            val incompatible = previous != null &&
                (previous.uid != settings.uid ||
                    previous.config.copy(geolocation = null) != settings.config.copy(geolocation = null))
            synchronized(transcriptCacheLock) {
                if (cachedTranscriptUid != settings.uid) cachedTranscriptMessages.clear()
                cachedTranscriptUid = settings.uid
            }
            socket?.close(1000, "reconfigure")
            socket = null
            connecting = false
            connected = false
            if (incompatible) pendingFrames.clear()
            activeSettings = settings
        }
        if ((connecting || connected) && socket != null) return
        if (nowMs() - lastFailureAtMs < RECONNECT_BACKOFF_MS) return

        val request = buildRequest(buildUrl(settings), settings)
        connecting = true
        connected = false
        sentFrames = 0
        log(Log.INFO, "Opening background transcription websocket (codec=${settings.config.codec}, source=${settings.config.source})")
        socket = openSocket(request, listener())
    }

    private fun listener(): WebSocketListener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            synchronized(lock) {
                if (webSocket != socket) return
                if (flutterAlive() && preferences.boolean("nativeBleForegroundReady")) {
                    stop("foreground_ready")
                    return
                }
                val settings = settingsReader.settings()
                if (settings == null) {
                    stop("disabled")
                    return
                }
                if (settings != activeSettings) {
                    ensureSocket(settings)
                    return
                }
                connecting = false
                connected = true
                log(Log.INFO, "Background transcription socket connected")
                while (pendingFrames.isNotEmpty()) {
                    val frame = pendingFrames.removeFirst()
                    if (!sendFrame(webSocket, frame)) {
                        pendingFrames.addFirst(frame)
                        break
                    }
                }
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            synchronized(lock) {
                if (webSocket != socket) return
                val settings = settingsReader.settings()
                if (settings == null || settings.uid != activeSettings?.uid) {
                    stop("disabled")
                    return
                }
                cacheTranscriptMessage(text)
            }
            log(Log.DEBUG, "Background transcription message received (${text.length} chars)")
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
            log(Log.INFO, "Background transcription socket closed (code=$code)")
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            synchronized(lock) {
                if (webSocket != socket) return
                socket = null
                connecting = false
                connected = false
                lastFailureAtMs = nowMs()
            }
            log(Log.WARN, "Background transcription socket failed: ${t.message}")
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
                log(Log.INFO, "Sent $totalSent background BLE audio frames")
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

    private fun buildRequest(url: String, settings: NativeBleStreamSettings): Request {
        val builder = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer ${settings.token}")
            .header("X-Request-Start-Time", (nowMs().toDouble() / 1000.0).toString())
            .header("X-App-Platform", "android")
            .header("X-Device-Id-Hash", settings.deviceIdHash)
            .header("X-App-Version", BuildConfig.VERSION_NAME)
        return addConversationGeolocationHeader(builder, settings.config.geolocation).build()
    }

    private fun buildUrl(settings: NativeBleStreamSettings): String {
        val config = settings.config
        val base = normalizeBaseUrl(config.apiBaseUrl.ifEmpty { DEFAULT_API_BASE_URL })
        val params = mutableListOf(
            "language=${enc(settings.language)}",
            "sample_rate=${config.sampleRate}",
            "codec=${enc(config.codec)}",
            "uid=${enc(settings.uid)}",
            "include_speech_profile=true",
            "stt_service=${enc(settings.sttService)}",
            "conversation_timeout=${settings.timeout}"
        )
        if (config.source.isNotEmpty()) params.add("source=${enc(config.source)}")
        params.add("speaker_auto_assign=enabled")
        if (settings.vadGate) params.add("vad_gate=enabled")
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

    private fun enc(value: String): String = URLEncoder.encode(value, "UTF-8")
}

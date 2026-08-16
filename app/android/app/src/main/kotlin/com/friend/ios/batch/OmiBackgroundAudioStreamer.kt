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
    private val pendingFrames = OmiBackgroundAudioStreamingLifecycle(MAX_PENDING_FRAMES)
    private var socket: WebSocket? = null
    private var connecting = false
    private var connected = false
    private var activeUrl: String? = null
    private var activeConfig: Config? = null
    private var sentFrames = 0
    @Volatile
    private var lastFailureAtMs = 0L

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
            pendingFrames.invalidateSession()
        }
        clearCachedTranscriptMessages()
        socketToClose?.close(1000, reason)
    }

    fun handleCharacteristic(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray) {
        // Capture before parsing or transforming. stop()/reconfigure invalidates
        // this generation, so a callback already in flight cannot attach its
        // old BLE payload to a later re-enabled stream with the same config.
        val callbackGeneration = synchronized(lock) { pendingFrames.currentGeneration() }
        val config = loadConfig()
        if (config == null) {
            val hasActiveStream = synchronized(lock) {
                socket != null || connecting || connected || activeConfig != null
            }
            if (hasActiveStream) stop("disabled")
            return
        }
        if (OmiBleManager.isFlutterAlive && boolPref("nativeBleForegroundReady", false)) {
            val hasActiveStream = synchronized(lock) {
                socket != null || connecting || connected || activeConfig != null
            }
            if (hasActiveStream) stop("foreground_ready")
            return
        }
        if (!config.deviceId.equals(address, ignoreCase = true)) return
        if (!matches(config, serviceUuid, characteristicUuid)) return

        val frames = transformFrames(config, value)
        if (frames.isEmpty()) return

        val session = ensureSocket(config, callbackGeneration) ?: return

        for (frame in frames) {
            sendOrQueue(config, session, frame)
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
            else -> {
                Log.w(TAG, "Unsupported background BLE audio device type: ${config.deviceType}")
                emptyList()
            }
        }

    private fun ensureSocket(
        config: Config,
        callbackGeneration: Long
    ): OmiBackgroundAudioStreamingLifecycle.Session? {
        synchronized(lock) {
            // The callback may have loaded this config before a concurrent
            // policy transition. Re-read it under the stream monitor before
            // opening anything, including after the reconnect backoff check.
            if (!pendingFrames.isGenerationCurrent(callbackGeneration)) return null
            val currentConfig = loadConfig()
            if (currentConfig == null || currentConfig != config) return null

            val now = System.currentTimeMillis()
            if (now - lastFailureAtMs < RECONNECT_BACKOFF_MS) return null

            val url = buildUrl(currentConfig) ?: return null
            val request = buildRequest(url) ?: return null

            if ((connecting || connected) && activeUrl == url && activeConfig == config && socket != null) {
                return pendingFrames.currentSession()
            }

            socket?.close(1000, "reconfigure")
            socket = null
            connecting = true
            connected = false
            activeUrl = url
            val configChanged = activeConfig != currentConfig
            activeConfig = currentConfig
            sentFrames = 0
            if (configChanged) {
                pendingFrames.invalidateSession()
            }
            val session = pendingFrames.beginSession()

            Log.i(TAG, "Opening background transcription websocket (codec=${currentConfig.codec}, source=${currentConfig.source})")
            socket = client.newWebSocket(request, listener(session))
            return session
        }
    }

    private fun listener(session: OmiBackgroundAudioStreamingLifecycle.Session): WebSocketListener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            var queued = emptyList<ByteArray>()
            var closeReason: String? = null
            synchronized(lock) {
                if (webSocket != socket || !pendingFrames.isCurrent(session)) return
                val currentConfig = loadConfig()
                val policyAllowsStreaming = currentConfig != null && currentConfig == activeConfig
                if (!policyAllowsStreaming) {
                    pendingFrames.drainOnOpen(session, policyAllowsStreaming = false)
                    socket = null
                    connecting = false
                    connected = false
                    activeUrl = null
                    activeConfig = null
                    closeReason = "policy_disabled"
                } else {
                    connecting = false
                    connected = true
                    queued = pendingFrames.drainOnOpen(session, policyAllowsStreaming = true)
                }
            }
            closeReason?.let { reason ->
                Log.i(TAG, "Discarding queued background audio after policy changed")
                webSocket.close(1000, reason)
                return
            }
            Log.i(TAG, "Background transcription socket connected")
            for (frame in queued) {
                sendFrame(webSocket, frame)
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            synchronized(lock) {
                val currentConfig = loadConfig()
                if (webSocket != socket || !connected || !pendingFrames.isCurrent(session) ||
                    currentConfig == null || currentConfig != activeConfig
                ) {
                    return
                }
                cacheTranscriptMessage(text)
            }
            Log.d(TAG, "Background transcription message received (${text.length} chars)")
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(code, reason)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            synchronized(lock) {
                if (webSocket != socket || !pendingFrames.isCurrent(session)) return
                socket = null
                connecting = false
                connected = false
                activeUrl = null
                activeConfig = null
                pendingFrames.invalidateSession()
                sentFrames = 0
            }
            Log.i(TAG, "Background transcription socket closed (code=$code)")
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            synchronized(lock) {
                if (webSocket != socket || !pendingFrames.isCurrent(session)) return
                socket = null
                connecting = false
                connected = false
                activeUrl = null
                activeConfig = null
                pendingFrames.invalidateSession()
                sentFrames = 0
                lastFailureAtMs = System.currentTimeMillis()
            }
            Log.w(TAG, "Background transcription socket failed: ${t.message}")
        }
    }

    private fun sendOrQueue(
        config: Config,
        session: OmiBackgroundAudioStreamingLifecycle.Session,
        frame: ByteArray
    ) {
        var target: WebSocket? = null
        synchronized(lock) {
            // A callback can reach this method after stop() or after the
            // persisted policy/config changed. Never queue that stale audio.
            val currentConfig = loadConfig()
            if (currentConfig == null || currentConfig != config || !pendingFrames.isCurrent(session)) return

            target = if (connected && activeConfig == currentConfig) socket else null
            if (target == null) {
                queueFrameLocked(session, frame)
                return
            }
        }
        val webSocket = target ?: return
        if (!sendFrame(webSocket, frame)) {
            synchronized(lock) {
                val currentConfig = loadConfig()
                if (currentConfig == config && currentConfig == activeConfig && pendingFrames.isCurrent(session)) {
                    queueFrameLocked(session, frame)
                }
            }
        }
    }

    private fun sendFrame(webSocket: WebSocket, frame: ByteArray): Boolean = synchronized(lock) {
        // Serialize sends with stop(). Once a disabling reconcile has acquired
        // this lock and returned, no stale frame can be written to the old
        // socket. Revalidate persisted policy at the final send boundary too.
        val currentConfig = loadConfig()
        if (webSocket != socket || !connected || currentConfig == null || currentConfig != activeConfig) {
            return@synchronized false
        }

        val sent = webSocket.send(frame.toByteString())
        if (sent) {
            sentFrames += 1
            if (sentFrames % 100 == 0) {
                Log.i(TAG, "Sent $sentFrames background BLE audio frames")
            }
        }
        sent
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

    private fun clearCachedTranscriptMessages() {
        synchronized(transcriptCacheLock) {
            cachedTranscriptMessages.clear()
        }
    }

    private fun queueFrameLocked(session: OmiBackgroundAudioStreamingLifecycle.Session, frame: ByteArray) {
        pendingFrames.queueFrameIfCurrent(session, frame)
    }

    private fun loadConfig(): Config? {
        if (!boolPref("nativeBleStreamingEnabled", false)) return null
        if (!CustomSttRawAudioPolicy.allowsForwarding(stringPref("customSttConfig"))) {
            Log.i(TAG, "Raw Omi audio blocked by Custom STT forwarding policy")
            return null
        }
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

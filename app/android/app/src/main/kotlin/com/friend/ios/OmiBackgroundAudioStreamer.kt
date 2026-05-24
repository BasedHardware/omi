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
        private const val OMI_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
        private const val OMI_AUDIO_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
        private const val FRIEND_SERVICE_UUID = "1a3fd0e7-b1f3-ac9e-2e49-b647b2c4f8da"
        private const val FRIEND_AUDIO_CHAR_UUID = "01000000-1111-1111-1111-111111111111"
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
    private var lastFailureAtMs = 0L

    fun isConfiguredFor(address: String): Boolean {
        val config = loadConfig() ?: return false
        return config.deviceId.equals(address, ignoreCase = true)
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

        val frames = transformFrames(serviceUuid, characteristicUuid, value)
        if (frames.isEmpty()) return

        ensureSocket(config)

        for (frame in frames) {
            sendOrQueue(frame)
        }
    }

    private fun matches(config: Config, serviceUuid: String, characteristicUuid: String): Boolean =
        config.serviceUuid.equals(serviceUuid, ignoreCase = true) &&
            config.characteristicUuid.equals(characteristicUuid, ignoreCase = true)

    private fun transformFrames(serviceUuid: String, characteristicUuid: String, value: ByteArray): List<ByteArray> {
        val svc = serviceUuid.lowercase(Locale.US)
        val chr = characteristicUuid.lowercase(Locale.US)

        if (svc == OMI_SERVICE_UUID && chr == OMI_AUDIO_CHAR_UUID) {
            if (value.size <= 3) return emptyList()
            return listOf(value.copyOfRange(3, value.size))
        }

        if (svc == FRIEND_SERVICE_UUID && chr == FRIEND_AUDIO_CHAR_UUID) {
            if (value.size <= 5) return emptyList()
            val payload = value.copyOfRange(0, value.size - 5)
            val frames = mutableListOf<ByteArray>()
            var offset = 0
            while (offset + 30 <= payload.size) {
                frames.add(payload.copyOfRange(offset, offset + 30))
                offset += 30
            }
            return frames
        }

        return listOf(value.copyOf())
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
            sentFrames += 1
            if (sentFrames % 100 == 0) {
                Log.i(TAG, "Sent $sentFrames background BLE audio frames")
            }
        }
        return sent
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
        var base = value.trim()
        if (!base.startsWith("http://") && !base.startsWith("https://")) {
            base = "https://$base"
        }
        base = base.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
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

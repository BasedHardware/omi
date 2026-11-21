package com.friend.ios.network.endpoints

import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.await
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Instant
import java.util.concurrent.TimeUnit

/**
 * Ask Omi from the wearable and spoken answers: the Omi's question written down
 * (`APIClient+ChatExtras.swift` `transcribeVoiceMessage`) and the backend voice
 * (`synthesizeSpeech`).
 */
interface VoiceMessagesAPI {
    /**
     * `POST v2/voice-message/transcribe` (multipart `files`): the words of a spoken question,
     * nothing stored. Empty when nothing was said.
     */
    suspend fun transcribeVoiceMessage(filename: String, audio: ByteArray): String

    /** `POST v2/tts/synthesize`: [text] read by the backend voice, as MP3. */
    suspend fun synthesizeSpeech(text: String, voiceID: String?): ByteArray
}

/** The Omi's question as an upload (`VoiceMessageEvent.file` in `APIClient+DeviceActions.swift`). */
object VoiceMessageFile {
    /**
     * Flutter's `[u32 LE length][frame]...` format, named so the backend's `decode_files_to_wav`
     * picks the codec and frame size (`audio_..._fs<samples>_<epoch>.bin`).
     */
    fun file(frames: List<ByteArray>, codec: String, sampleRate: Int, frameSamples: Int, startedAt: Instant): Pair<String, ByteArray> {
        val data = ByteArrayOutputStream()
        for (frame in frames) {
            data.write(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(frame.size).array())
            data.write(frame)
        }
        return "audio_omi_${codec}_${sampleRate}_1_fs${frameSamples}_${startedAt.epochSecond}.bin" to data.toByteArray()
    }
}

internal class VoiceMessagesEndpoints(private val http: HttpCore) : VoiceMessagesAPI {
    override suspend fun transcribeVoiceMessage(filename: String, audio: ByteArray): String {
        val text = http.data(
            Method.POST, "v2/voice-message/transcribe",
            body = Body.File("files", filename, "application/octet-stream", audio),
        )
        return JsonAccess.obj(text).string("transcript")?.trim() ?: ""
    }

    override suspend fun synthesizeSpeech(text: String, voiceID: String?): ByteArray {
        val body = buildJsonObject {
            put("text", text)
            if (voiceID != null) put("voice_id", voiceID)
        }
        val request = http.request(Method.POST, "v2/tts/synthesize", body = Body.Json(body.toString()), headers = mapOf("Accept" to "audio/mpeg"))
        val client = http.client.newBuilder().callTimeout(60, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build()
        val response = try {
            client.newCall(request).await()
        } catch (e: IOException) {
            throw APIError.Transport(e.message ?: e.toString())
        }
        return response.use {
            val bytes = withContext(Dispatchers.IO) { it.body?.bytes() ?: ByteArray(0) }
            if (it.code !in 200..299) throw APIError.Http(it.code, String(bytes.take(500).toByteArray()))
            if (bytes.isEmpty()) throw APIError.Decoding("no audio")
            bytes
        }
    }
}

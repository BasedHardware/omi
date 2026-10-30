package com.friend.ios.network.customstt

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

/**
 * Port of `CustomSTTRequests.swift`: how audio goes to each provider and how its answer becomes
 * segments, as Flutter builds them (`SttProviderConfig.buildRequestConfig`, `SttResponseSchema`).
 * Pure functions, so the wire shapes test without a network.
 */
object CustomSTTRequests {
    /** The HTTP providers: one 16 kHz mono WAV per request (multipart, field `file`). */
    fun upload(config: CustomSTTConfig, wav: ByteArray, boundary: String = "omi-${UUID.randomUUID()}"): Request {
        val endpoint = config.endpoint
        if (!config.isComplete || config.provider.isLive || endpoint == null) throw CustomSTTError.Incomplete
        val body = MultipartBody.Builder(boundary).setType(MultipartBody.FORM).apply {
            fields(config).forEach { (name, value) -> addFormDataPart(name, value) }
            addFormDataPart("file", "audio.wav", wav.toRequestBody("audio/wav".toMediaType()))
        }.build()
        return Request.Builder().url(endpoint).post(body).apply {
            val key = config.apiKey
            if (key != null && config.provider.requiresAPIKey) header("Authorization", "Bearer $key")
        }.build()
    }

    /** The form fields per provider; `multi` (detect) sends no language, as the APIs expect. */
    fun fields(config: CustomSTTConfig): List<Pair<String, String>> {
        val language = config.effectiveLanguage.takeIf { it != "multi" }
        val fields = when (config.provider) {
            CustomSTTProvider.OpenAI -> mutableListOf(
                "model" to config.effectiveModel, "response_format" to "verbose_json", "timestamp_granularities[]" to "segment",
            )
            CustomSTTProvider.OpenAIDiarize -> mutableListOf(
                "model" to config.effectiveModel, "response_format" to "diarized_json", "chunking_strategy" to "auto",
            )
            CustomSTTProvider.LocalWhisper -> mutableListOf("temperature" to "0.0", "temperature_inc" to "0.2", "response_format" to "verbose_json")
            CustomSTTProvider.Custom, CustomSTTProvider.DeepgramLive -> mutableListOf()
        }
        if (language != null) fields += "language" to language
        return fields
    }

    /**
     * An HTTP answer: `segments` with times (speakers for diarize), else the whole `text` as one
     * segment spanning [duration].
     */
    fun segments(data: String, duration: Double): List<CustomSTTSegment> {
        val root = runCatching { Json.parseToJsonElement(data) as? JsonObject }.getOrNull() ?: throw CustomSTTError.Undecodable
        val speakers = mutableMapOf<String, Int>()
        val segments = root["segments"] as? JsonArray
        if (segments != null && segments.isNotEmpty()) {
            return segments.mapNotNull { element ->
                val segment = element as? JsonObject ?: return@mapNotNull null
                val text = segment.string("text").orEmpty().trim()
                if (text.isEmpty()) return@mapNotNull null
                val start = segment.number("start") ?: 0.0
                val end = segment.number("end") ?: start
                CustomSTTSegment(text, start, end, speakerNumber(segment["speaker"], speakers))
            }
        }
        val text = root.string("text").orEmpty().trim()
        return if (text.isEmpty()) emptyList() else listOf(CustomSTTSegment(text, 0.0, duration))
    }

    /** Deepgram live: `wss://api.deepgram.com/v1/listen` with linear16 at 16 kHz, `Token` auth. */
    fun deepgramSocket(config: CustomSTTConfig): Request {
        val endpoint = config.endpoint
        if (!config.isComplete || config.provider != CustomSTTProvider.DeepgramLive || endpoint == null) throw CustomSTTError.Incomplete
        val url = endpoint.newBuilder().apply {
            listOf(
                "model" to config.effectiveModel, "language" to config.effectiveLanguage, "smart_format" to "true",
                "punctuate" to "true", "diarize" to "true", "interim_results" to "false", "no_delay" to "true",
                "endpointing" to "300", "encoding" to "linear16", "sample_rate" to "16000", "channels" to "1",
            ).forEach { (name, value) -> addQueryParameter(name, value) }
        }.build()
        return Request.Builder().url(url).header("Authorization", "Token ${config.apiKey.orEmpty()}").build()
    }

    /**
     * One Deepgram message: a final `Results` turns into one segment per speaker run; anything
     * else (metadata, interim results, empty speech) is null.
     */
    fun deepgramSegments(text: String): List<CustomSTTSegment>? {
        val root = runCatching { Json.parseToJsonElement(text) as? JsonObject }.getOrNull() ?: return null
        if ((root.string("type") ?: "Results") != "Results") return null
        if ((root["is_final"] as? JsonPrimitive)?.booleanOrNull == false) return null
        val alternative = ((root["channel"] as? JsonObject)?.get("alternatives") as? JsonArray)?.firstOrNull() as? JsonObject ?: return null
        val runs = mutableListOf<CustomSTTSegment>()
        for (element in (alternative["words"] as? JsonArray).orEmpty()) {
            val word = element as? JsonObject ?: continue
            val value = word.string("punctuated_word") ?: word.string("word") ?: ""
            if (value.isEmpty()) continue
            val start = word.number("start") ?: 0.0
            val end = word.number("end") ?: start
            val speaker = (word["speaker"] as? JsonPrimitive)?.intOrNull
            val last = runs.lastOrNull()
            if (last != null && last.speaker == speaker) {
                runs[runs.size - 1] = CustomSTTSegment(last.text + " " + value, last.start, end, speaker)
            } else {
                runs += CustomSTTSegment(value, start, end, speaker)
            }
        }
        val transcript = alternative.string("transcript")
        if (runs.isEmpty() && !transcript.isNullOrEmpty()) {
            val start = root.number("start") ?: 0.0
            runs += CustomSTTSegment(transcript, start, start + (root.number("duration") ?: 0.0))
        }
        return runs.ifEmpty { null }
    }

    /** OpenAI diarize names speakers `A`, `B`..., Deepgram numbers them: both become 0, 1, ... */
    private fun speakerNumber(value: Any?, known: MutableMap<String, Int>): Int? {
        val primitive = value as? JsonPrimitive ?: return null
        if (!primitive.isString) return primitive.intOrNull
        val name = primitive.content
        if (name.isEmpty()) return null
        name.filter { it.isDigit() }.toIntOrNull()?.let { return it }
        return known.getOrPut(name) { known.size }
    }

    private fun JsonObject.string(key: String): String? = (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private fun JsonObject.number(key: String): Double? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
}

/** Port of `PCMWave`: a 16-bit mono PCM WAV container (what the HTTP providers take). */
object PCMWave {
    fun wav(pcm16: ByteArray, sampleRate: Int = 16000): ByteArray {
        val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        header.put("RIFF".toByteArray()).putInt(36 + pcm16.size).put("WAVEfmt ".toByteArray())
        header.putInt(16).putShort(1).putShort(1).putInt(sampleRate).putInt(sampleRate * 2).putShort(2).putShort(16)
        header.put("data".toByteArray()).putInt(pcm16.size)
        return header.array() + pcm16
    }
}

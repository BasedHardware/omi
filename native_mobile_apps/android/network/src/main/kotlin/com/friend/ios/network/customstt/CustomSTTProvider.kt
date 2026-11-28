package com.friend.ios.network.customstt

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Port of `CustomSTTProvider.swift`. A speech-to-text service the app talks to itself (Flutter
 * "Custom STT", `stt_provider.dart`): the phone sends the audio there and hands the words to
 * `/v4/listen` as `suggested_transcript` (`custom_stt=enabled`), so Omi's managed transcription and
 * its minutes are not used. Raw values are Flutter's `SttProvider` names, so a config saved by the
 * Flutter app still reads.
 */
enum class CustomSTTProvider(val rawValue: String) {
    /** OpenAI Whisper (`whisper-1`), 3 s chunks over HTTP. */
    OpenAI("openai"),

    /** OpenAI GPT-4o Transcribe Diarize: chunks over HTTP, with speakers. */
    OpenAIDiarize("openaiDiarize"),

    /** Deepgram Nova over a live WebSocket. */
    DeepgramLive("deepgramLive"),

    /** A self-hosted whisper.cpp server (`/inference`), no key. */
    LocalWhisper("localWhisper"),

    /** Any HTTP endpoint that takes a WAV upload and answers like OpenAI (`segments` or `text`). */
    Custom("custom"),
    ;

    val requiresAPIKey: Boolean get() = this == OpenAI || this == OpenAIDiarize || this == DeepgramLive

    /** Streams over a WebSocket; the others post a WAV every few seconds. */
    val isLive: Boolean get() = this == DeepgramLive

    /** The endpoint is the user's (`localWhisper`, `custom`). */
    val takesURL: Boolean get() = this == LocalWhisper || this == Custom

    val displayName: String
        get() = when (this) {
            OpenAI -> "OpenAI Whisper"
            OpenAIDiarize -> "OpenAI GPT-4o Transcribe Diarize"
            DeepgramLive -> "Deepgram"
            LocalWhisper -> "Local Whisper"
            Custom -> "Custom"
        }

    val models: List<String>
        get() = when (this) {
            OpenAI -> listOf("whisper-1")
            OpenAIDiarize -> listOf("gpt-4o-transcribe-diarize")
            DeepgramLive -> listOf("nova-3")
            LocalWhisper, Custom -> emptyList()
        }

    val defaultLanguage: String get() = if (this == DeepgramLive) "multi" else "en"

    /** The placeholder for `url` (`stt_provider.dart` `buildRequestConfig`). */
    val defaultURL: String? get() = if (takesURL) "http://127.0.0.1:8080/inference" else null

    /** Where the user gets a key. */
    val apiKeyURL: String?
        get() = when (this) {
            OpenAI, OpenAIDiarize -> "https://platform.openai.com/api-keys"
            DeepgramLive -> "https://console.deepgram.com/"
            LocalWhisper, Custom -> null
        }

    companion object {
        fun from(raw: String?): CustomSTTProvider? = entries.firstOrNull { it.rawValue == raw }
    }
}

/** One saved provider setup. The key lives in the secret store (`CustomSTTSettings`), never in preferences. */
data class CustomSTTConfig(
    val provider: CustomSTTProvider,
    val apiKey: String? = null,
    val model: String? = null,
    /** ISO code, or `multi` to detect. */
    val language: String? = null,
    val url: String? = null,
) {
    val effectiveModel: String get() = model?.ifEmpty { null } ?: provider.models.firstOrNull() ?: ""

    val effectiveLanguage: String get() = language?.ifEmpty { null } ?: provider.defaultLanguage

    /** Everything needed to send audio (a key when the provider needs one, a valid endpoint). */
    val isComplete: Boolean
        get() {
            if (provider.requiresAPIKey && apiKey.orEmpty().isBlank()) return false
            if (provider.takesURL) return endpoint != null
            return true
        }

    internal val endpoint: HttpUrl?
        get() = when (provider) {
            CustomSTTProvider.OpenAI, CustomSTTProvider.OpenAIDiarize -> "https://api.openai.com/v1/audio/transcriptions".toHttpUrlOrNull()
            // OkHttp takes ws(s) URLs as http(s); the request builder maps them back.
            CustomSTTProvider.DeepgramLive -> "https://api.deepgram.com/v1/listen".toHttpUrlOrNull()
            CustomSTTProvider.LocalWhisper, CustomSTTProvider.Custom -> {
                val text = url?.ifEmpty { null } ?: provider.defaultURL
                val scheme = text?.substringBefore("://", "")?.lowercase()
                if (scheme == "http" || scheme == "https") text.toHttpUrlOrNull() else null
            }
        }
}

/** A piece of transcript from a provider; times are seconds from the start of what was sent. */
data class CustomSTTSegment(
    val text: String,
    val start: Double,
    val end: Double,
    /** The provider's speaker number, when it separates speakers. */
    val speaker: Int? = null,
)

sealed class CustomSTTError(message: String) : Exception(message) {
    data object Incomplete : CustomSTTError("incomplete")
    data class Http(val status: Int) : CustomSTTError("HTTP $status")
    data object Undecodable : CustomSTTError("undecodable")
}

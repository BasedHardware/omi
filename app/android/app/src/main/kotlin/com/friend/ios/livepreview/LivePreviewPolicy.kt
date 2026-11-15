package com.friend.ios.livepreview

import java.util.Locale

/**
 * Pure policy for the Android on-device live preview (display only; never
 * the record). Engine order: the OS on-device recognizer (API 33+, language
 * already installed) here; Omi's downloaded Whisper model is the Dart-side
 * fallback; otherwise none. Never a cloud recognizer, never a model download.
 */
object LivePreviewPolicy {
    /** EXTRA_AUDIO_SOURCE and EXTRA_SEGMENTED_SESSION need Android 13. */
    const val MIN_SDK = 33

    val REASONS = setOf(
        "ok", "not_admitted", "kill_switch", "os_too_old", "os_engine_unavailable", "locale_unsupported",
        "locale_asset_missing", "speech_permission_denied", "bundled_not_installed", "bundled_not_built",
        "engine_error",
    )

    fun none(reason: String): Map<String, Any> =
        mapOf("engine" to "none", "reason" to (if (reason in REASONS && reason != "ok") reason else "engine_error"),
            "bundledInstalled" to false)

    fun running(): Map<String, Any> = mapOf("engine" to "android_on_device", "reason" to "ok", "bundledInstalled" to false)

    /** Word start points from Android 14+, independent of callback latency. */
    fun timedSpans(originMs: Long, parts: List<Pair<String, Long>>): List<Map<String, Any>> {
        if (originMs <= 0 || parts.isEmpty() || parts.all { it.second == 0L } ||
            parts.any { it.second < 0L } || parts.zipWithNext().any { it.first.second > it.second.second }) return emptyList()
        return parts.map { (text, offset) ->
            mapOf("text" to text, "startMs" to originMs + offset, "endMs" to originMs + offset + 1)
        }
    }

    /** Reason the OS engine cannot even be probed, or null when it can. */
    fun preflight(sdkInt: Int, recordAudioGranted: Boolean, onDeviceAvailable: () -> Boolean): String? = when {
        sdkInt < MIN_SDK -> "os_too_old"
        // The recognition service checks the caller's RECORD_AUDIO on every
        // startListening, including an app-supplied EXTRA_AUDIO_SOURCE. The
        // preview never prompts from the capture path.
        !recordAudioGranted -> "speech_permission_denied"
        // No on-device recognition service (e.g. no Google speech services).
        !onDeviceAvailable() -> "os_engine_unavailable"
        else -> null
    }

    /**
     * Whether a recognizer error counts toward the runtime-failure budget.
     * Silence (no match, speech timeout) only reopens the session.
     */
    fun isRuntimeFailure(error: Int): Boolean =
        error != android.speech.SpeechRecognizer.ERROR_NO_MATCH &&
            error != android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT

    /**
     * Starts a recognizer on a fresh pipe: [start] receives the read end. On
     * success the read end is closed (the service holds its own duplicate) and
     * the write end returned; if [start] throws, BOTH ends are closed and the
     * error rethrown, so a failed (re)start never leaks descriptors.
     */
    fun <T : java.io.Closeable> startOnPipe(read: T, write: T, start: (T) -> Unit): T {
        try {
            start(read)
        } catch (error: Throwable) {
            runCatching { read.close() }
            runCatching { write.close() }
            throw error
        }
        runCatching { read.close() }
        return write
    }

    /** The app's bare language code; "multi"/empty use the device language. */
    fun languageCode(language: String, deviceLanguage: String): String {
        if (language.isEmpty() || language == "multi") return deviceLanguage.lowercase(Locale.ROOT)
        return language.split('-', '_').first().lowercase(Locale.ROOT)
    }

    data class LocalePick(val tag: String?, val reason: String)

    /**
     * An installed on-device language for [code] (device tag first), else
     * whether it is merely downloadable/pending (`locale_asset_missing`) or
     * not offered on device at all (`locale_unsupported`).
     */
    fun pickLanguage(
        code: String,
        installed: List<String>,
        pending: List<String>,
        supported: List<String>,
        deviceTag: String,
    ): LocalePick {
        fun matching(tags: List<String>) = tags.filter { languageCode(it, "") == code }.sorted()
        val ready = matching(installed)
        val chosen = ready.firstOrNull { it.equals(deviceTag, ignoreCase = true) } ?: ready.firstOrNull()
        if (chosen != null) return LocalePick(chosen, "ok")
        val known = matching(pending) + matching(supported)
        return LocalePick(null, if (known.isEmpty()) "locale_unsupported" else "locale_asset_missing")
    }
}

/** Partials share the open id; a segment result settles it and opens the next. */
class LivePreviewSegmentIds(private val prefix: String) {
    private var counter = 0
    val current: String get() = "$prefix$counter"

    fun id(isFinal: Boolean): String {
        val id = current
        if (isFinal) counter++
        return id
    }
}

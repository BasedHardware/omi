package com.friend.ios.service

import com.friend.ios.persistence.Preferences
import java.util.Locale

/**
 * Port of `TranscriptionLanguage.swift`: the language code a recording is transcribed in. Two or
 * more spoken languages nova-3 can mix are sent as `multi`, otherwise the main language.
 */
object TranscriptionLanguage {
    /** Base languages nova-3 transcribes together (backend `deepgram_nova3_multi_languages`). */
    internal val mixable = setOf("en", "es", "fr", "de", "hi", "ru", "pt", "ja", "it", "nl")

    fun code(main: String, spoken: List<String>): String {
        val bases = spoken.map(::base).toSet()
        return if (bases.size >= 2 && mixable.containsAll(bases)) "multi" else main
    }

    /** Whether these languages are transcribed together when spoken in one conversation. */
    fun mixes(spoken: List<String>): Boolean = code(spoken.firstOrNull() ?: "", spoken) == "multi"

    internal fun base(code: String): String = code.split("-").first()

    /** The language the phone's recognizer listens for: the main one (it cannot mix). */
    fun recognizer(preferences: Preferences): String =
        preferences.string(Preferences.Key.UserPrimaryLanguage) ?: Locale.getDefault().language.ifEmpty { "en" }

    fun current(preferences: Preferences): String {
        val main = preferences.string(Preferences.Key.UserPrimaryLanguage) ?: Locale.getDefault().language.ifEmpty { "en" }
        return code(main, preferences.strings(Preferences.NativeKey.SpokenLanguages))
    }
}

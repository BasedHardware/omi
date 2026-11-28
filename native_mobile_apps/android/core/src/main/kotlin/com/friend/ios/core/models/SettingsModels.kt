package com.friend.ios.core.models

import java.time.Instant

/** Port of the models in `APIClient+Settings.swift`: a person Omi tells apart by voice. */
data class Person(
    val id: String,
    val name: String,
    val sampleCount: Int,
    /** Signed URLs of the saved voice samples (playable without auth headers). */
    val sampleURLs: List<String> = emptyList(),
    /** Pinned people stay out of Clean up. */
    val isPinned: Boolean = false,
    val confidence: Confidence = Confidence.Unknown,
    /** Stats, only from `GET v1/users/people?include_stats=true`. */
    val conversationCount: Int? = null,
    val talkSeconds: Double? = null,
    val lastHeardAt: Instant? = null,
) {
    /** How sure Omi is about this voice (backend `PersonConfidence`). */
    enum class Confidence(val rawValue: String) {
        Confirmed("confirmed"), Likely("likely"), Unverified("unverified"), Unknown("unknown");

        companion object {
            fun from(raw: String?): Confidence? = entries.firstOrNull { it.rawValue == raw }
        }
    }
}

data class PhoneNumber(val id: String, val number: String, val isVerified: Boolean)

/** One spoken language the backend transcribes (`GET v1/users/available-languages`). */
data class SpokenLanguage(val name: String, val code: String)

/** One assistant voice (`GET v1/tts/voices`). */
data class AssistantVoice(val id: String, val name: String)

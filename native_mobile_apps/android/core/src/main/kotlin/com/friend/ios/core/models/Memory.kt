package com.friend.ios.core.models

import java.time.Instant

/** Port of `Memory.swift`: something Omi knows about the user. */
data class Memory(
    val id: String,
    val content: String,
    val headline: String?,
    val category: String,
    val createdAt: Instant,
    val conversationID: String?,
    val visibility: Visibility = Visibility.Private,
    /** Pinned as a baseline fact Omi always keeps. */
    val isBaseline: Boolean = false,
    /** The user answered "Is this right?" (`userReview` holds the answer). */
    val reviewed: Boolean = false,
    val userReview: Boolean? = null,
    /** `{platform}_{hash}` of the phone or computer that captured it. */
    val captureDevice: String? = null,
    /** Locked behind a plan upgrade: shown, not editable. */
    val isLocked: Boolean = false,
    val veracity: Double? = null,
    val captureConfidence: Double? = null,
    /** Why it needs caution (`single_source`, `stale`, ...), as sent. */
    val uncertaintyReasons: List<String> = emptyList(),
    /** Who it is about: `user`, `third_party`, `unknown`, `legacy_assumed`. */
    val subjectAttribution: String? = null,
    val subjectName: String? = null,
    /** Where it was heard, newest first. */
    val evidence: List<Evidence> = emptyList(),
) {
    /** Who may see it: private memories stay with the user, public ones feed their persona. */
    enum class Visibility(val rawValue: String) {
        Private("private"), Public("public");

        companion object {
            fun from(raw: String?): Visibility? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    data class Evidence(val sourceType: String, val sourceID: String?, val capturedAt: Instant?)
}

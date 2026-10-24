package com.friend.ios.service.phonecalls

import com.friend.ios.network.listen.LiveSegment

/**
 * Port of `PhoneCallTranscript.swift`. The live transcript of one call. The server re-sends a
 * segment with the same id as it refines it, so segments upsert by id in arrival order;
 * translations attach to the segment they belong to (Flutter `PhoneCallProvider._handleTranscriptionMessage`).
 * Immutable here: Compose state holds the value and each change is a new one.
 */
data class PhoneCallTranscript(
    val segments: List<LiveSegment> = emptyList(),
    /** Segment id -> translated texts (the live interpreter). */
    val translations: Map<String, List<String>> = emptyMap(),
) {
    val isEmpty: Boolean get() = segments.isEmpty()

    fun merge(incoming: List<LiveSegment>): PhoneCallTranscript {
        val merged = segments.toMutableList()
        for (segment in incoming) {
            val index = merged.indexOfFirst { it.id == segment.id }
            if (index >= 0) merged[index] = segment else merged += segment
        }
        return copy(segments = merged)
    }

    /** Only for segments already shown, like Flutter (a translation never creates a line). */
    fun applyTranslations(incoming: Map<String, List<String>>): PhoneCallTranscript {
        val ids = segments.mapTo(HashSet()) { it.id }
        val known = incoming.filterKeys { it in ids }
        return if (known.isEmpty()) this else copy(translations = translations + known)
    }
}

package com.friend.ios.core.models

import java.time.Instant

/** Port of the voice-learning half of `SpeakerModels.swift`. */

/** A voice marked Not a Person (TV, podcasts) in one conversation. */
data class IgnoredVoice(
    val conversationID: String,
    val speakerID: Int,
    val conversationTitle: String,
    val ignoredAt: Instant?,
) {
    val id: String get() = "$conversationID#$speakerID"
}

/** Voice-learning switches (`v1/users/voice-profile-settings`). */
data class VoiceProfileSettings(
    /** "Ask me to tag voices": Omi asks who spoke in recent conversations. */
    val asksToTag: Boolean,
    /** "Remember voices of people you name": naming someone keeps a short voice sample. */
    val savesOtherVoices: Boolean,
)

/**
 * One conversation a person speaks in (`POST v1/conversations/search` with `speaker_id`): the few
 * fields the person page shows, so the page does not depend on the full conversation model.
 */
data class PersonConversation(val id: String, val title: String, val emoji: String?, val date: Instant)

/** Port of `KnowledgeGraph` (`APIClient+MemoryExtras.swift`): people, places and things Omi knows. */
data class KnowledgeGraph(val nodes: List<Node>, val edges: List<Edge>) {
    data class Node(
        val id: String,
        val label: String,
        /** `person`, `place`, `organization`, `thing`, `concept` (canonical data also `user`, `entity`). */
        val kind: String,
        val memoryIDs: List<String> = emptyList(),
    )

    data class Edge(val source: String, val target: String, val label: String)
}

/** Port of `ImportJob` (`APIClient+Imports.swift`): a Limitless export zip turned into conversations. */
data class ImportJob(
    val id: String,
    val status: Status,
    val totalFiles: Int? = null,
    val processedFiles: Int? = null,
    val created: Int? = null,
    val skipped: Int? = null,
    val createdAt: Instant? = null,
    val error: String? = null,
) {
    enum class Status(val rawValue: String) {
        Pending("pending"), Processing("processing"), Completed("completed"), Failed("failed"), Cancelled("cancelled");

        companion object {
            fun from(raw: String?): Status? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    val isRunning: Boolean get() = status == Status.Pending || status == Status.Processing

    /** 0...1 while the files are processed. */
    val progress: Double?
        get() {
            val total = totalFiles ?: return null
            val done = processedFiles ?: return null
            if (total <= 0) return null
            return minOf(done.toDouble() / total, 1.0)
        }
}

// Transcript labels (conversations port): `SpeakerTarget`, `SpeakerRejection`, `VoiceMatch`.

/** Who said a line: the user or one of their people. */
sealed interface SpeakerTarget {
    data object User : SpeakerTarget
    data class Person(val id: String) : SpeakerTarget
}

/** Why a label on a voice is wrong (`POST .../speakers/{id}/reject`). */
enum class SpeakerRejection(val rawValue: String) {
    NotMe("not_me"),
    NotPerson("not_person"),
    /** TV, podcast, music: Omi stops asking about this voice (it shows under Ignored voices). */
    NotAPerson("not_a_person"),
}

/** An unnamed voice in an earlier conversation that sounds like a person (`GET .../voice-matches`). */
data class VoiceMatch(
    val conversationID: String,
    val title: String,
    val startedAt: Instant?,
    val speakerID: Int,
    val talkSeconds: Double,
    val segmentIDs: List<String>,
    val clipStart: Double,
    val clipEnd: Double,
    val isStrong: Boolean,
) {
    val id: String get() = "$conversationID#$speakerID"
}

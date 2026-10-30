package com.friend.ios.core.models

/**
 * Port of `SpeakerPrompt` / `SpeakerPromptAnswer` (`SpeakerModels.swift`): one "Who is this?"
 * question about a voice in a recent conversation (`GET v1/speaker-tag-prompts`).
 */
data class SpeakerPrompt(
    val id: String,
    val kind: Kind,
    /** Backend `origin` (auto_user | auto_person | unnamed), echoed back with the answer. */
    val origin: String = "unnamed",
    val conversationID: String,
    val conversationTitle: String = "",
    val speakerID: Int,
    val segmentIDs: List<String>,
    val clipStart: Double = 0.0,
    val clipEnd: Double = 0.0,
    val excerpt: String = "",
    val suggestedPersonID: String? = null,
    val suggestedPersonName: String? = null,
    val candidates: List<Candidate> = emptyList(),
) {
    enum class Kind(val rawValue: String) {
        OwnerCheck("owner_check"), ConfirmPerson("confirm_person"), Identify("identify");

        companion object {
            fun from(raw: String?): Kind? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    data class Candidate(val id: String, val name: String)
}

sealed interface SpeakerPromptAnswer {
    data object Me : SpeakerPromptAnswer
    data object NotMe : SpeakerPromptAnswer
    data class Person(val id: String) : SpeakerPromptAnswer
    data class NewPerson(val name: String) : SpeakerPromptAnswer

    /** Not the suggested person, and the user does not say who. */
    data object SomeoneElse : SpeakerPromptAnswer
    data object NotAPerson : SpeakerPromptAnswer
    data object Skip : SpeakerPromptAnswer

    val wire: String
        get() = when (this) {
            Me -> "me"
            NotMe -> "not_me"
            is Person -> "person"
            is NewPerson -> "new_person"
            SomeoneElse -> "someone_else"
            NotAPerson -> "not_a_person"
            Skip -> "skip"
        }
}

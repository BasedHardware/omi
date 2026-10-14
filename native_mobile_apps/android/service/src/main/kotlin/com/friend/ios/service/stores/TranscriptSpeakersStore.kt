package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.SpeakerRejection
import com.friend.ios.core.models.SpeakerTarget
import com.friend.ios.core.models.VoiceMatch
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.CancellationException

/**
 * Port of `TranscriptSpeakersStore.swift`: naming the voices in one conversation's transcript
 * (Flutter `name_speaker_sheet`, `speaker_summary_action`, `earlier_voice_matches_sheet`). Edits
 * show at once and roll back if the backend refuses them; the server's answer then replaces the
 * transcript.
 */
class TranscriptSpeakersStore(private val store: ConversationDetailStore) {
    enum class Scope { Line, Voice }

    sealed interface Choice {
        data object Me : Choice
        data class PersonChoice(val person: Person) : Choice
        data class NewPerson(val name: String) : Choice
        /** TV, podcast, music: clears the label and Omi stops asking about the voice. */
        data object NotAPerson : Choice
    }

    /** Earlier conversations where the person just named seems to speak too. */
    data class Matches(val person: Person, val items: List<VoiceMatch>)

    /** A name changed: the summary may still say "Speaker 2". */
    var offersSummaryRefresh by mutableStateOf(false)
        private set
    var isRefreshingSummary by mutableStateOf(false)
        private set
    var matches: Matches? by mutableStateOf(null)
        private set
    var lastError: String? by mutableStateOf(null)
        private set
    /** Set while a save is in flight so the sheet cannot double-submit. */
    var isSaving by mutableStateOf(false)
        private set

    private val api: APIClientProtocol get() = store.api

    /** Lines with the same voice, the tapped one included. */
    fun lines(sameVoiceAs: ConversationDetail.Line): List<ConversationDetail.Line> {
        val speakerID = sameVoiceAs.speakerID ?: return listOf(sameVoiceAs)
        return store.detail?.transcript.orEmpty().filter { it.speakerID == speakerID }
    }

    /**
     * Names [line] (or its whole voice). Returns the person a new name created, so the caller can
     * refresh its people list; null otherwise.
     */
    suspend fun assign(line: ConversationDetail.Line, choice: Choice, scope: Scope): Person? {
        val detail = store.detail
        if (isSaving || detail == null) return null
        isSaving = true
        lastError = null
        try {
            val speakerID = if (scope == Scope.Voice) line.speakerID else null
            val affected = if (speakerID == null) listOf(line) else lines(line)
            val segmentIDs = affected.mapNotNull { it.segmentID }
            if (segmentIDs.isEmpty() || (choice == Choice.NotAPerson && line.speakerID == null)) {
                lastError = "missing segment ids"
                return null
            }
            var created: Person? = null
            if (choice is Choice.NewPerson) {
                try {
                    created = api.createPerson(choice.name.trim())
                } catch (e: Exception) {
                    if (e is CancellationException) throw e
                    lastError = e.toString()
                    return null
                }
            }
            val target = target(choice, created)
            val ids = affected.map { it.id }.toSet()
            store.detail = detail.copy(
                transcript = detail.transcript.map { current ->
                    if (current.id !in ids) current else when (target) {
                        SpeakerTarget.User -> current.relabeled(isUser = true, personID = null)
                        is SpeakerTarget.Person -> current.relabeled(isUser = false, personID = target.id)
                        null -> current.relabeled(isUser = false, personID = null)
                    }
                },
            )
            try {
                store.detail = send(target, line, segmentIDs, speakerID, scope)
                offersSummaryRefresh = true
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                store.detail = detail
                lastError = e.toString()
                return created
            }
            val person = created ?: (choice as? Choice.PersonChoice)?.person
            if (target is SpeakerTarget.Person && person != null && person.id == target.id) {
                loadMatches(person, detail.conversation.id)
            }
            return created
        } finally {
            isSaving = false
        }
    }

    private suspend fun send(target: SpeakerTarget?, line: ConversationDetail.Line, segmentIDs: List<String>, voice: Int?, scope: Scope): ConversationDetail {
        val id = store.conversation.id
        if (target == null) {
            return api.rejectSpeaker(
                id, line.speakerID ?: -1, SpeakerRejection.NotAPerson,
                personID = null, segmentIDs = if (scope == Scope.Line) segmentIDs else null,
            )
        }
        return api.assignSpeaker(id, segmentIDs, voice, target)
    }

    /** "Update summary with new names": the backend summarizes the conversation again. */
    suspend fun refreshSummary() {
        if (isRefreshingSummary) return
        val id = store.conversation.id
        isRefreshingSummary = true
        lastError = null
        try {
            store.detail = api.reprocessConversation(id)
            offersSummaryRefresh = false
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            lastError = e.toString()
        } finally {
            isRefreshingSummary = false
        }
    }

    /** "Is this also <name>?" for one earlier conversation. The match leaves the list once answered. */
    suspend fun answer(match: VoiceMatch, same: Boolean) {
        val current = matches ?: return
        matches = current.copy(items = current.items.filter { it.id != match.id })
        try {
            if (same) {
                api.assignSpeaker(match.conversationID, match.segmentIDs, match.speakerID, SpeakerTarget.Person(current.person.id))
            } else {
                api.rejectSpeaker(match.conversationID, match.speakerID, SpeakerRejection.NotPerson, current.person.id, null)
            }
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            matches = current
            lastError = e.toString()
        }
    }

    fun dismissMatches() {
        matches = null
    }

    /** WAV bytes of the voice in an earlier conversation (null when no audio was stored). */
    suspend fun clip(match: VoiceMatch): ByteArray? = try {
        api.speakerClip(match.conversationID, match.clipStart, match.clipEnd)
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        null
    }

    private suspend fun loadMatches(person: Person, excluding: String) {
        val found = try {
            api.voiceMatches(person.id)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            emptyList()
        }
        val items = found.filter { it.conversationID != excluding }
        matches = if (items.isEmpty()) null else Matches(person, items)
    }

    /** null for Not a Person (and for a new name that could not be created). */
    private fun target(choice: Choice, created: Person?): SpeakerTarget? = when (choice) {
        Choice.Me -> SpeakerTarget.User
        is Choice.PersonChoice -> SpeakerTarget.Person(choice.person.id)
        is Choice.NewPerson -> created?.let { SpeakerTarget.Person(it.id) }
        Choice.NotAPerson -> null
    }
}

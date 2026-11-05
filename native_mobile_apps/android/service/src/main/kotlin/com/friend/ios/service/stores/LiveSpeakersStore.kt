package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.SpeakerTarget
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.network.listen.LiveSegment
import kotlinx.coroutines.CancellationException

/**
 * Port of `LiveSpeakersStore.swift`: naming a voice in the conversation being recorded (Flutter
 * `conversation_capturing` -> `assignSpeakerToConversation`). The in-progress conversation gets the
 * same REST assignment as a finished one, the listen session hears `speaker_assigned`, and the live
 * transcript shows the name at once, also on later lines of a voice named as a whole.
 */
class LiveSpeakersStore(
    private val api: APIClientProtocol,
    private val capture: CaptureStore,
) {
    /** Who said a line: the user, a person, or nobody named yet. */
    data class Label(val isUser: Boolean, val personID: String?)

    var isSaving: Boolean by mutableStateOf(false)
        private set
    var lastError: String? by mutableStateOf(null)
        private set

    /** Lines named one by one, and voices named as a whole (they cover lines still to come). */
    private val lines = mutableStateMapOf<String, Label>()
    private val voices = mutableStateMapOf<Int, Label>()
    /** Names chosen here, for people the people list does not know yet. */
    private val names = mutableStateMapOf<String, String>()
    /** The in-progress conversation the labels belong to. */
    private var conversationID: String? by mutableStateOf(null)

    private val isCurrent: Boolean
        get() = conversationID != null && (capture.liveConversationID == null || capture.liveConversationID == conversationID)

    /** The name chosen here for [personID], if any. */
    fun name(personID: String): String? = names[personID]

    fun label(segment: LiveSegment): Label {
        if (isCurrent) {
            lines[segment.id]?.let { return it }
            segment.speakerID?.let { id -> voices[id]?.let { return it } }
        }
        return Label(segment.isUser, if (segment.isUser) null else segment.personID)
    }

    /** The live lines with the same voice, the tapped one included. */
    fun lines(sameVoiceAs: LiveSegment): List<LiveSegment> {
        val speakerID = sameVoiceAs.speakerID ?: return listOf(sameVoiceAs)
        return capture.segments.filter { it.speakerID == speakerID }
    }

    /**
     * Names [segment] (or its whole voice). Not a Person is not offered while recording. Returns
     * the person a new name created, so the caller can refresh its people list.
     */
    suspend fun assign(segment: LiveSegment, choice: TranscriptSpeakersStore.Choice, scope: TranscriptSpeakersStore.Scope): Person? {
        if (isSaving || choice == TranscriptSpeakersStore.Choice.NotAPerson) return null
        isSaving = true
        lastError = null
        try {
            val voice = if (scope == TranscriptSpeakersStore.Scope.Voice) segment.speakerID else null
            val segmentIDs = (if (voice == null) listOf(segment) else lines(sameVoiceAs = segment)).map { it.id }
            val id = currentConversationID() ?: throw APIError.Http(404, "no in-progress conversation")
            var created: Person? = null
            val (target, personName) = when (choice) {
                TranscriptSpeakersStore.Choice.Me -> SpeakerTarget.User to ""
                is TranscriptSpeakersStore.Choice.PersonChoice -> SpeakerTarget.Person(choice.person.id) to choice.person.name
                is TranscriptSpeakersStore.Choice.NewPerson -> {
                    val person = api.createPerson(choice.name.trim())
                    created = person
                    SpeakerTarget.Person(person.id) to person.name
                }
                TranscriptSpeakersStore.Choice.NotAPerson -> return null
            }
            api.assignSpeaker(id, segmentIDs, voice, target)
            apply((target as? SpeakerTarget.Person)?.id, personName, id, segmentIDs, voice)
            capture.sendSpeakerAssigned(segment.speakerID, target.wireID, personName, segmentIDs)
            return created
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            lastError = e.toString()
            return null
        } finally {
            isSaving = false
        }
    }

    private suspend fun currentConversationID(): String? = capture.liveConversationID ?: api.inProgressConversationID()

    /**
     * Records a naming: [personID] null is the user. A whole voice ([voice] set) covers its lines
     * named one by one before now.
     */
    internal fun apply(personID: String?, name: String, conversationID: String, segmentIDs: List<String>, voice: Int?) {
        if (conversationID != this.conversationID) {
            lines.clear()
            voices.clear()
            this.conversationID = conversationID
        }
        val label = Label(isUser = personID == null, personID = personID)
        if (personID != null && name.isNotEmpty()) names[personID] = name
        if (voice != null) {
            voices[voice] = label
            // Lines of this voice named one by one before now follow the voice.
            segmentIDs.forEach { lines.remove(it) }
        } else {
            segmentIDs.forEach { lines[it] = label }
        }
    }
}

/** Flutter sends `user` for the wearer. */
private val SpeakerTarget.wireID: String
    get() = when (this) {
        SpeakerTarget.User -> "user"
        is SpeakerTarget.Person -> id
    }

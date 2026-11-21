package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.IgnoredVoice
import com.friend.ios.core.models.SpeakerPrompt
import com.friend.ios.core.models.SpeakerPromptAnswer
import com.friend.ios.core.models.VoiceProfileSettings
import com.friend.ios.network.APIClientProtocol

/**
 * Port of `VoicesStore.swift` (the Settings half): the voice-learning switches and the voices
 * marked Not a Person (Flutter `voice_profile_settings_section`, `ignored_voices_sheet`). Changes
 * apply at once and roll back. Home's "Who is this?" prompts follow (and-onboarding).
 */
class VoicesStore(private val api: APIClientProtocol) {
    // MARK: Prompts (and-onboarding)

    /** Voices to confirm from recent conversations, the next one first. */
    var prompts: List<SpeakerPrompt> by mutableStateOf(emptyList())
        private set
    private val shownIDs = HashSet<String>()

    val currentPrompt: SpeakerPrompt? get() = prompts.firstOrNull()

    suspend fun loadPrompts() {
        runCatching { api.speakerPrompts() }.getOrNull()?.let { prompts = it }
    }

    /** The card is on screen: tells the backend once per set (starts its daily cooldown). */
    suspend fun promptsShown() {
        val fresh = prompts.map { it.id }.filter { it !in shownIDs }
        if (fresh.isEmpty()) return
        shownIDs.addAll(fresh)
        runCatching { api.markSpeakerPromptsShown(fresh) }
    }

    suspend fun answer(prompt: SpeakerPrompt, answer: SpeakerPromptAnswer) {
        val previous = prompts
        prompts = prompts.filter { it.id != prompt.id }
        attempt({ api.answerSpeakerPrompt(prompt, answer) }) { prompts = previous }
    }

    /** Closed without answering: the card goes away and Omi asks less often. */
    suspend fun dismissPrompts() {
        val previous = prompts
        prompts = emptyList()
        attempt({ api.dismissSpeakerPrompts() }) { prompts = previous }
    }

    suspend fun clip(prompt: SpeakerPrompt): ByteArray? =
        runCatching { api.speakerClip(prompt.conversationID, prompt.clipStart, prompt.clipEnd) }.getOrNull()

    private suspend fun attempt(request: suspend () -> Unit, rollback: () -> Unit) {
        lastError = null
        try {
            request()
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            rollback()
            lastError = e.toString()
        }
    }

    var settings: VoiceProfileSettings? by mutableStateOf(null)
        private set
    var ignored: List<IgnoredVoice> by mutableStateOf(emptyList())
        private set
    var ignoredLoaded: Boolean by mutableStateOf(false)
        private set
    var lastError: String? by mutableStateOf(null)
        private set

    // MARK: Settings

    suspend fun loadSettings() {
        runCatching { api.voiceProfileSettings() }.getOrNull()?.let { settings = it }
    }

    suspend fun setAsksToTag(value: Boolean) {
        update({ it.copy(asksToTag = value) }) { api.updateVoiceProfileSettings(value, null) }
        if (!value) prompts = emptyList()
    }

    suspend fun setSavesOtherVoices(value: Boolean) {
        update({ it.copy(savesOtherVoices = value) }) { api.updateVoiceProfileSettings(null, value) }
    }

    // MARK: Ignored voices

    suspend fun loadIgnored() {
        runCatching { api.ignoredVoices() }.getOrNull()?.let { ignored = it }
        ignoredLoaded = true
    }

    /** Undo Not a Person: Omi may ask about this voice again. */
    suspend fun restore(voice: IgnoredVoice) {
        val previous = ignored
        ignored = ignored.filter { it.id != voice.id }
        lastError = null
        try {
            api.restoreIgnoredVoice(voice.conversationID, voice.speakerID)
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            ignored = previous
            lastError = e.toString()
        }
    }

    private suspend fun update(change: (VoiceProfileSettings) -> VoiceProfileSettings, send: suspend () -> VoiceProfileSettings) {
        val previous = settings ?: return
        settings = change(previous)
        lastError = null
        try {
            settings = send()
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            settings = previous
            lastError = e.toString()
        }
    }
}

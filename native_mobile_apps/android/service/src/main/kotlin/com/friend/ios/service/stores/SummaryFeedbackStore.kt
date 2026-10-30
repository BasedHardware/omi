package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.ConversationFeedbackKind
import com.friend.ios.core.models.ConversationScreenshot
import com.friend.ios.core.models.SummaryFeedbackReason
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import kotlinx.coroutines.CancellationException
import java.security.MessageDigest
import java.util.UUID

/**
 * Port of `SummaryFeedbackStore.swift`: "Was this helpful?" under Omi's own summary, or "What
 * issues did you experience?" about a finished recording (Flutter `SummaryFeedbackPrompt`,
 * `RecordingQualityFeedbackPrompt` and `FeedbackPromptPolicy`): one question per conversation, a
 * quarter of conversations, at most once a week across both questions, once per conversation.
 */
class SummaryFeedbackStore(
    private val api: APIClientProtocol,
    private val preferences: Preferences?,
    internal val conversationID: String,
    private val now: () -> Long = System::currentTimeMillis,
) {
    enum class State {
        Hidden,
        Asking,
        Sending,
        /** The answer was stored; the row says thanks for a moment. */
        Thanked,
        /** Not stored; the row stays so the user can try again. */
        Failed,
    }

    var state by mutableStateOf(State.Hidden)
        private set
    /** What the row asks about, chosen when it starts. */
    var kind by mutableStateOf(ConversationFeedbackKind.Summary)
        private set

    /** Reused when a send is retried (`feedback_id`). */
    private val feedbackID = UUID.randomUUID().toString().uppercase()

    /**
     * Shows the row when the conversation is sampled, not answered yet, and none showed this week.
     * Only Omi's own summary asks about the summary (an app's result does not); a finished
     * recording with audio asks about the recording.
     */
    fun start(hasOwnSummary: Boolean, hasRecording: Boolean = false) {
        if (state != State.Hidden) return
        val kind = kind(conversationID, hasOwnSummary, hasRecording) ?: return
        if (!eligible) return
        this.kind = kind
        state = State.Asking
        preferences?.set(Preferences.NativeKey.FeedbackPromptLastShown, String.format(java.util.Locale.ROOT, "%.3f", now() / 1000.0))
    }

    /** +1 ("All good") or -1 with a reason. */
    suspend fun send(helpful: Boolean, reason: SummaryFeedbackReason? = null) {
        if (!(state == State.Asking || state == State.Failed)) return
        state = State.Sending
        val stored = try {
            api.sendConversationFeedback(conversationID, kind, helpful, if (helpful) null else reason, feedbackID)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            false
        }
        if (!stored) {
            state = State.Failed
            return
        }
        remember()
        state = State.Thanked
    }

    /** The close button: nothing is sent, the conversation does not ask again. */
    fun dismiss() {
        remember()
        state = State.Hidden
    }

    /** The row finished thanking. */
    fun finish() {
        if (state == State.Thanked) state = State.Hidden
    }

    internal val eligible: Boolean
        get() {
            if (conversationID.isEmpty() || conversationID.length > 256 || !sampled(conversationID)) return false
            val last = preferences?.string(Preferences.NativeKey.FeedbackPromptLastShown)?.toDoubleOrNull()
            if (last != null && now() / 1000.0 - last < cooldown) return false
            return conversationID !in (preferences?.strings(Preferences.NativeKey.FeedbackPromptDone) ?: emptyList())
        }

    private fun remember() {
        val preferences = preferences ?: return
        val done = preferences.strings(Preferences.NativeKey.FeedbackPromptDone).filter { it != conversationID } + conversationID
        preferences.set(Preferences.NativeKey.FeedbackPromptDone, done.takeLast(remembered))
    }

    companion object {
        const val sampleFraction = 0.25
        const val cooldown = 7.0 * 24 * 3600
        const val remembered = 64

        /**
         * Which question a conversation asks (Flutter `feedbackPromptKindForTarget`): the one it can
         * ask, and with both, bit 0 of byte 4 of SHA-256(id), a byte the sampling does not read.
         */
        fun kind(id: String, hasSummary: Boolean, hasRecording: Boolean): ConversationFeedbackKind? = when {
            !hasSummary && !hasRecording -> null
            !hasRecording -> ConversationFeedbackKind.Summary
            !hasSummary -> ConversationFeedbackKind.Recording
            id.isEmpty() || id.length > 256 -> null
            else -> if (digest(id)[4].toInt() and 1 == 0) ConversationFeedbackKind.Summary else ConversationFeedbackKind.Recording
        }

        private fun digest(id: String): ByteArray = MessageDigest.getInstance("SHA-256").digest(id.toByteArray(Charsets.UTF_8))

        /** The first four bytes of SHA-256(id) as a fraction of 2^32, below the sample fraction. */
        fun sampled(id: String): Boolean {
            val digest = digest(id)
            val bucket = digest.take(4).fold(0L) { acc, byte -> (acc shl 8) or (byte.toLong() and 0xff) }
            return bucket.toDouble() / 4_294_967_296.0 < sampleFraction
        }
    }
}

/** "What was on screen": a meeting's screenshots, with delete (Flutter `conversation_screenshots_section`). */
class ConversationScreenshotsStore(private val api: APIClientProtocol, private val conversationID: String) {
    var screenshots: List<ConversationScreenshot> by mutableStateOf(emptyList())
        private set
    var failedToDelete by mutableStateOf(false)
        private set

    suspend fun load() {
        try {
            screenshots = api.conversationScreenshots(conversationID)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
        }
    }

    suspend fun delete(screenshot: ConversationScreenshot) {
        failedToDelete = false
        try {
            screenshots = api.deleteConversationScreenshot(conversationID, screenshot.id)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            failedToDelete = true
        }
    }
}

// The detail page makes these from the long-lived list store (its client and preferences).

fun ConversationsStore.makeTemplatesStore(): SummaryTemplatesStore = SummaryTemplatesStore(api, preferences)

fun ConversationsStore.makeFeedbackStore(conversationID: String): SummaryFeedbackStore =
    SummaryFeedbackStore(api, preferences, conversationID)

fun ConversationsStore.makeScreenshotsStore(conversationID: String): ConversationScreenshotsStore =
    ConversationScreenshotsStore(api, conversationID)

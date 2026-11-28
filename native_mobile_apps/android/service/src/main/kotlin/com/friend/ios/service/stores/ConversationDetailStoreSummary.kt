package com.friend.ios.service.stores

import com.friend.ios.network.APIError
import kotlinx.coroutines.CancellationException

// Port of `ConversationDetailStore+Summary.swift`: editing the saved summary in place
// (`PATCH v1/conversations/{id}/summary`).

/** Why the summary on screen could not be saved. The screen turns each case into words. */
sealed interface SummaryEditFailure {
    /** The conversation has no result from that app any more (`app_result_not_found`). */
    data object AppResultGone : SummaryEditFailure

    /** More than one result from that app, so the backend cannot tell which one to edit (`app_result_ambiguous`). */
    data object AppResultAmbiguous : SummaryEditFailure

    /** The conversation itself is gone: it was deleted while its summary was open. */
    data object ConversationGone : SummaryEditFailure

    /** The device could not reach Omi. */
    data object Offline : SummaryEditFailure

    /** Nobody is signed in. */
    data object SignedOut : SummaryEditFailure

    /** Any other refusal, with the HTTP status when the response had one. */
    data class Refused(val status: Int?) : SummaryEditFailure

    companion object {
        /**
         * `editingAppResult` tells the backend's two 404s apart: it answers 404 both when the app's
         * result is gone ("App summary not found for this conversation") and when the conversation
         * itself is ("Conversation not found").
         */
        fun of(error: Throwable, editingAppResult: Boolean): SummaryEditFailure = when {
            error is APIError.Http && (error.status == 409 || error.body.contains("app_result_ambiguous")) -> AppResultAmbiguous
            error is APIError.Http && (error.status == 404 || error.body.contains("app_result_not_found")) ->
                if (editingAppResult) AppResultGone else ConversationGone
            error is APIError.Http -> Refused(error.status)
            error is APIError.Transport -> Offline
            error is APIError.NotSignedIn -> SignedOut
            else -> Refused(null)
        }
    }
}

/** What one attempt at editing the summary did. */
sealed interface SummaryEditOutcome {
    data object Saved : SummaryEditOutcome

    /**
     * Nothing was sent: the text is empty, it is what the summary already shows, or the summary
     * cannot be edited.
     */
    data object Unchanged : SummaryEditOutcome

    data class Failed(val failure: SummaryEditFailure) : SummaryEditOutcome
}

/**
 * Whether the summary on screen can be edited in place: Omi's own summary, or an app's result that
 * carries the app id the PATCH addresses. A result from an app that sent no id stays read-only,
 * because the request could not name it.
 */
val ConversationDetailStore.canEditSummary: Boolean
    get() {
        val detail = detail ?: return false
        return detail.summaryIsOmiOwn || detail.summaryAppID != null
    }

/**
 * Edits the summary in place (`PATCH v1/conversations/{id}/summary`): the new text shows at once and
 * the old one comes back when the backend refuses. Editing Omi's own summary drops the generated
 * sections on the backend, so the gist goes with them.
 */
suspend fun ConversationDetailStore.editSummary(text: String): SummaryEditOutcome {
    val text = text.trim()
    val current = detail ?: return SummaryEditOutcome.Unchanged
    if (text.isEmpty() || text == current.summary || !canEditSummary) return SummaryEditOutcome.Unchanged
    val appID = if (current.summaryIsOmiOwn) null else current.summaryAppID
    val previous = current.summary to current.gist
    detail = current.copy(summary = text, gist = if (appID == null) null else current.gist)
    return try {
        api.updateConversationSummary(conversation.id, appID, text)
        SummaryEditOutcome.Saved
    } catch (e: Exception) {
        if (e is CancellationException) throw e
        detail = detail?.copy(summary = previous.first, gist = previous.second)
        SummaryEditOutcome.Failed(SummaryEditFailure.of(e, editingAppResult = appID != null))
    }
}

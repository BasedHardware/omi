package com.friend.ios.core.models

import java.time.Duration
import java.time.Instant

/**
 * Port of `Conversation.swift`: a captured conversation, reduced to what the app renders.
 * Adapted from the generated `OmiAPI.Conversation` wire type in network; screens never see wire types.
 */
data class Conversation(
    val id: String,
    val title: String,
    val overview: String,
    val emoji: String?,
    val category: String?,
    val createdAt: Instant,
    val startedAt: Instant?,
    val finishedAt: Instant?,
    val status: Status,
    val isStarred: Boolean,
    val actionItemCount: Int,
    val folderID: String? = null,
    val visibility: Visibility = Visibility.Private,
    /** Behind the paywall: it cannot be merged or moved. */
    val isLocked: Boolean = false,
    /** The summary failed and the backend can try again (`summary_retryable`). */
    val summaryRetryable: Boolean = false,
    /** Where it was recorded (location allowed at the time). */
    val location: ConversationLocation? = null,
    /** Omi judged it not worth keeping (shown only when the list includes discarded ones). */
    val isDiscarded: Boolean = false,
    /**
     * Other devices recorded the same moment (`capture_group`): the group, and the recording the
     * list shows for it.
     */
    val captureGroupID: String? = null,
    val captureGroupPrimaryID: String? = null,
    /** Who took part: the summary's participants, then the linked calendar event's attendees. */
    val people: List<ConversationPerson> = emptyList(),
) {
    enum class Status { InProgress, Processing, Merging, Completed, Failed, Unknown }

    /** Who can open the conversation: only the owner, or anyone with its link. */
    enum class Visibility(val rawValue: String) { Private("private"), Shared("shared"), Public("public") }

    /** When the conversation happened (start if known, else creation). */
    val date: Instant get() = startedAt ?: createdAt

    /** Seconds. */
    val duration: Double?
        get() {
            val start = startedAt ?: return null
            val end = finishedAt ?: return null
            if (!end.isAfter(start)) return null
            return Duration.between(start, end).toMillis() / 1000.0
        }

    /** The summary did not come out: failed, or finished without one while the backend offers a retry. */
    val summaryFailed: Boolean get() = status == Status.Failed || (status == Status.Completed && summaryRetryable)

    /** The backend merges only finished, unlocked conversations (`validate_merge_compatibility`). */
    val canMerge: Boolean get() = status == Status.Completed && !isLocked

    companion object
}

/** Someone in a conversation, as far as the backend knows them (any field may be missing). */
data class ConversationPerson(val name: String?, val email: String?, val organization: String?)

package com.friend.ios.core.models

import java.time.Instant

// Port of `Agent.swift`: workstreams, recommendations and the workstream address.

/** A server-side record of Omi working on one task (backend workstreams). */
data class Workstream(
    val id: String,
    val title: String,
    val status: Status,
    val summary: String?,
    val events: List<Event>,
    /** When anything last changed, and when the work last moved forward (backend fields). */
    val updatedAt: Instant? = null,
    val lastProgressAt: Instant? = null,
) {
    enum class Status(val rawValue: String) {
        Open("open"), Paused("paused"), Completed("completed"), Archived("archived"), Unknown("unknown");

        companion object {
            fun from(rawValue: String): Status = entries.firstOrNull { it.rawValue == rawValue } ?: Unknown
        }
    }

    data class Event(
        val id: String,
        val kind: String,
        val summary: String,
        val createdAt: Instant?,
        /** Position in the workstream's log (1 = first). */
        val sequence: Int = 0,
        val evidence: List<Evidence> = emptyList(),
    ) {
        /** An event's `evidence_refs` (kind `chat_message`, `external` ...). */
        data class Evidence(val kind: String, val id: String)
    }

    /** The newest moment anything happened on it (an event, an update, progress). */
    val lastActivityAt: Instant?
        get() = (listOf(updatedAt, lastProgressAt) + events.map { it.createdAt }).filterNotNull().maxOrNull()
}

/** One "what matters now" recommendation (backend `models/task_recommendation.py` `Recommendation`). */
data class Recommendation(
    /** The intervention id (feedback names it). */
    val id: String,
    val headline: String,
    val whyNow: String,
    /** The next action in the backend's words ("Send Anna the Thursday follow-up"). */
    val action: String,
    val taskID: String?,
    val workstreamID: String? = null,
    /** The goal or workstream it belongs to, when the backend knows one. */
    val goalLabel: String? = null,
    /** A second way to act, `verb:text` on the wire (`reschedule:Send proof of income`). */
    val alternativeAction: String? = null,
    /** One line on where it comes from ("Created directly by you.", "Due in 2 days."). */
    val evidencePreview: String = "",
    val evidence: List<Evidence> = emptyList(),
    /** Feedback addresses this subject (a task, a candidate, a workstream ...). */
    val feedbackSubjectKind: String = "task",
    val feedbackSubjectID: String = taskID ?: id,
    /** Stable across evaluations of the same thing: what the app hides after a decision. */
    val dedupeKey: String = id,
    /** After this the recommendation is stale and the backend has to be asked again. */
    val expiresAt: Instant? = null,
) {
    /**
     * What the user decided about a recommendation; each one goes back as task-intelligence
     * feedback, so the backend stops (or pauses) showing it.
     */
    enum class Decision {
        /** "Omi takes over" or "Do it". */
        DoNow,
        /** Show it again tomorrow. */
        Later,
        /** "Not now": the backend keeps it away for a month. */
        Dismiss,
        /** The user did it. */
        Complete,
        /** It was dealt with elsewhere (the backend proposes completing the task). */
        AlreadyHandled,
    }

    /** Where a recommendation comes from (`EvidenceRef`: kind `conversation`, `chat_message`, `external` ...). */
    data class Evidence(val kind: String, val id: String)

    /** The verb of `alternativeAction` (`reschedule`), when it is coded that way. */
    val alternativeVerb: String?
        get() {
            val alternative = alternativeAction ?: return null
            val colon = alternative.indexOf(':')
            if (colon < 0) return null
            val verb = alternative.substring(0, colon)
            return if (verb.isNotEmpty() && verb.all { it.isLetter() || it == '_' }) verb else null
        }

    /** Conversations the backend cites as the source. */
    val conversationIDs: List<String> get() = evidence.filter { it.kind == "conversation" }.map { it.id }

    fun isExpired(at: Instant): Boolean = expiresAt?.let { !it.isAfter(at) } ?: false
}

/**
 * Addresses a workstream for writes: its id plus the account generation the backend requires
 * on every task-intelligence mutation (`X-Account-Generation`).
 */
data class WorkstreamRef(val id: String, val generation: Int)

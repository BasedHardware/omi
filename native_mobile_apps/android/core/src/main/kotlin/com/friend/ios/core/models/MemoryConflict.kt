package com.friend.ios.core.models

import java.time.Instant

/**
 * Port of `MemoryConflict.swift`: a memory the backend holds back because it contradicts what Omi
 * already knows (backend `models/memory_review.py`, `GET v3/memories/review-queue`): the new
 * candidate and the memories it conflicts with. The user decides which is right.
 */
data class MemoryConflict(
    /** `review_id`. */
    val id: String,
    /** The candidate's memory id (`fact_id`). */
    val factID: String,
    /** What Omi heard now. */
    val candidate: String,
    /** The memories it contradicts. */
    val conflictsWith: List<String>,
    val createdAt: Instant?,
) {
    /** How a conflict is resolved (`POST v3/memories/review-queue/{id}/resolve`). */
    enum class Decision(val rawValue: String) {
        /** The new candidate is right (it replaces the earlier ones). */
        Accept("accept"),

        /** The new candidate is wrong (the earlier memory stays). */
        Reject("reject"),
    }
}

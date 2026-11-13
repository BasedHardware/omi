package com.friend.ios.service.stores

import com.friend.ios.core.models.Memory
import com.friend.ios.core.models.MemoryConflict

/**
 * Port of `MemoriesStore+Review.swift`.
 *
 * Why Omi asks about a memory, which decides how the question is put (the words live in the app:
 * `MemoryReviewSheet`). Only the backend's own doubts and conflicts lead to a question, never "is
 * every new memory right?".
 */
sealed interface MemoryReviewQuestion {
    /** Two versions of the same fact: which is right (or neither)? [earlier] is null when the earlier memory is not loaded. */
    data class WhichIsRight(val earlier: String?, val now: String) : MemoryReviewQuestion

    /** The backend thinks it is about someone else (`third_party_subject`). */
    data class AboutSomeoneElse(val name: String?) : MemoryReviewQuestion

    /** It may be out of date (`stale`). */
    data object StillTrue : MemoryReviewQuestion

    /** Heard once and not clearly (`low_capture_signal`, with `single_source`). */
    data object HeardOnce : MemoryReviewQuestion

    /** Not clearly heard (`low_capture_signal` from more than one source). */
    data object Unclear : MemoryReviewQuestion
}

/** One question in the review flow. */
sealed interface MemoryReviewItem {
    /** A memory with a doubt; [earlier] is the memory it contradicts, when there is one. */
    data class ForMemory(val memory: Memory, val reviewQuestion: MemoryReviewQuestion, val earlier: Memory?) : MemoryReviewItem

    /** A conflict the backend holds back (review queue); [earlier] is the first conflicting memory. */
    data class Conflict(val conflict: MemoryConflict, val earlier: Memory?) : MemoryReviewItem

    val id: String
        get() = when (this) {
            is ForMemory -> "memory.${memory.id}"
            is Conflict -> "conflict.${conflict.id}"
        }

    val question: MemoryReviewQuestion
        get() = when (this) {
            is ForMemory -> reviewQuestion
            is Conflict -> MemoryReviewQuestion.WhichIsRight(earlier?.content, conflict.candidate)
        }
}

/** The user's answer. */
sealed interface MemoryReviewAnswer {
    data object Yes : MemoryReviewAnswer
    data object No : MemoryReviewAnswer
    data class Edit(val text: String) : MemoryReviewAnswer

    /** Two versions: the earlier one, the new one, or neither. */
    data object KeepEarlier : MemoryReviewAnswer
    data object KeepNew : MemoryReviewAnswer
    data object Neither : MemoryReviewAnswer
}

/** Which memories have a reason to be reviewed and how to ask (pure, so it is testable). */
object MemoryReviewRule {
    /**
     * The backend's doubts that are worth a question. `single_source` alone is nearly every memory
     * (one conversation), so it only shapes the wording.
     */
    internal val askingReasons = setOf("contradicted_by", "third_party_subject", "stale", "low_capture_signal")

    fun needsReview(memory: Memory): Boolean {
        if (memory.reviewed || memory.isLocked || memory.isBaseline || memory.category == "manual") return false
        return memory.uncertaintyReasons.any { reasonName(it) in askingReasons }
    }

    /**
     * The question for a memory that needs review; null otherwise. A contradiction wins, then who
     * it is about, then age, then how clearly it was heard.
     */
    fun question(memory: Memory, among: List<Memory>): Pair<MemoryReviewQuestion, Memory?>? {
        if (!needsReview(memory)) return null
        val reasons = memory.uncertaintyReasons.map(::reasonName)
        if ("contradicted_by" in reasons) {
            val earlier = contradictedID(memory)?.let { id -> among.firstOrNull { it.id == id } }
            return MemoryReviewQuestion.WhichIsRight(earlier?.content, memory.content) to earlier
        }
        if ("third_party_subject" in reasons) return MemoryReviewQuestion.AboutSomeoneElse(memory.subjectName) to null
        if ("stale" in reasons) return MemoryReviewQuestion.StillTrue to null
        return (if ("single_source" in reasons) MemoryReviewQuestion.HeardOnce else MemoryReviewQuestion.Unclear) to null
    }

    /** `contradicted_by` may carry the other memory's id (`contradicted_by:<id>`). */
    internal fun reasonName(reason: String): String = reason.split(":", limit = 2).first()

    internal fun contradictedID(memory: Memory): String? = memory.uncertaintyReasons.firstNotNullOfOrNull { reason ->
        val parts = reason.split(":", limit = 2)
        if (parts.size == 2 && parts[0] == "contradicted_by") parts[1] else null
    }

    internal fun priority(question: MemoryReviewQuestion): Int = when (question) {
        is MemoryReviewQuestion.WhichIsRight -> 0
        is MemoryReviewQuestion.AboutSomeoneElse -> 1
        MemoryReviewQuestion.StillTrue -> 2
        MemoryReviewQuestion.HeardOnce, MemoryReviewQuestion.Unclear -> 3
    }
}

/**
 * What the review flow asks, in order: the backend's held-back conflicts, then memories with a
 * doubt (contradictions first), newest first within each.
 */
val MemoriesStore.reviewQueue: List<MemoryReviewItem>
    get() {
        val byID = memories.associateBy { it.id }
        val conflicts = reviewConflicts.map { conflict ->
            MemoryReviewItem.Conflict(conflict, conflict.conflictsWith.firstNotNullOfOrNull { byID[it] })
        }
        val doubts = memories.mapNotNull { memory ->
            val (question, earlier) = MemoryReviewRule.question(memory, memories) ?: return@mapNotNull null
            memory to MemoryReviewItem.ForMemory(memory, question, earlier)
        }
            .sortedWith(compareBy<Pair<Memory, MemoryReviewItem>> { MemoryReviewRule.priority(it.second.question) }.thenByDescending { it.first.createdAt })
            .map { it.second }
        return conflicts + doubts
    }

/** How many questions wait; zero means no review entry at all. */
val MemoriesStore.reviewCount: Int
    get() = reviewConflicts.size + memories.count(MemoryReviewRule::needsReview)

/** The backend's pending conflicts. A failure leaves the last known ones. */
suspend fun MemoriesStore.loadReviewQueue() {
    runCatching { api.memoryReviewQueue() }.getOrNull()?.let { reviewConflicts = it }
}

/**
 * Applies an answer: a memory's verdict goes to `v3/memories/{id}/review` (an edit saves the fix
 * first), a held-back conflict to the review queue's resolve.
 */
suspend fun MemoriesStore.answer(item: MemoryReviewItem, answer: MemoryReviewAnswer) {
    when (item) {
        is MemoryReviewItem.ForMemory -> {
            val memory = item.memory
            val earlier = item.earlier
            when (answer) {
                MemoryReviewAnswer.Yes, MemoryReviewAnswer.KeepNew -> {
                    review(memory.id, isRight = true)
                    if (answer == MemoryReviewAnswer.KeepNew && earlier != null) review(earlier.id, isRight = false)
                }
                MemoryReviewAnswer.No, MemoryReviewAnswer.KeepEarlier -> review(memory.id, isRight = false)
                is MemoryReviewAnswer.Edit -> {
                    edit(memory.id, answer.text)
                    review(memory.id, isRight = true)
                }
                MemoryReviewAnswer.Neither -> {
                    review(memory.id, isRight = false)
                    if (earlier != null) review(earlier.id, isRight = false)
                }
            }
        }
        is MemoryReviewItem.Conflict -> {
            val conflict = item.conflict
            reviewConflicts = reviewConflicts.filter { it.id != conflict.id }
            val decision = if (answer == MemoryReviewAnswer.KeepNew || answer == MemoryReviewAnswer.Yes) MemoryConflict.Decision.Accept else MemoryConflict.Decision.Reject
            try {
                api.resolveMemoryConflict(conflict.id, decision)
                // Neither: the earlier ones go too.
                if (answer == MemoryReviewAnswer.Neither) {
                    for (id in conflict.conflictsWith) if (memories.any { it.id == id }) review(id, isRight = false)
                }
            } catch (e: Exception) {
                lastError = e.toString()
                reviewConflicts = reviewConflicts + conflict
            }
        }
    }
}

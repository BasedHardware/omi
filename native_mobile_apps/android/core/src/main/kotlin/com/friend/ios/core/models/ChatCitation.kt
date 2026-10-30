package com.friend.ios.core.models

import java.time.Instant

/**
 * Port of `ChatCitation.swift`: a source chip under an answer ("Q4 roadmap · 14:05"): a
 * conversation the answer drew on, at the moment it came from when the backend said which
 * (evidence), else at its start.
 */
data class ChatCitation(
    val conversationID: String,
    val title: String,
    val emoji: String?,
    /** When it was said: the conversation's start plus the moment's offset (null when unknown). */
    val time: Instant?,
    /** Seconds from the conversation's start, for opening it at that moment. */
    val offset: Double?,
) {
    val id: String get() = "$conversationID|${offset?.toInt()?.toString() ?: ""}"
}

/**
 * Every conversation the answer cites, once per moment: evidence first (it knows the moment),
 * then the referenced conversations evidence did not cover. At most [limit].
 */
fun ChatMessage.citations(limit: Int = 6): List<ChatCitation> {
    val result = mutableListOf<ChatCitation>()
    val seen = mutableSetOf<String>()
    val covered = mutableSetOf<String>()
    // The first reference per conversation wins.
    val byID = LinkedHashMap<String, ChatMessage.Reference>().also { map -> references.forEach { map.putIfAbsent(it.conversationID, it) } }
    for (item in evidence) {
        if (!item.opensConversation) continue
        val id = item.conversationID ?: continue
        val reference = byID[id]
        val offset = if (item.kind == ChatEvidence.Kind.ConversationSegment) item.startMs?.let { it / 1000.0 } else null
        val citation = ChatCitation(
            conversationID = id,
            title = reference?.title?.takeIf { it.isNotEmpty() } ?: item.title ?: "",
            emoji = reference?.emoji,
            time = reference?.createdAt?.plusMillis(((offset ?: 0.0) * 1000).toLong()),
            offset = offset,
        )
        covered.add(id)
        if (seen.add(citation.id)) result.add(citation)
    }
    for (reference in references) {
        if (reference.conversationID in covered) continue
        val citation = ChatCitation(reference.conversationID, reference.title, reference.emoji, reference.createdAt, null)
        if (seen.add(citation.id)) result.add(citation)
    }
    return result.take(limit)
}

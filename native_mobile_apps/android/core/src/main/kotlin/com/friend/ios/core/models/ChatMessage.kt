package com.friend.ios.core.models

import java.time.Instant

/** Port of `ChatMessage.swift`: one message of the chat with Omi. */
data class ChatMessage(
    val id: String,
    val text: String,
    val sender: Sender,
    val createdAt: Instant,
    /** Progress steps the agent reported while answering ("Searching the web"). */
    val steps: List<String> = emptyList(),
    /** Conversations the answer drew on. */
    val references: List<Reference> = emptyList(),
    /** Set when this answer did not come through as a reply (the UI words it). */
    val failure: Failure? = null,
    /** The backend's id once the message is stored (a streamed answer keeps its local `id`). */
    val serverID: String? = null,
    /** The user's rating: 1 helpful, -1 not helpful, null none. */
    val rating: Int? = null,
    /** One grounded next question the answer invites (a `followUp` content block). */
    val followUp: String? = null,
    /** A chart the answer draws (`chart_data`). */
    val chart: ChatChart? = null,
    /** Photos and files sent with a question. */
    val files: List<ChatFile> = emptyList(),
    /** Where the answer came from (backend `evidence`): conversation summaries and moments. */
    val evidence: List<ChatEvidence> = emptyList(),
    /** The structured parts of the answer (backend `content_blocks`), in the order they arrived. */
    val blocks: List<ChatBlock> = emptyList(),
    /** What the answer is: ordinary text, or the day's memories (`day_summary`). */
    val kind: Kind = Kind.Text,
) {
    enum class Sender(val rawValue: String) { User("human"), Omi("ai") }

    /** The backend's own message `type` (`Message` in `models/chat.py`). */
    enum class Kind(val rawValue: String) {
        Text("text"),
        /** "Things I learned today": the answer is a numbered recap of the day's memories. */
        DaySummary("day_summary"),
        ;

        companion object {
            /** An unknown type reads as ordinary text, as it does on iOS. */
            fun from(rawValue: String?): Kind = entries.firstOrNull { it.rawValue == rawValue } ?: Text
        }
    }

    enum class Failure(val rawValue: String) {
        /** No answer arrived (network, backend error, canned failure text). */
        CouldNotAnswer("couldNotAnswer"),
        /** The answer broke off part way. */
        Interrupted("interrupted"),
        /** The user stopped it. */
        Stopped("stopped"),
        /** The phone had no connection. */
        Offline("offline"),
        /** The backend gave up waiting for the answer. */
        Timeout("timeout"),
        /** The plan's monthly chat limit is used up. */
        QuotaExceeded("quotaExceeded"),
    }

    data class Reference(
        val conversationID: String,
        val title: String,
        val emoji: String?,
        /** When the conversation happened (its `created_at`). */
        val createdAt: Instant? = null,
    )
}

/** What a chat turn is about (backend `PageContext`). */
data class ChatContext(val kind: Kind, val id: String, val title: String) {
    enum class Kind(val rawValue: String) { Conversation("conversation"), Task("task"), Memory("memory") }
}

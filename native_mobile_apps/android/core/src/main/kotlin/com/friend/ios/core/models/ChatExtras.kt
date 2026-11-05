package com.friend.ios.core.models

/** Port of `ChatExtras.swift`: a photo or file sent with a chat message (backend `FileChat`). */
data class ChatFile(
    val id: String,
    val name: String,
    val mimeType: String,
    /** The backend's thumbnail for images. */
    val thumbnailURL: String? = null,
    /** A small JPEG kept on the phone, so a photo shows before (and without) the backend's thumbnail. */
    val localPreview: ByteArray? = null,
) {
    val isImage: Boolean get() = mimeType.startsWith("image")

    override fun equals(other: Any?): Boolean =
        other is ChatFile && other.id == id && other.name == name && other.mimeType == mimeType &&
            other.thumbnailURL == thumbnailURL && (other.localPreview contentEqualsOrNull localPreview)

    override fun hashCode(): Int = id.hashCode()

    private infix fun ByteArray?.contentEqualsOrNull(other: ByteArray?): Boolean =
        if (this == null || other == null) this == null && other == null else contentEquals(other)
}

/** A chart an answer draws (backend `ChartData`): one line or bar chart, one or more series. */
data class ChatChart(
    val kind: Kind,
    val title: String,
    val xLabel: String?,
    val yLabel: String?,
    val series: List<Series>,
) {
    enum class Kind(val rawValue: String) {
        Line("line"), Bar("bar");

        companion object {
            fun from(raw: String?): Kind? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    data class Point(val label: String, val value: Double)

    /** [color]: `#RRGGBB`, when the backend picks one. */
    data class Series(val label: String, val points: List<Point>, val color: String?)
}

/**
 * One source an answer drew on (backend `ChatEvidenceReference`). The answer text stays the
 * authority; these are chips under it. Unknown kinds and states from a newer backend decode as
 * `Unknown` and are not shown.
 */
data class ChatEvidence(
    val id: String,
    val kind: Kind,
    val state: State,
    val title: String? = null,
    val summary: String? = null,
    val conversationID: String? = null,
    val segmentID: String? = null,
    /** The moment inside the conversation (milliseconds from its start). */
    val startMs: Int? = null,
    val endMs: Int? = null,
    /** When it was captured (epoch milliseconds), for screen evidence. */
    val capturedAtMs: Long? = null,
) {
    enum class Kind(val rawValue: String) {
        ConversationSummary("conversation_summary"),
        ConversationSegment("conversation_segment"),
        Screen("screen"), Keyframe("keyframe"), Request("request"), Unknown("unknown");

        companion object {
            fun from(raw: String?): Kind = entries.firstOrNull { it.rawValue == raw?.lowercase() } ?: Unknown
        }
    }

    enum class State(val rawValue: String) {
        Available("available"), Loading("loading"), Offline("offline"), Pruned("pruned"), Failed("failed"), Unknown("unknown");

        companion object {
            fun from(raw: String?): State = entries.firstOrNull { it.rawValue == raw?.lowercase() } ?: Unknown
        }
    }

    /** A conversation the app can open (summary or moment, and still there). */
    val opensConversation: Boolean
        get() = conversationID != null && (kind == Kind.ConversationSummary || kind == Kind.ConversationSegment) &&
            state != State.Pruned && state != State.Failed
}

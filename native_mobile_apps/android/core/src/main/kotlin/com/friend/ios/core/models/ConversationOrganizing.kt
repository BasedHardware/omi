package com.friend.ios.core.models

/**
 * Port of `ConversationOrganizing.swift`. A folder conversations are sorted into (`v1/folders`).
 * System folders (Work, Personal, ...) are created by the backend and cannot be deleted.
 */
data class Folder(
    val id: String,
    val name: String,
    val icon: String,
    /** `#RRGGBB`. */
    val color: String,
    val description: String = "",
    val isSystem: Boolean,
    val order: Int,
    val conversationCount: Int,
) {
    /** What the folder editor starts from. */
    val draft: FolderDraft get() = FolderDraft(name = name, icon = icon, color = color, description = description)
}

/** Which conversations the list shows. Filtering happens on the backend (`starred=`, `folder_id=`). */
sealed interface ConversationFilter {
    data object All : ConversationFilter
    data object Starred : ConversationFilter
    data class Folder(val id: String) : ConversationFilter

    /** Whether a conversation still belongs in this filter after a local change (`ConversationsStore+Organizing.swift`). */
    fun keeps(conversation: Conversation): Boolean = when (this) {
        All -> true
        Starred -> conversation.isStarred
        is Folder -> conversation.folderID == id
    }
}

/** Where a conversation's recording can be played (`v1/sync/audio/{id}/urls`). */
sealed interface ConversationAudio {
    /** A signed URL, playable without auth headers; [duration] in seconds. */
    data class Ready(val url: String, val duration: Double?) : ConversationAudio
    /** The backend is still building the playback file; ask again after this long (seconds). */
    data class Pending(val retryAfter: Double) : ConversationAudio
    /** No single file: these cached parts, played (and shared) one after another. */
    data class Parts(val parts: List<AudioPart>) : ConversationAudio
    data object Unavailable : ConversationAudio
}

/**
 * The public page for a shared conversation, tagged like the Flutter app's `conversationShareUrl`
 * (`s` = platform, `sid` = a random per-share id, never derived from the sender).
 */
fun Conversation.Companion.shareURL(id: String, base: String = "https://h.omi.me", source: String = "android"): String {
    val random = java.security.SecureRandom()
    val sid = (0 until 16).joinToString("") { String.format(java.util.Locale.ROOT, "%02x", random.nextInt(256)) }
    return "${base.trimEnd('/')}/conversations/$id?s=$source&sid=$sid"
}

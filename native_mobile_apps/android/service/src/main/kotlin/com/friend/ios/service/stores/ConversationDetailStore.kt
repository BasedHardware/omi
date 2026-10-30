package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.AudioPart
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationAudio
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.service.AudioJoiner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Port of `ConversationDetailStore.swift`: one conversation's summary, transcript and recording.
 * Created per detail screen; changes that concern the whole conversation (star, folder, delete) go
 * through [ConversationsStore].
 */
class ConversationDetailStore(
    /** Shown immediately from the list while the detail loads. */
    val preview: Conversation,
    internal val api: APIClientProtocol,
    /** Where shared audio is written (`FileManager.default.temporaryDirectory`). */
    internal val temporaryDirectory: File = File(System.getProperty("java.io.tmpdir") ?: "."),
) {
    sealed interface Phase {
        data object Loading : Phase
        data object Loaded : Phase
        data class Failed(val message: String) : Phase
    }

    sealed interface AudioState {
        /** Not asked for yet (no recording, or the transcript tab was never opened). */
        data object Idle : AudioState
        data object Preparing : AudioState
        /** [url] is a signed URL or a local file path; [duration] in seconds. */
        data class Ready(val url: String, val duration: Double?) : AudioState
        data object Unavailable : AudioState
    }

    var phase: Phase by mutableStateOf(Phase.Loading)
        private set
    var detail: ConversationDetail? by mutableStateOf(null)
        internal set
    var isReprocessing by mutableStateOf(false)
        private set
    var audio: AudioState by mutableStateOf(AudioState.Idle)
        private set

    val conversation: Conversation get() = detail?.conversation ?: preview

    suspend fun load() {
        try {
            detail = api.conversationDetail(preview.id)
            phase = Phase.Loaded
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            phase = Phase.Failed(e.toString())
        }
    }

    /**
     * Summarizes again through the list (which shows "processing" meanwhile), with one summary
     * app when [appID] is given. Returns success.
     */
    suspend fun reprocess(list: ConversationsStore, appID: String? = null): Boolean {
        if (isReprocessing) return false
        isReprocessing = true
        try {
            val fresh = list.reprocess(conversation.id, appID) ?: return false
            detail = fresh
            return true
        } finally {
            isReprocessing = false
        }
    }

    /** Optimistic edit of one transcript line; the old words come back if the backend refuses. */
    suspend fun editLine(lineID: Int, text: String): Boolean {
        val trimmed = text.trim()
        val current = detail ?: return false
        val index = current.transcript.indexOfFirst { it.id == lineID }
        if (trimmed.isEmpty() || index < 0) return false
        val line = current.transcript[index]
        val segmentID = line.segmentID ?: return false
        if (line.text == trimmed) return false
        replaceLine(lineID) { it.copy(text = trimmed) }
        return try {
            api.editTranscriptSegment(conversation.id, segmentID, trimmed)
            true
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            replaceLine(lineID) { it.copy(text = line.text) }
            false
        }
    }

    private fun replaceLine(lineID: Int, change: (ConversationDetail.Line) -> ConversationDetail.Line) {
        val current = detail ?: return
        detail = current.copy(transcript = current.transcript.map { if (it.id == lineID) change(it) else it })
    }

    /** Finds the recording's playback file, waiting while the backend builds it ([attempts] polls). */
    suspend fun loadAudio(attempts: Int = 6) {
        if (detail?.hasAudio != true || !(audio == AudioState.Idle || audio == AudioState.Unavailable)) return
        audio = AudioState.Preparing
        // Asks the backend to build the playback files (Flutter does this when the page opens).
        try {
            api.precacheConversationAudio(conversation.id)
        } catch (e: Exception) {
            if (e is CancellationException) {
                audio = AudioState.Idle
                throw e
            }
        }
        repeat(maxOf(1, attempts)) {
            val result = try {
                api.conversationAudio(conversation.id)
            } catch (e: Exception) {
                if (e is CancellationException) {
                    audio = AudioState.Idle
                    throw e
                }
                null
            }
            when (result) {
                is ConversationAudio.Ready -> {
                    audio = AudioState.Ready(result.url, result.duration)
                    return
                }
                is ConversationAudio.Parts -> {
                    // Several parts: downloaded and joined into one file that plays and shares as one.
                    val joined = AudioJoiner.join(ordered(result.parts), audioFileName, temporaryDirectory)
                    audio = if (joined != null) AudioState.Ready(joined.path, result.parts.sumOf { it.duration }) else AudioState.Unavailable
                    return
                }
                is ConversationAudio.Pending -> try {
                    delay((result.retryAfter.coerceIn(0.0, 5.0) * 1000).toLong())
                } catch (e: CancellationException) {
                    audio = AudioState.Idle
                    throw e
                }
                ConversationAudio.Unavailable, null -> {
                    audio = AudioState.Unavailable
                    return
                }
            }
        }
        audio = AudioState.Unavailable
    }

    /** Downloads the recording to a temporary file for the share sheet (parts are joined already). */
    suspend fun exportAudio(): File? {
        val ready = audio as? AudioState.Ready ?: return null
        if (!ready.url.startsWith("http")) return File(ready.url)
        return withContext(Dispatchers.IO) {
            runCatching {
                val connection = URL(ready.url).openConnection() as HttpURLConnection
                try {
                    val type = connection.contentType
                    val bytes = connection.inputStream.use { it.readBytes() }
                    val ext = if (type == "audio/mpeg" || ready.url.substringBefore('?').endsWith(".mp3")) "mp3" else "wav"
                    val target = File(temporaryDirectory, "$audioFileName.$ext")
                    target.delete()
                    target.writeBytes(bytes)
                    target
                } finally {
                    connection.disconnect()
                }
            }.getOrNull()
        }
    }

    /** The file name shared audio gets: the title, else "Omi". */
    internal val audioFileName: String get() = (conversation.title.ifEmpty { "Omi" }).replace("/", "-")

    /** Parts by when they started (`audio_files[].started_at`), unknown starts last. */
    internal fun ordered(parts: List<AudioPart>): List<AudioPart> {
        val starts = HashMap<String, java.time.Instant?>()
        detail?.audioParts.orEmpty().forEach { if (it.id !in starts) starts[it.id] = it.startedAt }
        return parts.withIndex().sortedWith { lhs, rhs ->
            val left = starts[lhs.value.id]
            val right = starts[rhs.value.id]
            when {
                left != null && right != null && left != right -> left.compareTo(right)
                left != null && right == null -> -1
                left == null && right != null -> 1
                else -> lhs.index.compareTo(rhs.index)
            }
        }.map { it.value }
    }

    /** The summary as plain Markdown: summary, key points, other apps' results (copy and share). */
    val summaryText: String
        get() {
            val detail = detail ?: return conversation.overview
            val parts = mutableListOf(detail.summary)
            if (detail.keyPoints.isNotEmpty()) parts += detail.keyPoints.joinToString("\n") { "- $it" }
            parts += detail.otherSummaries.map { it.content }
            return parts.filter { it.isNotEmpty() }.joinToString("\n\n")
        }
}

/**
 * The detail page's store (`ConversationDetailStore(preview:api:)` in the shell): the loaded copy as
 * the preview when the list knows the conversation, else a blank one the page fills when it loads.
 */
fun ConversationsStore.makeDetailStore(id: String): ConversationDetailStore {
    val preview = known[id] ?: conversations.firstOrNull { it.id == id } ?: filtered.firstOrNull { it.id == id }
        ?: Conversation(
            id = id, title = "", overview = "", emoji = null, category = null, createdAt = java.time.Instant.now(), startedAt = null,
            finishedAt = null, status = Conversation.Status.Completed, isStarred = false, actionItemCount = 0,
        )
    return ConversationDetailStore(preview, api)
}

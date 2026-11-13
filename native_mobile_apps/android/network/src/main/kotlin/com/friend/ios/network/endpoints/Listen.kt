package com.friend.ios.network.endpoints

import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.listen.ListenSocket
import com.friend.ios.network.listen.LiveTranscriptionChannel
import kotlinx.serialization.json.JsonObject

/**
 * Port of the `APIClient` extension at the end of `ListenSocket.swift` and of
 * `APIClient+LiveSpeakers.swift` (`inProgressConversationID`): opening the capture socket and
 * finalizing what it recorded (contracts: backend `routers/transcribe.py`, `routers/conversations.py`).
 */
interface ListenAPI {
    /** Opens `/v4/listen` with the bearer header on the upgrade request. */
    suspend fun openListenSocket(uid: String, options: ListenSocket.Options): LiveTranscriptionChannel

    /** `/v2/voice-message/transcribe-stream`: words only, nothing stored. */
    suspend fun openTranscribeStream(language: String): LiveTranscriptionChannel

    /**
     * `POST v1/conversations` with `{}`: finalizes the in-progress conversation after a stop.
     * 404 means the server already finalized it (silence timeout), which is fine.
     */
    suspend fun finalizeInProgressConversation(): String?

    /** `POST v1/conversations/{id}/finalize`. */
    suspend fun finalizeConversation(id: String)

    /** `GET v1/conversations?statuses=in_progress&limit=1` (Flutter `_loadInProgressConversation`). */
    suspend fun inProgressConversationID(): String?
}

internal class ListenEndpoints(private val http: HttpCore) : ListenAPI {
    private val socketClient by lazy { ListenSocket.socketClient(http.client) }

    override suspend fun openListenSocket(uid: String, options: ListenSocket.Options): LiveTranscriptionChannel {
        val headers = buildMap { options.geolocationHeader?.let { put("X-Omi-Conversation-Geolocation", it) } }
        val request = http.request(Method.GET, "v4/listen", ListenSocket.query(uid, options), headers = headers)
        return ListenSocket(request, socketClient).also { it.open() }
    }

    override suspend fun openTranscribeStream(language: String): LiveTranscriptionChannel {
        val query = listOf("language" to language, "sample_rate" to "16000", "codec" to "linear16")
        val request = http.request(Method.GET, "v2/voice-message/transcribe-stream", query)
        return ListenSocket(request, socketClient, ListenSocket.Kind.TranscribeOnly).also { it.open() }
    }

    override suspend fun finalizeInProgressConversation(): String? = try {
        val text = http.data(Method.POST, "v1/conversations", body = Body.Json("{}"))
        JsonAccess.obj(text).obj("conversation")?.string("id")
    } catch (error: APIError.Http) {
        if (error.status == 404) null else throw error
    }

    override suspend fun finalizeConversation(id: String) {
        http.data(Method.POST, "v1/conversations/$id/finalize", body = Body.Json("{}"))
    }

    override suspend fun inProgressConversationID(): String? {
        val text = http.data(Method.GET, "v1/conversations", query = listOf("statuses" to "in_progress", "limit" to "1"))
        return (JsonAccess.array(text).firstOrNull() as? JsonObject)?.string("id")
    }
}

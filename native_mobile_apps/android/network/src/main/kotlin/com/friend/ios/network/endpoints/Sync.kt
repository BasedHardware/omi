package com.friend.ios.network.endpoints

import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method

/** The server's answer to an offline-recording upload (`POST v2/sync-local-files`). */
data class SyncUpload(
    /** Null when the server finished synchronously (HTTP 200) or knew the audio already. */
    val jobID: String?,
    /** `queued`, `processing`, `completed`, `failed`, `partial_failure`. */
    val status: String,
)

/** `GET v2/sync-local-files/{job_id}`. */
data class SyncJob(val status: String, val reasonCode: String? = null) {
    val isFinished: Boolean get() = status in setOf("completed", "failed", "partial_failure")

    /**
     * The audio itself was refused; sending the same bytes again cannot help
     * (Flutter `_kPermanentInputFailureReasonCodes`).
     */
    val isPermanentFailure: Boolean get() = status == "failed" && (reasonCode ?: "") in setOf("sync_invalid_audio", "stt_invalid_input")
}

/** Port of `APIClient+Sync.swift`. */
interface SyncAPI {
    /**
     * `POST v2/sync-local-files`, one multipart `files` part. The filename carries codec, sample
     * rate, frame size and start time (`audio_<device>_<codec>_<rate>_<channels>_fs<frame>_<epoch>.bin`);
     * the body is `[u32 LE length][frame]...`, as the Flutter app writes it.
     */
    suspend fun uploadOfflineRecording(filename: String, data: ByteArray): SyncUpload

    /**
     * Null once the server no longer knows the job (404/403): the caller uploads again; the
     * backend recognises audio it already has.
     */
    suspend fun syncJob(id: String): SyncJob?
}

internal class SyncEndpoints(private val http: HttpCore) : SyncAPI {
    override suspend fun uploadOfflineRecording(filename: String, data: ByteArray): SyncUpload {
        val text = http.data(Method.POST, "v2/sync-local-files", body = Body.File("files", filename, "application/octet-stream", data))
        val obj = JsonAccess.obj(text)
        // A 200 carries the finished result instead of a job.
        return SyncUpload(jobID = obj.string("job_id"), status = obj.string("status") ?: "completed")
    }

    override suspend fun syncJob(id: String): SyncJob? {
        val text = try {
            http.data(Method.GET, "v2/sync-local-files/$id")
        } catch (e: APIError.Http) {
            if (e.status == 404 || e.status == 403) return null
            throw e
        }
        val obj = JsonAccess.obj(text)
        return SyncJob(status = obj.string("status") ?: "queued", reasonCode = obj.string("reason_code"))
    }
}

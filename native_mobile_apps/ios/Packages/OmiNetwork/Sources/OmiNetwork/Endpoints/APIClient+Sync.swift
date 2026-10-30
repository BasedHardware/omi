import Foundation

/// The server's answer to an offline-recording upload (`POST v2/sync-local-files`).
public struct SyncUpload: Equatable, Sendable {
    /// Nil when the server finished synchronously (HTTP 200) or knew the audio already.
    public var jobID: String?
    /// `queued`, `processing`, `completed`, `failed`, `partial_failure`.
    public var status: String

    public init(jobID: String?, status: String) {
        self.jobID = jobID
        self.status = status
    }
}

/// `GET v2/sync-local-files/{job_id}`.
public struct SyncJob: Equatable, Sendable {
    public var status: String
    public var reasonCode: String?

    public init(status: String, reasonCode: String? = nil) {
        self.status = status
        self.reasonCode = reasonCode
    }

    public var isFinished: Bool {
        ["completed", "failed", "partial_failure"].contains(status)
    }

    /// The audio itself was refused; sending the same bytes again cannot help
    /// (Flutter `_kPermanentInputFailureReasonCodes`).
    public var isPermanentFailure: Bool {
        status == "failed" && ["sync_invalid_audio", "stt_invalid_input"].contains(reasonCode ?? "")
    }
}

public extension APIClient {
    /// `POST v2/sync-local-files`, one multipart `files` part. The filename carries codec, sample rate,
    /// frame size and start time (`audio_<device>_<codec>_<rate>_<channels>_fs<frame>_<epoch>.bin`);
    /// the body is `[u32 LE length][frame]…`, as the Flutter app writes it.
    func uploadOfflineRecording(filename: String, data body: Data) async throws -> SyncUpload {
        let file = Body.file(field: "files", filename: filename, mimeType: "application/octet-stream", data: body)
        let data = try await data(.post, "v2/sync-local-files", body: file)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        // A 200 carries the finished result instead of a job.
        return SyncUpload(jobID: object?["job_id"] as? String, status: object?["status"] as? String ?? "completed")
    }

    /// Nil once the server no longer knows the job (404/403): the caller uploads again; the
    /// backend recognises audio it already has.
    func syncJob(id: String) async throws -> SyncJob? {
        do {
            let data = try await data(.get, "v2/sync-local-files/\(id)")
            let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return SyncJob(status: object?["status"] as? String ?? "queued", reasonCode: object?["reason_code"] as? String)
        } catch let APIError.http(status, _) where status == 404 || status == 403 {
            return nil
        }
    }
}

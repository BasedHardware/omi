import Foundation
import OmiNetwork

/// What the fake backend received for offline sync, and how it answers.
public final class FakeSyncBackend: @unchecked Sendable {
    let lock = NSLock()
    private var _uploads: [(filename: String, data: Data)] = []
    private var _failures: [APIError] = []
    private var _jobs: [String: SyncJob] = [:]
    private var _jobPolls: [String] = []
    /// Status of jobs created by uploads (`queued` keeps them pending until `finish`).
    public nonisolated(unsafe) var newJobStatus = "queued"
    /// Set to park an upload inside the request, so a test can watch what the app does while a
    /// transfer is in flight.
    public nonisolated(unsafe) var uploadGate: (() async -> Void)?

    public init() {}

    public var uploads: [(filename: String, data: Data)] {
        lock.withLock { _uploads }
    }

    public var jobPolls: [String] {
        lock.withLock { _jobPolls }
    }

    /// The next uploads fail with these errors, in order.
    public func failUploads(_ errors: [APIError]) {
        lock.withLock { _failures = errors }
    }

    public func setJob(_ id: String, _ job: SyncJob?) {
        lock.withLock { _jobs[id] = job }
    }

    func upload(filename: String, data: Data) throws -> SyncUpload {
        try lock.withLock {
            if !_failures.isEmpty { throw _failures.removeFirst() }
            _uploads.append((filename, data))
            let id = "job-\(_uploads.count)"
            _jobs[id] = SyncJob(status: newJobStatus)
            return SyncUpload(jobID: id, status: newJobStatus)
        }
    }

    func job(_ id: String) -> SyncJob? {
        lock.withLock {
            _jobPolls.append(id)
            return _jobs[id]
        }
    }
}

public extension FakeAPIClient {
    func uploadOfflineRecording(filename: String, data: Data) async throws -> SyncUpload {
        if let gate = syncBackend.uploadGate { await gate() }
        return try syncBackend.upload(filename: filename, data: data)
    }

    func syncJob(id: String) async throws -> SyncJob? {
        syncBackend.job(id)
    }
}

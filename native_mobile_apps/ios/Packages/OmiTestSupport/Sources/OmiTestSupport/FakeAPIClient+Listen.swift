import Foundation
import OmiCore
import OmiNetwork

/// Backend state for the listen socket and finalizing conversations.
public final class FakeListenBackend: @unchecked Sendable {
    /// Every `POST v1/conversations/{id}/finalize`, in order.
    public internal(set) var finalizedIDs: [String] = []
    /// Answers `finalize` with this (e.g. 503: no durable finalization worker).
    public var finalizeError: APIError?
    /// Every call in order: `listen`, `finalize:<id>`, `finalizeInProgress`.
    public internal(set) var calls: [String] = []
    /// Opening the socket takes this long (audio arriving meanwhile).
    public var openDelay: Duration?

    public init() {}
}

// MARK: Listen

public extension FakeAPIClient {
    func openListenSocket(uid _: String, options: ListenSocket.Options) async throws -> any LiveTranscriptionChannel {
        if let delay = lock.withLock({ listenBackend.openDelay }) { try? await Task.sleep(for: delay) }
        if let failure = lock.withLock({ _error }) { throw failure }
        lock.withLock {
            listenOptions.append(options)
            listenBackend.calls.append("listen")
        }
        return liveChannel
    }

    func finalizeInProgressConversation() async throws -> String? {
        lock.withLock {
            finalizeCalls += 1
            listenBackend.calls.append("finalizeInProgress")
        }
        return "c-new"
    }

    func finalizeConversation(id: String) async throws {
        try lock.withLock {
            listenBackend.calls.append("finalize:\(id)")
            if let failure = listenBackend.finalizeError { throw failure }
            listenBackend.finalizedIDs.append(id)
        }
    }
}

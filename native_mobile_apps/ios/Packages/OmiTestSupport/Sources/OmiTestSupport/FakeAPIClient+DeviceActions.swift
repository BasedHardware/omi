import Foundation
import OmiCore
import OmiNetwork

/// What the fake backend received from the Omi's button, and how it answers a spoken question.
public final class FakeDeviceActions: @unchecked Sendable {
    let lock = NSLock()
    private var _starred: [(id: String, starred: Bool)] = []
    private var _voiceUploads: [(filename: String, audio: Data)] = []
    private var _voiceReply: [VoiceMessageEvent] = []

    public init() {}

    public var starred: [(id: String, starred: Bool)] {
        lock.withLock { _starred }
    }

    public var voiceUploads: [(filename: String, audio: Data)] {
        lock.withLock { _voiceUploads }
    }

    /// The frames every voice question streams back.
    public func replyToVoice(_ events: [VoiceMessageEvent]) {
        lock.withLock { _voiceReply = events }
    }

    func star(_ id: String, _ starred: Bool) {
        lock.withLock { _starred.append((id, starred)) }
    }

    func voice(_ filename: String, _ audio: Data) -> [VoiceMessageEvent] {
        lock.withLock {
            _voiceUploads.append((filename, audio))
            return _voiceReply
        }
    }
}

public extension FakeAPIClient {
    func starConversation(id: String, starred: Bool) async throws {
        if let failure = lock.withLock({ _error }) { throw failure }
        deviceActions.star(id, starred)
    }

    func sendVoiceMessage(filename: String, audio: Data) -> AsyncThrowingStream<VoiceMessageEvent, any Error> {
        let events = deviceActions.voice(filename, audio)
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }
}

/// Diagnostics bundles sent to support, and the ticket the fake hands back.
public final class FakeDiagnosticsUploads: @unchecked Sendable {
    let lock = NSLock()
    private var _bundles: [Data] = []
    private var _ticket = "A1B2C3D4E5F6"

    public init() {}

    public var bundles: [Data] {
        lock.withLock { _bundles }
    }

    var ticket: String {
        lock.withLock { _ticket }
    }

    func record(_ bundle: Data) {
        lock.withLock { _bundles.append(bundle) }
    }
}

public extension FakeAPIClient {
    func uploadDeviceDiagnostics(_ bundle: Data) async throws -> String {
        if let failure = lock.withLock({ _error }) { throw failure }
        diagnosticsUploads.record(bundle)
        return diagnosticsUploads.ticket
    }
}

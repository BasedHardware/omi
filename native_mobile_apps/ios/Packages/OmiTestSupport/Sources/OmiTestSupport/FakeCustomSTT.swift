import Foundation
import OmiNetwork
import OmiPersistence

/// Records the provider requests custom STT makes and answers them from `responses` (in order;
/// the last one repeats). Tests push Deepgram messages through `socket.emit`.
public final class FakeCustomSTTTransport: CustomSTTTransport, @unchecked Sendable {
    private let lock = NSLock()
    private var _requests: [URLRequest] = []
    private var _responses: [(Data, Int)]
    public let socket = FakeCustomSTTSocket()
    public private(set) var openedSockets: [URLRequest] = []

    public init(responses: [(Data, Int)] = [(Data(#"{"text":""}"#.utf8), 200)]) {
        _responses = responses
    }

    public var requests: [URLRequest] {
        lock.withLock { _requests }
    }

    public func send(_ request: URLRequest) async throws -> (Data, Int) {
        lock.withLock {
            _requests.append(request)
            return _responses.count > 1 ? _responses.removeFirst() : _responses[0]
        }
    }

    public func openSocket(_ request: URLRequest) -> any CustomSTTSocket {
        lock.withLock { openedSockets.append(request) }
        return socket
    }
}

public final class FakeCustomSTTSocket: CustomSTTSocket, @unchecked Sendable {
    public let messages: AsyncStream<String>
    private let continuation: AsyncStream<String>.Continuation
    private let lock = NSLock()
    public private(set) var audioBytes = 0
    public private(set) var texts: [String] = []
    public private(set) var closed = false

    public init() {
        (messages, continuation) = AsyncStream.makeStream(of: String.self)
    }

    public func emit(_ message: String) {
        continuation.yield(message)
    }

    public func send(audio: Data) {
        lock.withLock { audioBytes += audio.count }
    }

    public func send(text: String) {
        lock.withLock { texts.append(text) }
    }

    public func close() {
        lock.withLock { closed = true }
        continuation.finish()
    }
}

/// Secrets in memory (the app: the Keychain).
public final class InMemorySecretStore: SecretStore, @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: String] = [:]

    public init() {}

    public func secret(_ name: String) -> String? {
        lock.withLock { values[name] }
    }

    public func setSecret(_ value: String?, for name: String) {
        lock.withLock { values[name] = value.flatMap { $0.isEmpty ? nil : $0 } }
    }
}

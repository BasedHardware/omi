import Foundation

/// A live connection to a streaming provider (Deepgram): binary audio in, text messages out.
public protocol CustomSTTSocket: AnyObject, Sendable {
    /// Every text message; finishes when the connection closes or fails.
    var messages: AsyncStream<String> { get }
    func send(audio: Data)
    func send(text: String)
    func close()
}

/// How custom STT reaches its provider (real: `URLSession`; tests: `FakeCustomSTTTransport`).
/// Requests carry the user's key in a header: nothing here logs them.
public protocol CustomSTTTransport: Sendable {
    /// The body and HTTP status.
    func send(_ request: URLRequest) async throws -> (Data, Int)
    func openSocket(_ request: URLRequest) -> any CustomSTTSocket
}

public struct URLSessionCustomSTTTransport: CustomSTTTransport {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func send(_ request: URLRequest) async throws -> (Data, Int) {
        let (data, response) = try await session.data(for: request)
        return (data, (response as? HTTPURLResponse)?.statusCode ?? 0)
    }

    public func openSocket(_ request: URLRequest) -> any CustomSTTSocket {
        let socket = WebSocketSTTSocket(task: session.webSocketTask(with: request))
        socket.open()
        return socket
    }
}

/// `URLSessionWebSocketTask` as a `CustomSTTSocket`.
final class WebSocketSTTSocket: CustomSTTSocket, @unchecked Sendable {
    let messages: AsyncStream<String>
    private let continuation: AsyncStream<String>.Continuation
    private let task: URLSessionWebSocketTask

    init(task: URLSessionWebSocketTask) {
        (messages, continuation) = AsyncStream.makeStream(of: String.self, bufferingPolicy: .bufferingNewest(256))
        self.task = task
    }

    func open() {
        task.resume()
        receiveNext()
    }

    func send(audio: Data) {
        task.send(.data(audio)) { _ in }
    }

    func send(text: String) {
        task.send(.string(text)) { _ in }
    }

    func close() {
        task.cancel(with: .normalClosure, reason: nil)
        continuation.finish()
    }

    private func receiveNext() {
        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case let .success(.string(text)):
                continuation.yield(text)
                receiveNext()
            case let .success(.data(data)):
                if let text = String(data: data, encoding: .utf8) { continuation.yield(text) }
                receiveNext()
            case .success:
                receiveNext()
            case .failure:
                continuation.finish()
            }
        }
    }
}

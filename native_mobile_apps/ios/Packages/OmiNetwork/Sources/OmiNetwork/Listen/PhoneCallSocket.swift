import Foundation

/// Server → client on a phone call's transcription socket.
public enum PhoneCallSocketEvent: Sendable, Equatable {
    /// Segments, re-sent with the same id when refined (upsert by id).
    case segments([LiveSegment])
    /// `translating`: segment id → its translated texts (live interpreter on calls).
    case translations([String: [String]])
    /// Any other server message (`service_status`, the session, `ping`): the socket is accepted.
    case status(String)
    /// The socket closed (server, network); the store reconnects while the call lasts.
    case closed(String?)

    /// Parses one text frame (Flutter `PhoneCallProvider._handleTranscriptionMessage`); `ping` is nil.
    public static func parse(_ text: String) -> PhoneCallSocketEvent? {
        guard text != "ping", let data = text.data(using: .utf8) else { return nil }
        if text.first == "[" {
            return (try? JSONDecoder().decode([LiveSegment].self, from: data)).map { .segments($0) }
        }
        guard let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return nil }
        guard let type = object["type"] as? String, type == "translating" else {
            return .status(object["status"] as? String ?? object["type"] as? String ?? "message")
        }
        var translated: [String: [String]] = [:]
        for segment in object["segments"] as? [[String: Any]] ?? [] {
            guard let id = segment["id"] as? String else { continue }
            let texts = (segment["translations"] as? [[String: Any]] ?? []).compactMap { $0["text"] as? String }
            if !texts.isEmpty { translated[id] = texts }
        }
        return .translations(translated)
    }
}

/// One phone call's transcription stream as the phone-call store sees it (real socket or test fake).
public protocol PhoneCallTranscriptChannel: AnyObject, Sendable {
    /// Every message the server sent; finishes after `.closed`.
    var events: AsyncStream<PhoneCallSocketEvent> { get }
    /// One binary frame: a channel byte (`0x01` you, `0x02` the other side) then PCM16 at 48 kHz.
    func send(frame: Data)
    func close()
}

/// `/v4/listen` for a call: `source=phone_call`, `channels=2`, the call id the Twilio leg carries.
/// Contract: backend `routers/listen` (`build_channel_config('phone_call')`) and Flutter
/// `buildPhoneCallWebSocketUrl` (`app/lib/backend/http/api/phone_calls.dart`).
public final class PhoneCallSocket: PhoneCallTranscriptChannel, @unchecked Sendable {
    public static let sampleRate = 48000

    public let events: AsyncStream<PhoneCallSocketEvent>
    private let continuation: AsyncStream<PhoneCallSocketEvent>.Continuation
    private let task: URLSessionWebSocketTask
    private let lock = NSLock()
    private var closed = false
    private var pinger: Task<Void, Never>?

    init(request: URLRequest, session: URLSession) {
        (events, continuation) = AsyncStream.makeStream(of: PhoneCallSocketEvent.self, bufferingPolicy: .bufferingNewest(256))
        task = session.webSocketTask(with: request)
    }

    static func url(base: URL, uid: String, callID: String, language: String) -> URL {
        var components = URLComponents(url: base.appending(path: "v4/listen"), resolvingAgainstBaseURL: false)!
        components.scheme = base.scheme == "https" ? "wss" : "ws"
        components.queryItems = [
            URLQueryItem(name: "source", value: "phone_call"),
            URLQueryItem(name: "call_id", value: callID),
            URLQueryItem(name: "uid", value: uid),
            URLQueryItem(name: "sample_rate", value: String(sampleRate)),
            URLQueryItem(name: "codec", value: "pcm"),
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "channels", value: "2"),
        ]
        return components.url!
    }

    func open() {
        task.resume()
        receiveNext()
        // Flutter's IOWebSocketChannel pings every 20 s; idle calls (hold music) must not drop.
        pinger = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                guard let self, !isClosed else { return }
                task.sendPing { _ in }
            }
        }
    }

    public func send(frame: Data) {
        guard frame.count > 1, !isClosed else { return }
        task.send(.data(frame)) { _ in }
    }

    public func close() {
        lock.withLock { closed = true }
        pinger?.cancel()
        task.cancel(with: .normalClosure, reason: nil)
        continuation.finish()
    }

    private var isClosed: Bool {
        lock.withLock { closed }
    }

    private func receiveNext() {
        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case let .success(.string(text)):
                // Flutter counts every message, `ping` included, as the server having accepted the socket.
                continuation.yield(PhoneCallSocketEvent.parse(text) ?? .status(text == "ping" ? "ping" : "message"))
                receiveNext()
            case .success:
                receiveNext()
            case let .failure(error):
                guard !isClosed else { return }
                lock.withLock { closed = true }
                pinger?.cancel()
                continuation.yield(.closed(error.localizedDescription))
                continuation.finish()
            }
        }
    }
}

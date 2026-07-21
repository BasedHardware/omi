import Foundation

/// Hosted Parakeet `/v3/stream` client (http(s) base → ws(s) + /v3/stream).
public final class OmiParakeetTranscriber: NSObject, OmiStreamingTranscriber, URLSessionWebSocketDelegate {
    private let sampleRate: Int
    private let onTranscript: OmiTranscriptHandler
    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private let queue = DispatchQueue(label: "omi.stt.parakeet")
    private var ready = false

    public init(apiURL: URL, sampleRate: Int = 16000, onTranscript: @escaping OmiTranscriptHandler) {
        self.sampleRate = sampleRate
        self.onTranscript = onTranscript
        super.init()
        connect(apiURL: apiURL)
    }

    public convenience init(apiURLString: String, sampleRate: Int = 16000, onTranscript: @escaping OmiTranscriptHandler) {
        var s = apiURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        while s.hasSuffix("/") { s.removeLast() }
        s = s.replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        let url = URL(string: "\(s)/v3/stream?sample_rate=\(sampleRate)")!
        self.init(apiURL: url, sampleRate: sampleRate, onTranscript: onTranscript)
    }

    private func connect(apiURL: URL) {
        let session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
        self.session = session
        let task = session.webSocketTask(with: apiURL)
        self.task = task
        task.resume()
        receiveLoop()
    }

    public func appendPcm(_ data: Data) {
        queue.async { [weak self] in
            guard let self, self.ready else { return }
            self.task?.send(.data(data)) { _ in }
        }
    }

    public func stop() {
        queue.async { [weak self] in
            self?.task?.send(.string("finalize")) { _ in }
            self?.task?.cancel(with: .goingAway, reason: nil)
            self?.session?.invalidateAndCancel()
            self?.task = nil
            self?.session = nil
        }
    }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .failure:
                return
            case .success(let message):
                if case .string(let text) = message,
                   let data = text.data(using: .utf8),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if json["type"] as? String == "ready" {
                        self.ready = true
                    } else if let t = Self.extractText(json), !t.isEmpty {
                        self.onTranscript(t)
                    }
                }
                self.receiveLoop()
            }
        }
    }

    private static func extractText(_ json: [String: Any]) -> String? {
        if let t = json["text"] as? String, !t.isEmpty { return t }
        if let t = json["transcript"] as? String, !t.isEmpty { return t }
        if let segs = json["segments"] as? [[String: Any]] {
            let parts = segs.compactMap { $0["text"] as? String ?? $0["transcript"] as? String }.filter { !$0.isEmpty }
            if !parts.isEmpty { return parts.joined(separator: " ") }
        }
        return nil
    }
}

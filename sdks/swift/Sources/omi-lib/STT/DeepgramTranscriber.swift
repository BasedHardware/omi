import Foundation

/// Deepgram live transcription over WebSocket.
public final class OmiDeepgramTranscriber: NSObject, OmiStreamingTranscriber, URLSessionWebSocketDelegate {
    private let apiKey: String
    private let sampleRate: Int
    private let onTranscript: OmiTranscriptHandler
    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private let queue = DispatchQueue(label: "omi.stt.deepgram")

    public init(apiKey: String, sampleRate: Int = 16000, onTranscript: @escaping OmiTranscriptHandler) {
        self.apiKey = apiKey
        self.sampleRate = sampleRate
        self.onTranscript = onTranscript
        super.init()
        connect()
    }

    private func connect() {
        var components = URLComponents(string: "wss://api.deepgram.com/v1/listen")!
        components.queryItems = [
            URLQueryItem(name: "punctuate", value: "true"),
            URLQueryItem(name: "model", value: "nova"),
            URLQueryItem(name: "language", value: "en-US"),
            URLQueryItem(name: "encoding", value: "linear16"),
            URLQueryItem(name: "sample_rate", value: String(sampleRate)),
            URLQueryItem(name: "channels", value: "1"),
        ]
        var request = URLRequest(url: components.url!)
        request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")
        let session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
        self.session = session
        let task = session.webSocketTask(with: request)
        self.task = task
        task.resume()
        receiveLoop()
    }

    public func appendPcm(_ data: Data) {
        queue.async { [weak self] in
            self?.task?.send(.data(data)) { _ in }
        }
    }

    public func stop() {
        queue.async { [weak self] in
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
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let channel = json["channel"] as? [String: Any],
                   let alts = channel["alternatives"] as? [[String: Any]],
                   let transcript = alts.first?["transcript"] as? String,
                   !transcript.isEmpty {
                    self.onTranscript(transcript)
                }
                self.receiveLoop()
            }
        }
    }
}

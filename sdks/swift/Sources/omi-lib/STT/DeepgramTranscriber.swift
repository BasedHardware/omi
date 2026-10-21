import Foundation

/// Deepgram live transcription over WebSocket.
public final class OmiDeepgramTranscriber: NSObject, OmiStreamingTranscriber, URLSessionWebSocketDelegate {
  private let apiKey: String
  public let sampleRate: Int
  public let model: String
  public let language: String
  private let onTranscript: OmiTranscriptHandler
  private var task: URLSessionWebSocketTask?
  private var session: URLSession?
  private let queue = DispatchQueue(label: "omi.stt.deepgram")

  public convenience init(
    apiKey: String,
    sampleRate: Int = 16000,
    model: String = "nova",
    language: String = "en-US",
    onTranscript: @escaping OmiTranscriptHandler
  ) {
    self.init(
      apiKey: apiKey,
      sampleRate: sampleRate,
      model: model,
      language: language,
      autoConnect: true,
      onTranscript: onTranscript
    )
  }

  init(
    apiKey: String,
    sampleRate: Int = 16000,
    model: String = "nova",
    language: String = "en-US",
    autoConnect: Bool,
    onTranscript: @escaping OmiTranscriptHandler
  ) {
    self.apiKey = apiKey
    self.sampleRate = sampleRate
    self.model = model
    self.language = language
    self.onTranscript = onTranscript
    super.init()
    if autoConnect {
      connect()
    }
  }

  public convenience init(
    apiKey: String,
    sampleRate: Int = 16000,
    onTranscript: @escaping OmiTranscriptHandler
  ) {
    self.init(
      apiKey: apiKey,
      sampleRate: sampleRate,
      model: "nova",
      language: "en-US",
      autoConnect: true,
      onTranscript: onTranscript
    )
  }

  public static func buildRequest(
    apiKey: String,
    sampleRate: Int = 16000,
    model: String = "nova",
    language: String = "en-US"
  ) -> URLRequest {
    var components = URLComponents(string: "wss://api.deepgram.com/v1/listen")!
    components.queryItems = [
      URLQueryItem(name: "punctuate", value: "true"),
      URLQueryItem(name: "model", value: model),
      URLQueryItem(name: "language", value: language),
      URLQueryItem(name: "encoding", value: "linear16"),
      URLQueryItem(name: "sample_rate", value: String(sampleRate)),
      URLQueryItem(name: "channels", value: "1"),
    ]
    var request = URLRequest(url: components.url!)
    request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")
    return request
  }

  private func connect() {
    let request = Self.buildRequest(
      apiKey: apiKey,
      sampleRate: sampleRate,
      model: model,
      language: language
    )
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
          !transcript.isEmpty
        {
          self.onTranscript(transcript)
        }
        self.receiveLoop()
      }
    }
  }
}

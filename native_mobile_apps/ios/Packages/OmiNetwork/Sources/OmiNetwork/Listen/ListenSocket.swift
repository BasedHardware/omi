import Foundation
import OmiCore

/// A live transcription session as the capture layer sees it (real socket or test fake).
public protocol LiveTranscriptionChannel: AnyObject, Sendable {
    var events: AsyncStream<ListenEvent> { get }
    func send(audio: Data)
    func sendSuggestedTranscript(_ segments: [LiveSegment], provider: String)
    func close(reason: String)
    /// A voice was named during capture (after the REST assignment): the session picks it up.
    func sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: [String])
}

public extension LiveTranscriptionChannel {
    func sendSpeakerAssigned(speakerID _: Int?, personID _: String, personName _: String, segmentIDs _: [String]) {}
}

/// The capture stream to `/v4/listen`. One instance per recording session.
/// Contract: backend `routers/transcribe.py` + Flutter `transcription_service.dart`.
public final class ListenSocket: LiveTranscriptionChannel, @unchecked Sendable {
    public struct Options: Sendable {
        public enum Codec: String, Sendable { case pcm16, opusFS320 = "opus_fs320", opus, pcm8 }
        /// Backend `ConversationSource` values (`models/conversation_enums.py`).
        public enum Source: String, Sendable { case phone, omi, appleWatch = "apple_watch" }

        public var codec: Codec
        public var sampleRate: Int
        public var source: Source
        public var language: String
        public var conversationTimeout: Int
        /// The client supplies transcripts itself (`suggested_transcript`), e.g. on-device STT.
        public var clientTranscription: Bool
        /// The server's speech model (`stt_service`, e.g. `parakeet`); nil lets the backend choose.
        public var sttService: String?
        /// `vad_gate=enabled`: the backend only transcribes speech (developer setting).
        public var vadGate = false
        /// Where the recording starts (`X-Omi-Conversation-Geolocation`); `nil` without location access.
        public var geolocation: GeolocationSnapshot?
        /// The recording's id (`client_conversation_id`). A socket reopened with the same id resumes
        /// the recording's conversation instead of starting a new one.
        public var clientConversationID = UUID().uuidString.lowercased()

        public init(
            codec: Codec,
            sampleRate: Int = 16000,
            source: Source,
            language: String = "en",
            conversationTimeout: Int = 120,
            clientTranscription: Bool = false
        ) {
            self.codec = codec
            self.sampleRate = sampleRate
            self.source = source
            self.language = language
            self.conversationTimeout = conversationTimeout
            self.clientTranscription = clientTranscription
        }
    }

    /// `/v4/listen` captures conversations; `/v2/voice-message/transcribe-stream` only transcribes.
    enum Kind { case listen, transcribeOnly }

    public let events: AsyncStream<ListenEvent>
    private let continuation: AsyncStream<ListenEvent>.Continuation
    private let task: URLSessionWebSocketTask
    private let kind: Kind
    private let lock = NSLock()
    private var closed = false

    init(request: URLRequest, session: URLSession, kind: Kind = .listen) {
        (events, continuation) = AsyncStream.makeStream(of: ListenEvent.self, bufferingPolicy: .bufferingNewest(256))
        task = session.webSocketTask(with: request)
        self.kind = kind
    }

    static func transcribeURL(base: URL, language: String) -> URL {
        var components = URLComponents(url: base.appending(path: "v2/voice-message/transcribe-stream"), resolvingAgainstBaseURL: false)!
        components.scheme = base.scheme == "https" ? "wss" : "ws"
        components.queryItems = [
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "sample_rate", value: "16000"),
            URLQueryItem(name: "codec", value: "linear16"),
        ]
        return components.url!
    }

    static func url(base: URL, uid: String, options: Options) -> URL {
        var components = URLComponents(url: base.appending(path: "v4/listen"), resolvingAgainstBaseURL: false)!
        components.scheme = base.scheme == "https" ? "wss" : "ws"
        var items = [
            URLQueryItem(name: "language", value: options.language),
            URLQueryItem(name: "sample_rate", value: String(options.sampleRate)),
            URLQueryItem(name: "codec", value: options.codec.rawValue),
            URLQueryItem(name: "uid", value: uid),
            URLQueryItem(name: "include_speech_profile", value: "true"),
            URLQueryItem(name: "conversation_timeout", value: String(options.conversationTimeout)),
            URLQueryItem(name: "source", value: options.source.rawValue),
            URLQueryItem(name: "client_conversation_id", value: options.clientConversationID),
            URLQueryItem(name: "speaker_auto_assign", value: "enabled"),
            URLQueryItem(name: "create_speakers", value: "true"),
        ]
        if options.clientTranscription { items.append(URLQueryItem(name: "custom_stt", value: "enabled")) }
        if let service = options.sttService, !service.isEmpty { items.append(URLQueryItem(name: "stt_service", value: service)) }
        if options.vadGate { items.append(URLQueryItem(name: "vad_gate", value: "enabled")) }
        components.queryItems = items
        return components.url!
    }

    func open() {
        task.resume()
        if kind == .listen { send(text: #"{"type":"client_state","foreground":true,"transcript_visible":true}"#) }
        receiveNext()
    }

    /// One binary message per audio chunk (PCM16 chunk or one opus packet).
    public func send(audio: Data) {
        guard audio.count > 2, !isClosed else { return }
        task.send(.data(audio)) { _ in }
    }

    /// Client-side transcript (custom STT mode). Shape from backend `fakes/stt.py`.
    public func sendSuggestedTranscript(_ segments: [LiveSegment], provider: String) {
        let payload: [String: Any] = [
            "type": "suggested_transcript",
            "stt_provider": provider,
            "segments": segments.map {
                ["id": $0.id, "text": $0.text, "speaker": $0.speaker ?? "SPEAKER_00", "speaker_id": $0.speakerID ?? 0,
                 "is_user": $0.isUser, "start": $0.start, "end": $0.end]
            },
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let text = String(data: data, encoding: .utf8) else { return }
        send(text: text)
    }

    /// Flutter `assignSpeakerToConversation`; backend `receiver.py` `_handle_speaker_assigned`.
    public func sendSpeakerAssigned(speakerID: Int?, personID: String, personName: String, segmentIDs: [String]) {
        var payload: [String: Any] = [
            "type": "speaker_assigned", "person_id": personID, "person_name": personName, "segment_ids": segmentIDs,
        ]
        if let speakerID { payload["speaker_id"] = speakerID }
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let text = String(bytes: data, encoding: .utf8) else { return }
        send(text: text)
    }

    public func close(reason: String = "user_stop") {
        send(text: kind == .listen ? #"{"type":"finalization_reason","reason":"\#(reason)"}"# : "finalize")
        lock.withLock { closed = true }
        task.cancel(with: .normalClosure, reason: nil)
        continuation.finish()
    }

    private var isClosed: Bool {
        lock.withLock { closed }
    }

    private func send(text: String) {
        task.send(.string(text)) { _ in }
    }

    private func receiveNext() {
        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case let .success(.string(text)):
                if text == "ping" {
                    send(text: "pong")
                } else if let event = ListenEvent.parse(text) {
                    continuation.yield(event)
                }
                receiveNext()
            case .success:
                receiveNext()
            case let .failure(error):
                if !isClosed {
                    continuation.yield(.status("disconnected: \(error.localizedDescription)"))
                    continuation.finish()
                }
            }
        }
    }
}

public extension APIClient {
    /// Opens `/v4/listen` with the bearer header on the upgrade request.
    func openListenSocket(uid: String, options: ListenSocket.Options) async throws -> any LiveTranscriptionChannel {
        var request = URLRequest(url: ListenSocket.url(base: configuration.apiBaseURL, uid: uid, options: options))
        let token = try await tokens.idToken(forceRefresh: false)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("ios", forHTTPHeaderField: "X-App-Platform")
        request.setValue(configuration.appVersion, forHTTPHeaderField: "X-App-Version")
        if let header = options.geolocation?.headerValue { request.setValue(header, forHTTPHeaderField: "X-Omi-Conversation-Geolocation") }
        let socket = ListenSocket(request: request, session: session)
        socket.open()
        return socket
    }

    func openTranscribeStream(language: String) async throws -> any LiveTranscriptionChannel {
        var request = URLRequest(url: ListenSocket.transcribeURL(base: configuration.apiBaseURL, language: language))
        let token = try await tokens.idToken(forceRefresh: false)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("ios", forHTTPHeaderField: "X-App-Platform")
        request.setValue(configuration.appVersion, forHTTPHeaderField: "X-App-Version")
        let socket = ListenSocket(request: request, session: session, kind: .transcribeOnly)
        socket.open()
        return socket
    }

    /// `POST v1/conversations` with `{}`: finalizes the in-progress conversation after a stop.
    /// 404 means the server already finalized it (silence timeout), which is fine.
    func finalizeInProgressConversation() async throws -> String? {
        do {
            let data = try await data(.post, "v1/conversations", body: .json(Data("{}".utf8)))
            let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return (object?["conversation"] as? [String: Any])?["id"] as? String
        } catch APIError.http(404, _) {
            return nil
        }
    }

    func finalizeConversation(id: String) async throws {
        _ = try await data(.post, "v1/conversations/\(id)/finalize", body: .json(Data("{}".utf8)))
    }
}

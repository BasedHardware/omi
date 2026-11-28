import Foundation

/// A speech-to-text service the app talks to itself (Flutter "Custom STT", `stt_provider.dart`):
/// the phone sends the audio there and hands the words to `/v4/listen` as `suggested_transcript`
/// (`custom_stt=enabled`), so Omi's managed transcription and its minutes are not used.
/// Raw values are Flutter's `SttProvider` names, so a config saved by the Flutter app still reads.
public enum CustomSTTProvider: String, CaseIterable, Sendable {
    /// OpenAI Whisper (`whisper-1`), 3 s chunks over HTTP.
    case openai
    /// OpenAI GPT-4o Transcribe Diarize: chunks over HTTP, with speakers.
    case openaiDiarize
    /// Deepgram Nova over a live WebSocket.
    case deepgramLive
    /// A self-hosted whisper.cpp server (`/inference`), no key.
    case localWhisper
    /// Any HTTP endpoint that takes a WAV upload and answers like OpenAI (`segments` or `text`).
    case custom

    public var requiresAPIKey: Bool {
        switch self {
        case .openai, .openaiDiarize, .deepgramLive: true
        case .localWhisper, .custom: false
        }
    }

    /// Streams over a WebSocket; the others post a WAV every few seconds.
    public var isLive: Bool {
        self == .deepgramLive
    }

    /// The endpoint is the user's (`localWhisper`, `custom`).
    public var takesURL: Bool {
        self == .localWhisper || self == .custom
    }

    public var displayName: String {
        switch self {
        case .openai: "OpenAI Whisper"
        case .openaiDiarize: "OpenAI GPT-4o Transcribe Diarize"
        case .deepgramLive: "Deepgram"
        case .localWhisper: "Local Whisper"
        case .custom: "Custom"
        }
    }

    public var models: [String] {
        switch self {
        case .openai: ["whisper-1"]
        case .openaiDiarize: ["gpt-4o-transcribe-diarize"]
        case .deepgramLive: ["nova-3"]
        case .localWhisper, .custom: []
        }
    }

    public var defaultLanguage: String {
        self == .deepgramLive ? "multi" : "en"
    }

    /// The placeholder for `url` (`stt_provider.dart` `buildRequestConfig`).
    public var defaultURL: String? {
        switch self {
        case .localWhisper, .custom: "http://127.0.0.1:8080/inference"
        default: nil
        }
    }

    /// Where the user gets a key.
    public var apiKeyURL: URL? {
        switch self {
        case .openai, .openaiDiarize: URL(string: "https://platform.openai.com/api-keys")
        case .deepgramLive: URL(string: "https://console.deepgram.com/")
        case .localWhisper, .custom: nil
        }
    }
}

/// One saved provider setup. The key lives in the Keychain (`CustomSTTSettings`), never here on disk.
public struct CustomSTTConfig: Sendable, Equatable {
    public var provider: CustomSTTProvider
    public var apiKey: String?
    public var model: String?
    /// ISO code, or `multi` to detect.
    public var language: String?
    public var url: String?

    public init(provider: CustomSTTProvider, apiKey: String? = nil, model: String? = nil, language: String? = nil, url: String? = nil) {
        self.provider = provider
        self.apiKey = apiKey
        self.model = model
        self.language = language
        self.url = url
    }

    public var effectiveModel: String {
        model.flatMap { $0.isEmpty ? nil : $0 } ?? provider.models.first ?? ""
    }

    public var effectiveLanguage: String {
        language.flatMap { $0.isEmpty ? nil : $0 } ?? provider.defaultLanguage
    }

    /// Everything needed to send audio (a key when the provider needs one, a valid endpoint).
    public var isComplete: Bool {
        if provider.requiresAPIKey, (apiKey ?? "").trimmingCharacters(in: .whitespaces).isEmpty { return false }
        if provider.takesURL { return endpoint != nil }
        return true
    }

    var endpoint: URL? {
        switch provider {
        case .openai, .openaiDiarize: URL(string: "https://api.openai.com/v1/audio/transcriptions")
        case .deepgramLive: URL(string: "wss://api.deepgram.com/v1/listen")
        case .localWhisper, .custom:
            (url.flatMap { $0.isEmpty ? nil : $0 } ?? provider.defaultURL).flatMap(URL.init(string:))
                .flatMap { ["http", "https"].contains($0.scheme?.lowercased() ?? "") ? $0 : nil }
        }
    }
}

/// A piece of transcript from a provider; times are seconds from the start of what was sent.
public struct CustomSTTSegment: Equatable, Sendable {
    public let text: String
    public let start: Double
    public let end: Double
    /// The provider's speaker number, when it separates speakers.
    public let speaker: Int?

    public init(text: String, start: Double, end: Double, speaker: Int? = nil) {
        self.text = text
        self.start = start
        self.end = end
        self.speaker = speaker
    }
}

public enum CustomSTTError: Error, Equatable, Sendable {
    case incomplete
    case http(status: Int)
    case undecodable
}

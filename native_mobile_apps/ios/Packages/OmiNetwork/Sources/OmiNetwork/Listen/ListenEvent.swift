import Foundation

/// One live transcript segment from `/v4/listen`. Segments are re-sent with the same id when the
/// backend refines them, so clients upsert by id.
public struct LiveSegment: Identifiable, Hashable, Sendable, Codable {
    public let id: String
    public let text: String
    public let speaker: String?
    public let speakerID: Int?
    public let isUser: Bool
    public let start: Double
    public let end: Double
    /// The person the backend matched this voice to (`person_id`).
    public let personID: String?
    /// The backend's translations into the primary language (`translating`, Automatic translation).
    public var translations: [Translation]

    /// One translated text (backend `models/transcript_segment.py` `Translation`).
    public struct Translation: Hashable, Sendable, Codable {
        public let lang: String
        public let text: String

        public init(lang: String, text: String) {
            self.lang = lang
            self.text = text
        }
    }

    public init(
        id: String, text: String, speaker: String?, speakerID: Int?, isUser: Bool, start: Double, end: Double, personID: String? = nil,
        translations: [Translation] = []
    ) {
        self.id = id
        self.text = text
        self.speaker = speaker
        self.speakerID = speakerID
        self.isUser = isUser
        self.start = start
        self.end = end
        self.personID = personID
        self.translations = translations
    }

    enum CodingKeys: String, CodingKey {
        case id, text, speaker, start, end, translations
        case speakerID = "speaker_id"
        case isUser = "is_user"
        case personID = "person_id"
    }

    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
        speaker = try c.decodeIfPresent(String.self, forKey: .speaker)
        speakerID = try c.decodeIfPresent(Int.self, forKey: .speakerID)
        isUser = try c.decodeIfPresent(Bool.self, forKey: .isUser) ?? false
        start = try c.decodeIfPresent(Double.self, forKey: .start) ?? 0
        end = try c.decodeIfPresent(Double.self, forKey: .end) ?? start
        personID = try c.decodeIfPresent(String.self, forKey: .personID).flatMap { $0.isEmpty ? nil : $0 }
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? "\(start)-\(text.hashValue)"
        translations = (try? c.decodeIfPresent([Translation].self, forKey: .translations)) ?? []
    }
}

/// Server → client messages on `/v4/listen` (backend `models/message_event.py`).
public enum ListenEvent: Sendable, Equatable {
    case segments([LiveSegment])
    /// `service_status`: initiating, stt_initiating, ready, stt_failed …
    case status(String)
    /// The live conversation id (`conversation_session`).
    case conversationStarted(id: String)
    case processingStarted(conversationID: String)
    /// `memory_created`: the conversation is finalized.
    case conversationCreated(id: String)
    case segmentsDeleted([String])
    /// `translating`: segments sent again with their translations (only the translations are new).
    case translated([LiveSegment])
    /// `freemium_threshold_reached`: the plan's transcription minutes run out soon (or did, at 0).
    /// `requiresOnDevice`: the backend asks the app to transcribe on the phone (`setup_on_device_stt`).
    case freemiumThreshold(remainingSeconds: Int, requiresOnDevice: Bool)
    case other(type: String)

    /// Parses one text frame. Arrays are segments; objects are typed events; `"ping"` is nil.
    public static func parse(_ text: String) -> ListenEvent? {
        guard text != "ping", let data = text.data(using: .utf8) else { return nil }
        if text.first == "[" {
            return (try? JSONDecoder().decode([LiveSegment].self, from: data)).map { .segments($0) }
        }
        guard let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let type = object["type"] as? String else { return nil }
        switch type {
        case "service_status":
            // Older backends announced the threshold as a status (Flutter still accepts both).
            if object["status"] as? String == "freemium_threshold_reached" { return freemium(object) }
            return .status(object["status"] as? String ?? "unknown")
        case "freemium_threshold_reached":
            return freemium(object)
        case "translating":
            let segments = (object["segments"] as? [Any]).flatMap { try? JSONSerialization.data(withJSONObject: $0) }
                .flatMap { try? JSONDecoder().decode([LiveSegment].self, from: $0) } ?? []
            return .translated(segments)
        case "conversation_session":
            return (object["conversation_id"] as? String).map { .conversationStarted(id: $0) }
        case "memory_processing_started":
            return (object["conversation_id"] as? String).map { .processingStarted(conversationID: $0) }
        case "memory_created":
            let id = object["conversation_id"] as? String ?? (object["memory"] as? [String: Any])?["id"] as? String
            return id.map { .conversationCreated(id: $0) }
        case "segments_deleted":
            return .segmentsDeleted(object["segment_ids"] as? [String] ?? [])
        default:
            return .other(type: type)
        }
    }

    private static func freemium(_ object: [String: Any]) -> ListenEvent {
        .freemiumThreshold(
            remainingSeconds: (object["remaining_seconds"] as? NSNumber)?.intValue ?? 0,
            requiresOnDevice: object["action"] as? String == "setup_on_device_stt"
        )
    }
}

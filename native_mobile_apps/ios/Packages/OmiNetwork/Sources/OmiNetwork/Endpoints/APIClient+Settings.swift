import Foundation

public struct Person: Identifiable, Hashable, Sendable {
    /// How sure Omi is about this voice (backend `PersonConfidence`).
    public enum Confidence: String, Sendable { case confirmed, likely, unverified, unknown }

    public let id: String
    public var name: String
    public var sampleCount: Int
    /// Signed URLs of the saved voice samples (playable without auth headers).
    public var sampleURLs: [URL]
    /// Pinned people stay out of Clean up.
    public var isPinned: Bool
    public var confidence: Confidence
    /// Stats, only from `GET v1/users/people?include_stats=true`.
    public var conversationCount: Int?
    public var talkSeconds: Double?
    public var lastHeardAt: Date?

    public init(
        id: String, name: String, sampleCount: Int, sampleURLs: [URL] = [], isPinned: Bool = false,
        confidence: Confidence = .unknown, conversationCount: Int? = nil, talkSeconds: Double? = nil, lastHeardAt: Date? = nil
    ) {
        self.id = id
        self.name = name
        self.sampleCount = sampleCount
        self.sampleURLs = sampleURLs
        self.isPinned = isPinned
        self.confidence = confidence
        self.conversationCount = conversationCount
        self.talkSeconds = talkSeconds
        self.lastHeardAt = lastHeardAt
    }
}

public struct PhoneNumber: Identifiable, Hashable, Sendable {
    public let id: String
    public let number: String
    public let isVerified: Bool

    public init(id: String, number: String, isVerified: Bool) {
        self.id = id
        self.number = number
        self.isVerified = isVerified
    }
}

public extension APIClient {
    private func object(_ method: Method, _ path: String, query: [URLQueryItem] = [],
                        json: [String: Any]? = nil) async throws -> [String: Any]
    {
        let body: Body = try json.map { try .json(JSONSerialization.data(withJSONObject: $0)) } ?? .none
        let data = try await data(method, path, query: query, body: body)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    // MARK: Notifications

    func dailySummary() async throws -> (enabled: Bool, hour: Int) {
        let object = try await object(.get, "v1/users/daily-summary-settings")
        return (object["enabled"] as? Bool ?? true, object["hour"] as? Int ?? 22)
    }

    func setDailySummary(enabled: Bool, hour: Int) async throws {
        _ = try await object(.patch, "v1/users/daily-summary-settings", json: ["enabled": enabled, "hour": hour])
    }

    func notificationFrequency() async throws -> Int {
        try await object(.get, "v1/users/mentor-notification-settings")["frequency"] as? Int ?? 0
    }

    func setNotificationFrequency(_ value: Int) async throws {
        _ = try await object(.patch, "v1/users/mentor-notification-settings", json: ["frequency": value])
    }

    // MARK: Privacy

    func storesRecordings() async throws -> Bool {
        try await object(.get, "v1/users/store-recording-permission")["store_recording_permission"] as? Bool ?? false
    }

    func setStoresRecordings(_ value: Bool) async throws {
        _ = try await object(.post, "v1/users/store-recording-permission", query: [URLQueryItem(name: "value", value: String(value))])
    }

    // MARK: Assistant voice

    func assistantVoices() async throws -> (voices: [(id: String, name: String)], selected: String?) {
        let catalog = try await object(.get, "v1/tts/voices")
        let voices = (catalog["voices"] as? [[String: Any]] ?? []).compactMap { voice -> (id: String, name: String)? in
            guard let id = voice["id"] as? String else { return nil }
            return (id, voice["name"] as? String ?? id)
        }
        let selected = try? await object(.get, "v1/users/voice")["voice_id"] as? String
        return (voices, selected ?? catalog["default_voice_id"] as? String)
    }

    func setAssistantVoice(_ id: String) async throws {
        _ = try await object(.patch, "v1/users/voice", json: ["voice_id": id])
    }

    // MARK: Vocabulary

    func vocabulary() async throws -> [String] {
        try await object(.get, "v1/users/transcription-preferences")["vocabulary"] as? [String] ?? []
    }

    func setVocabulary(_ words: [String]) async throws {
        _ = try await object(.patch, "v1/users/transcription-preferences", json: ["vocabulary": words])
    }

    // MARK: People

    func people() async throws -> [Person] {
        let data = try await data(.get, "v1/users/people", query: [URLQueryItem(name: "include_speech_samples", value: "true")])
        return try (JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []).compactMap(PersonMapper.map)
    }

    func addPerson(_ name: String) async throws {
        _ = try await object(.post, "v1/users/people", json: ["name": name])
    }

    func renamePerson(_ id: String, to name: String) async throws {
        _ = try await object(.patch, "v1/users/people/\(id)/name", query: [URLQueryItem(name: "value", value: name)])
    }

    func deletePerson(_ id: String) async throws {
        _ = try await object(.delete, "v1/users/people/\(id)")
    }

    // MARK: Phone

    func phoneNumbers() async throws -> [PhoneNumber] {
        let object = try await object(.get, "v1/phone/numbers")
        return (object["numbers"] as? [[String: Any]] ?? []).compactMap { item in
            guard let id = item["id"] as? String else { return nil }
            return PhoneNumber(id: id, number: item["phone_number"] as? String ?? "", isVerified: item["verified_at"] != nil)
        }
    }
}

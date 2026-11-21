import Foundation
import OmiCore

/// The webhooks Omi calls for the user's own tools (backend `models/users.py` `WebhookType`).
public enum DeveloperWebhook: String, CaseIterable, Sendable, Identifiable {
    /// "Conversation events": a conversation was created (the backend still calls it a memory).
    case conversationCreated = "memory_created"
    case realtimeTranscript = "realtime_transcript"
    /// Raw audio every few seconds; the interval travels in the URL field as `<url>,<seconds>`.
    case audioBytes = "audio_bytes"
    case daySummary = "day_summary"

    public var id: String {
        rawValue
    }

    /// The backend default for the audio interval (`utils/webhooks.py`).
    public static let defaultAudioInterval = 5

    /// Splits the stored `<url>,<seconds>` of the audio webhook.
    public static func splitAudio(_ stored: String) -> (url: String, seconds: Int) {
        let parts = stored.split(separator: ",", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
        let seconds = parts.count > 1 ? Int(parts[1]) ?? defaultAudioInterval : defaultAudioInterval
        return (parts.first ?? "", max(1, seconds))
    }

    public static func joinAudio(url: String, seconds: Int) -> String {
        url.isEmpty ? "" : "\(url),\(max(1, seconds))"
    }
}

/// A developer API key (`v1/dev/keys`) or MCP key (`v1/mcp/keys`). `secret` is only present right
/// after creation: the backend never shows it again.
public struct DeveloperKey: Identifiable, Hashable, Sendable {
    public enum Kind: String, Sendable { case api = "dev", mcp }

    public let id: String
    public let name: String
    /// e.g. `omi_dev_1e0b...ae0a`.
    public let prefix: String
    public let createdAt: Date?
    public let lastUsedAt: Date?
    public let scopes: [String]
    public let secret: String?

    public init(id: String, name: String, prefix: String, createdAt: Date?, lastUsedAt: Date?, scopes: [String], secret: String?) {
        self.id = id
        self.name = name
        self.prefix = prefix
        self.createdAt = createdAt
        self.lastUsedAt = lastUsedAt
        self.scopes = scopes
        self.secret = secret
    }

    static func from(_ object: [String: Any]) -> DeveloperKey? {
        guard let id = object["id"] as? String else { return nil }
        return DeveloperKey(
            id: id, name: object["name"] as? String ?? "", prefix: object["key_prefix"] as? String ?? "",
            createdAt: BackendDate.parse(object["created_at"] as? String),
            lastUsedAt: BackendDate.parse(object["last_used_at"] as? String),
            scopes: object["scopes"] as? [String] ?? [], secret: object["key"] as? String
        )
    }
}

public extension APIClient {
    /// `GET v1/users/developer/webhooks/status`: which webhooks are on.
    func webhookStatus() async throws -> [DeveloperWebhook: Bool] {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/users/developer/webhooks/status")) as? [String: Any]
        var result: [DeveloperWebhook: Bool] = [:]
        for hook in DeveloperWebhook.allCases {
            result[hook] = object?[hook.rawValue] as? Bool ?? false
        }
        return result
    }

    /// `GET v1/users/developer/webhook/{type}` → the stored URL ("" when none).
    func webhookURL(_ hook: DeveloperWebhook) async throws -> String {
        let response = try await data(.get, "v1/users/developer/webhook/\(hook.rawValue)")
        let object = try JSONSerialization.jsonObject(with: response) as? [String: Any]
        return object?["url"] as? String ?? ""
    }

    /// `POST v1/users/developer/webhook/{type}`. An empty URL also turns the webhook off, any other
    /// turns it on; a private or malformed address is refused (400).
    func setWebhookURL(_ hook: DeveloperWebhook, url: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["url": url])
        _ = try await data(.post, "v1/users/developer/webhook/\(hook.rawValue)", body: .json(body))
    }

    /// `POST v1/users/developer/webhook/{type}/enable|disable`.
    func setWebhook(_ hook: DeveloperWebhook, enabled: Bool) async throws {
        _ = try await data(.post, "v1/users/developer/webhook/\(hook.rawValue)/\(enabled ? "enable" : "disable")")
    }

    /// `GET v1/dev/keys` or `v1/mcp/keys`.
    func developerKeys(_ kind: DeveloperKey.Kind) async throws -> [DeveloperKey] {
        let array = try await JSONSerialization.jsonObject(with: data(.get, "v1/\(kind.rawValue)/keys")) as? [[String: Any]] ?? []
        return array.compactMap(DeveloperKey.from)
    }

    /// `POST v1/dev/keys` / `v1/mcp/keys` with a name; the answer carries the secret once.
    /// API keys without scopes are read-only (backend `utils/scopes.py`).
    func createDeveloperKey(_ kind: DeveloperKey.Kind, name: String, scopes: [String]?) async throws -> DeveloperKey {
        var body: [String: Any] = ["name": name]
        if let scopes { body["scopes"] = scopes }
        let data = try await data(.post, "v1/\(kind.rawValue)/keys", body: .json(JSONSerialization.data(withJSONObject: body)))
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any], let key = DeveloperKey.from(object) else {
            throw APIError.decoding("key without id")
        }
        return key
    }

    /// `DELETE v1/dev/keys/{id}` / `v1/mcp/keys/{id}` (204).
    func revokeDeveloperKey(_ kind: DeveloperKey.Kind, id: String) async throws {
        _ = try await data(.delete, "v1/\(kind.rawValue)/keys/\(id)")
    }
}

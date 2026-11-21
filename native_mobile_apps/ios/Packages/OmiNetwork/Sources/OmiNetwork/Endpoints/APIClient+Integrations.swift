import Foundation
import OmiCore

/// Something Omi can connect to (calendar, mail, task apps).
public struct Integration: Identifiable, Hashable, Sendable {
    public enum Kind: Sendable { case integration, taskApp }
    public let id: String
    public let kind: Kind
    public var isConnected: Bool

    public init(id: String, kind: Kind, isConnected: Bool) {
        self.id = id
        self.kind = kind
        self.isConnected = isConnected
    }
}

public extension APIClient {
    /// `GET v1/users/available-languages` → (name, code).
    func availableLanguages() async throws -> [(name: String, code: String)] {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/users/available-languages")) as? [String: Any]
        return (object?["languages"] as? [[String: Any]] ?? []).compactMap { item in
            guard let name = item["name"] as? String, let code = item["code"] as? String else { return nil }
            return (name, code)
        }
    }

    /// `GET v1/integrations/{key}` → connected (google_calendar, gmail, apple_health).
    func integrationConnected(_ key: String) async throws -> Bool {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/integrations/\(key)")) as? [String: Any]
        return object?["connected"] as? Bool ?? false
    }

    /// `GET v1/integrations/{key}/oauth-url` or `v1/task-integrations/{key}/oauth-url` → URL to open.
    /// The backend redirects to `omi://{key}/callback?success=true` when done.
    func integrationOAuthURL(_ integration: Integration) async throws -> URL {
        let base = integration.kind == .taskApp ? "v1/task-integrations" : "v1/integrations"
        // Gmail shares Google's OAuth client with the calendar (Flutter gmail_service.dart).
        let key = integration.id == "gmail" ? "google_calendar" : integration.id
        let object = try await JSONSerialization.jsonObject(with: data(.get, "\(base)/\(key)/oauth-url")) as? [String: Any]
        guard let string = object?["auth_url"] as? String, let url = URL(string: string) else {
            throw APIError.decoding("no auth_url")
        }
        return url
    }

    /// `DELETE v1/integrations/{key}` / `v1/task-integrations/{key}`
    func disconnectIntegration(_ integration: Integration) async throws {
        let base = integration.kind == .taskApp ? "v1/task-integrations" : "v1/integrations"
        _ = try await data(.delete, "\(base)/\(integration.id)")
    }

    /// `GET v1/task-integrations` → connected task apps.
    func connectedTaskApps() async throws -> Set<String> {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/task-integrations")) as? [String: Any]
        let integrations = object?["integrations"] as? [String: Any] ?? [:]
        return Set(integrations.compactMap { key, value in
            let connected = (value as? [String: Any])?["connected"] as? Bool ?? true
            return connected ? key : nil
        })
    }
}

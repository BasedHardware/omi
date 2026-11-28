import Foundation
import OmiCore

/// Apple Health (backend `routers/integrations.py`, key `apple_health`; Flutter `integrations.dart`).
/// Connected state is `GET v1/integrations/apple_health`; disconnect is `DELETE v1/integrations/apple_health`.
public extension APIClient {
    /// `PUT v1/integrations/apple-health/sync`: the summary the chat answers health questions from.
    /// Returns the server's `synced_at`.
    @discardableResult
    func syncAppleHealth(_ summary: HealthSummary) async throws -> Date? {
        let body = try JSONSerialization.data(withJSONObject: summary.syncBody)
        let response = try await data(.put, "v1/integrations/apple-health/sync", body: .json(body))
        let object = try JSONSerialization.jsonObject(with: response) as? [String: Any]
        guard object?["status"] as? String == "ok" else { throw APIError.decoding("apple health sync status") }
        return BackendDate.parse(object?["synced_at"] as? String)
    }

    /// `PUT v1/integrations/apple_health` with `{}` (`connected` defaults to true): Flutter's
    /// `saveConnection` after the first sync.
    func markAppleHealthConnected() async throws {
        _ = try await data(.put, "v1/integrations/apple_health", body: .json(Data("{}".utf8)))
    }
}

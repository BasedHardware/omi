import Foundation

public extension APIClient {
    /// `GET v1/users/transcription-preferences` → `single_language_mode`. Off means the backend
    /// detects the languages spoken (Flutter "Automatic translation · Detect languages").
    func singleLanguageMode() async throws -> Bool {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/users/transcription-preferences")) as? [String: Any]
        return object?["single_language_mode"] as? Bool ?? false
    }

    /// `PATCH v1/users/transcription-preferences`; applies from the next `/v4/listen`.
    func setSingleLanguageMode(_ value: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["single_language_mode": value])
        _ = try await data(.patch, "v1/users/transcription-preferences", body: .json(body))
    }
}

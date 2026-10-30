import Foundation
import OmiCore

/// Server-side onboarding state (`GET v1/users/onboarding`).
public struct OnboardingState: Sendable, Equatable {
    public let completed: Bool
    public let acquisitionSource: String?

    public init(completed: Bool, acquisitionSource: String?) {
        self.completed = completed
        self.acquisitionSource = acquisitionSource
    }
}

public extension APIClient {
    func onboardingState() async throws -> OnboardingState {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/users/onboarding")) as? [String: Any] ?? [:]
        let source = object["acquisition_source"] as? String
        return OnboardingState(completed: object["completed"] as? Bool ?? false, acquisitionSource: source?.isEmpty == true ? nil : source)
    }

    /// `PATCH v1/users/onboarding` with whichever fields are set.
    func updateOnboarding(completed: Bool?, acquisitionSource: String?) async throws {
        var fields: [String: Any] = [:]
        if let completed { fields["completed"] = completed }
        if let acquisitionSource { fields["acquisition_source"] = acquisitionSource }
        _ = try await data(.patch, "v1/users/onboarding", body: .json(JSONSerialization.data(withJSONObject: fields)))
    }

    /// `GET v1/users/language` → primary language code, if set.
    func primaryLanguage() async throws -> String? {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/users/language")) as? [String: Any]
        return (object?["language"] as? String).flatMap { $0.isEmpty ? nil : $0 }
    }

    /// `PATCH v1/users/language`; the server also updates transcription preferences.
    func setPrimaryLanguage(_ code: String) async throws {
        _ = try await data(.patch, "v1/users/language", body: .json(JSONSerialization.data(withJSONObject: ["language": code])))
    }

    /// `PUT v1/users/time-zone`
    func setTimeZone(_ identifier: String) async throws {
        _ = try await data(.put, "v1/users/time-zone", body: .json(JSONSerialization.data(withJSONObject: ["time_zone": identifier])))
    }

    /// `DELETE v1/users/delete-account`
    func deleteAccount(reason: String?) async throws {
        let body: Body = try reason.map { try .json(JSONSerialization.data(withJSONObject: ["reason": $0])) } ?? .none
        _ = try await data(.delete, "v1/users/delete-account", body: body)
    }
}

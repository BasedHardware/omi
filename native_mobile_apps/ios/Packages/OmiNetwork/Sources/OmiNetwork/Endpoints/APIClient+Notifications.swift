import Foundation

public extension APIClient {
    /// `POST v1/users/fcm-token` (Flutter's `saveFcmTokenServer`). The backend files the token under
    /// `<X-App-Platform>_<X-Device-Id-Hash>`, so sending Flutter's hash replaces that install's token.
    func saveNotificationToken(_ token: String, timeZone: String, deviceIDHash: String?) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["fcm_token": token, "time_zone": timeZone])
        let headers = deviceIDHash.map { ["X-Device-Id-Hash": $0] } ?? [:]
        _ = try await data(.post, "v1/users/fcm-token", body: .json(body), headers: headers)
    }
}

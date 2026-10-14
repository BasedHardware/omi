import Foundation
import OmiCore

/// Where conversations happen (backend `routers/users.py` geolocation, `routers/transcribe.py` header).
/// The recording's own position travels on the listen socket (`ListenSocket.Options.geolocation`).
public extension APIClient {
    /// `PATCH v1/users/geolocation`: the backend's short-lived user-location cache, which delayed
    /// processing falls back to (Flutter `uploadCompatibilitySnapshot`). Best effort.
    func updateUserGeolocation(_ snapshot: GeolocationSnapshot) async throws {
        let body = try JSONSerialization.data(withJSONObject: snapshot.jsonObject)
        _ = try await data(.patch, "v1/users/geolocation", body: .json(body))
    }
}

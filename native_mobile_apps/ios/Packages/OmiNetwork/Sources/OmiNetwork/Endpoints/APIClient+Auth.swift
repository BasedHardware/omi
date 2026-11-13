import Foundation

private struct CustomTokenResponse: Decodable {
    let customToken: String

    enum CodingKeys: String, CodingKey { case customToken = "custom_token" }
}

public extension APIClient {
    /// `POST v1/auth/local-dev/custom-token`. Only registered when the backend runs against the
    /// Firebase Auth emulator (local harness); 404 everywhere else.
    func localDevCustomToken(uid: String) async throws -> String {
        let data = try await data(.post, "v1/auth/local-dev/custom-token", body: .form(["uid": uid]), authenticated: false)
        return try decode(CustomTokenResponse.self, from: data).customToken
    }
}

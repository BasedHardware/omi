import Foundation

extension APIClient {
  /// Flags the Omi flag store owns for this account. Keys it does not list keep reading PostHog.
  func clientFlags() async throws -> [OmiFlag] {
    let response: OmiAPI.ClientFlagsResponse = try await get(
      "v1/flags", queryItems: [URLQueryItem(name: "surface", value: "macos")])
    return response.flags.map {
      OmiFlag(key: $0.key, enabled: $0.enabled, variant: $0.variant, payloadJson: $0.payloadJson)
    }
  }
}

import Foundation

struct ReferralLinkResponse: Decodable, Equatable {
  let referralURL: String

  enum CodingKeys: String, CodingKey {
    case referralURL = "referral_url"
  }
}

extension APIClient {
  func getReferralLink() async throws -> ReferralLinkResponse {
    try await get(
      "v1/users/me/referral",
      customBaseURL: DesktopBackendEnvironment.authBaseURL()
    )
  }
}

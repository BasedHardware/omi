import Foundation

/// Server-driven config for the built-in product CSAT ask
/// (`csat_config/product` in Firestore, served by `GET /v1/csat/config`).
/// Admin.omi.me edits the copy; clients pick changes up within one poll.
struct CsatConfig: Codable, Equatable {
  let enabled: Bool
  let title: String
  let body: String
  let thankYouText: String
  let referCtaText: String
  let questionThreshold: Int
  let commentMaxScore: Int
  let revision: Int

  enum CodingKeys: String, CodingKey {
    case enabled, title, body, revision
    case thankYouText = "thank_you_text"
    case referCtaText = "refer_cta_text"
    case questionThreshold = "question_threshold"
    case commentMaxScore = "comment_max_score"
  }

  /// Hardcoded copy of the server defaults (`backend/database/csat.py`).
  /// This is the fail-open branch when no fetch has ever succeeded; the
  /// PostHog kill switch still applies on top of it.
  static let fallback = CsatConfig(
    enabled: true,
    title: "How would you rate Omi Desktop?",
    body: "",
    thankYouText: "Thank you!",
    referCtaText: "Enjoying Omi? Give a friend a free month.",
    questionThreshold: 3,
    commentMaxScore: 3,
    revision: 0
  )
}

struct CsatRatingReceipt: Decodable {
  let id: String
  let created: Bool
}

private struct CsatRatingBody: Encodable {
  let platform: String
  let appVersion: String
  let score: Int
  let comment: String
  let revision: Int

  enum CodingKeys: String, CodingKey {
    case platform, score, comment, revision
    case appVersion = "app_version"
  }
}

extension APIClient {
  func getCsatConfig(platform: String = "macos") async throws -> CsatConfig {
    try await get(
      "v1/csat/config?platform=\(platform)",
      customBaseURL: DesktopBackendEnvironment.authBaseURL())
  }

  func submitCsatRating(
    score: Int,
    comment: String,
    revision: Int,
    platform: String = "macos"
  ) async throws -> CsatRatingReceipt {
    try await post(
      "v1/csat/ratings",
      body: CsatRatingBody(
        platform: platform,
        appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "",
        score: score,
        comment: comment,
        revision: revision),
      customBaseURL: DesktopBackendEnvironment.authBaseURL())
  }
}

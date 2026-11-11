import Foundation

struct DesktopUsageDailyPayload: Codable, Equatable, Sendable {
  let date: String
  let timezone: String
  let clientDeviceID: String
  var watchingSeconds: Int
  var listeningSeconds: Int
  var proactiveCardsShown: Int
  var proactiveCardsActed: Int
  var pttTurns: Int

  enum CodingKeys: String, CodingKey {
    case date
    case timezone
    case clientDeviceID = "client_device_id"
    case watchingSeconds = "watching_seconds"
    case listeningSeconds = "listening_seconds"
    case proactiveCardsShown = "proactive_cards_shown"
    case proactiveCardsActed = "proactive_cards_acted"
    case pttTurns = "ptt_turns"
  }
}

extension APIClient {
  private struct DesktopUsageDailyResponse: Decodable {}

  func postDesktopUsageDaily(_ payload: DesktopUsageDailyPayload) async throws {
    let _: DesktopUsageDailyResponse = try await post(
      "v1/users/desktop-usage/daily",
      body: payload,
      includeBYOK: false)
  }
}

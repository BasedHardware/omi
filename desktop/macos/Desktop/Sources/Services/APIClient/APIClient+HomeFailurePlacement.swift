import Foundation

struct HomeFailurePlacementSnapshot: Decodable {
  let enabled: Bool?
  let homeProcessingToday: Bool?

  enum CodingKeys: String, CodingKey {
    case enabled
    case homeProcessingToday = "home_processing_today"
  }

  var confirmed: Bool { enabled == true && homeProcessingToday == true }
}

extension APIClient {
  func getHomeFailurePlacement() async throws -> Bool {
    let snapshot: HomeFailurePlacementSnapshot = try await get("v1/pending-work")
    return snapshot.confirmed
  }
}

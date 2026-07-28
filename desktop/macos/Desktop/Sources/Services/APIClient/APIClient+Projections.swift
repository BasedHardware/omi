import Foundation

// MARK: - Projections Models

/// Domain model adapted from the generated `OmiAPI.ProjectionResponse` wire type.
/// A projection is one generated image carrying one future-tense imperative.
struct Projection: Identifiable, Sendable {
  let id: String
  let imperative: String
  let imageURL: URL?

  init?(_ dto: OmiAPI.ProjectionResponse) {
    guard let id = dto.id else { return nil }
    self.id = id
    self.imperative = dto.imperative ?? ""
    self.imageURL = dto.imageUrl.flatMap(URL.init(string:))
  }
}

// MARK: - Projections API

extension APIClient {

  /// Lists the signed-in user's projections, newest first.
  func getProjections(
    limit: Int = 30,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> [Projection] {
    let response: OmiAPI.ProjectionsResponse = try await get(
      "v1/users/projections?limit=\(limit)",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    return (response.projections ?? []).compactMap(Projection.init)
  }

  /// Generates a projection immediately rather than waiting for a scheduled run.
  func generateProjection(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Projection? {
    let response: OmiAPI.ProjectionResponse = try await post(
      "v1/users/projections/test",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    return Projection(response)
  }
}

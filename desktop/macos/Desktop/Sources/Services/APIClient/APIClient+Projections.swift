import Foundation

// MARK: - Projections Models

/// Domain model adapted from the generated `OmiAPI.ProjectionResponse` wire type.
/// A projection is one generated image carrying one future-tense imperative.
struct Projection: Identifiable, Sendable {
  let id: String
  let imperative: String
  let imageURL: URL?

  init(id: String, imperative: String, imageURL: URL?) {
    self.id = id
    self.imperative = imperative
    self.imageURL = imageURL
  }

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

  /// Loads private image bytes through the same owner-bound Firebase session as
  /// the projection document. The backend performs the final uid ownership check.
  func getProjectionImage(
    from url: URL,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Data {
    let authPolicy = try resolvedRequestAuthPolicy(
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    try validateExpectedOwner(authPolicy)

    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true,
      includeBYOK: false,
      expectedAuthOwnerId: authPolicy.expectedAuthOwnerId)
    try validateExpectedOwner(authPolicy)

    let (data, response) = try await performAuthenticatedData(
      for: request,
      authPolicy: authPolicy)
    guard (200...299).contains(response.statusCode) else {
      let detail = OmiHTTPTransport.extractErrorDetail(from: data)
      throw APIError.httpError(statusCode: response.statusCode, detail: detail)
    }
    guard !data.isEmpty else { throw APIError.invalidResponse }
    try validateExpectedOwner(authPolicy)
    return data
  }
}

import Foundation

// MARK: - Projections Models

/// Domain model adapted from the generated `OmiAPI.ProjectionResponse` wire type.
/// A projection is the internal model for one grounded Omen.
struct Projection: Identifiable, Sendable {
  let id: String
  let imperative: String
  let imageURL: URL?
  let whyThis: ProjectionWhyThis?
  let feedback: ProjectionFeedbackRating?

  init(
    id: String,
    imperative: String,
    imageURL: URL?,
    whyThis: ProjectionWhyThis? = nil,
    feedback: ProjectionFeedbackRating? = nil
  ) {
    self.id = id
    self.imperative = imperative
    self.imageURL = imageURL
    self.whyThis = whyThis
    self.feedback = feedback
  }

  init?(_ dto: OmiAPI.ProjectionResponse) {
    guard let id = dto.id else { return nil }
    self.id = id
    self.imperative = dto.imperative ?? ""
    self.imageURL = dto.imageUrl.flatMap(URL.init(string:))
    self.whyThis = dto.whyThis.map(ProjectionWhyThis.init)
    self.feedback = dto.feedback.flatMap { ProjectionFeedbackRating(rawValue: $0.rating) }
  }
}

struct ProjectionWhyThis: Sendable {
  let evidence: [ProjectionEvidenceReceipt]
  let evidenceTier: String
  let selectionRank: Int
  let uncertainty: [String]

  init(
    evidence: [ProjectionEvidenceReceipt],
    evidenceTier: String,
    selectionRank: Int,
    uncertainty: [String]
  ) {
    self.evidence = evidence
    self.evidenceTier = evidenceTier
    self.selectionRank = selectionRank
    self.uncertainty = uncertainty
  }

  init(_ dto: OmiAPI.ProjectionWhyThis) {
    evidence = (dto.evidence ?? []).map(ProjectionEvidenceReceipt.init)
    evidenceTier = dto.evidenceTier
    selectionRank = dto.selectionRank
    uncertainty = dto.uncertainty ?? []
  }
}

struct ProjectionEvidenceReceipt: Identifiable, Sendable {
  var id: String { reference }

  let reference: String
  let source: String
  let label: String
  let occurredAt: String?

  init(reference: String, source: String, label: String, occurredAt: String?) {
    self.reference = reference
    self.source = source
    self.label = label
    self.occurredAt = occurredAt
  }

  init(_ dto: OmiAPI.ProjectionEvidenceReceipt) {
    reference = dto.reference
    source = dto.source
    label = dto.label
    occurredAt = dto.occurredAt
  }
}

enum ProjectionFeedbackRating: String, Sendable {
  case up
  case down
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
      includeBYOK: false,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    return (response.projections ?? []).compactMap(Projection.init)
  }

  /// Generates a projection through the local-development-only test route.
  func generateProjection(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Projection? {
    let response: OmiAPI.ProjectionResponse = try await post(
      "v1/users/projections/test",
      includeBYOK: false,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot,
      requestTimeoutInterval: 120)
    return Projection(response)
  }

  func recordProjectionFeedback(
    projectionID: String,
    rating: ProjectionFeedbackRating,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ProjectionFeedbackRating {
    let response: OmiAPI.ProjectionFeedback = try await post(
      "v1/users/projections/\(projectionID)/feedback",
      body: OmiAPI.ProjectionFeedbackRequest(rating: rating.rawValue),
      includeBYOK: false,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    guard let recorded = ProjectionFeedbackRating(rawValue: response.rating) else {
      throw APIError.invalidResponse
    }
    return recorded
  }

  /// Loads private image bytes through the same owner-bound Firebase session as
  /// the projection document. The persisted image URL is never trusted as an
  /// authorization destination: this client constructs the route from the
  /// projection UUID and its configured API base.
  func getProjectionImage(
    projectionID: String,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Data {
    guard
      let projectionUUID = UUID(uuidString: projectionID),
      let url = URL(
        string:
          "\(baseURL)v1/projection-images/\(projectionUUID.uuidString.lowercased()).png")
    else {
      throw APIError.invalidResponse
    }
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

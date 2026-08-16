import Foundation

/// Publishes validated context bucket facts to the backend.
///
/// Capture stays on this device. What crosses the boundary is a projection:
/// bucket identity and validated facts, with evidence named by device-local
/// reference rather than carried. Screenshots, quoted screen text, narratives,
/// and window titles are never part of a payload — see
/// `docs/agents/context-buckets.md` for the full boundary.
enum ContextBucketSyncError: LocalizedError, Equatable {
  case invalidResponse
  case http(status: Int, retryAfterSeconds: Int?)
  case ownerChanged

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "context bucket sync received an invalid response"
    case .http(let status, _):
      return "context bucket sync failed with status \(status)"
    case .ownerChanged:
      return "context bucket sync aborted because the signed-in owner changed"
    }
  }
}

/// One validated fact staged for publication.
struct ContextBucketSyncFact: Equatable, Sendable {
  let factID: String
  let bucketID: String
  let statement: String
  let identifiers: [String]
  let confidence: Double
  let notifyWorthiness: Double
  let dispositionState: String
  let workstreamTag: String?
  let expiresAt: Date?
  let updatedAt: Date
}

/// One bucket staged for publication.
struct ContextBucketSyncBucket: Equatable, Sendable {
  let bucketID: String
  let subjectKind: String
  let subjectID: String
  let workstreamID: String?
  let displayLabel: String?
  let notifyWorthiness: Double
  let visitCount: Int
  let lastVisitedAt: Date?
  let updatedAt: Date
}

enum ContextBucketSyncPayload {
  /// Backend caps a sync request at 50 buckets and 200 facts per bucket.
  static let bucketLimit = 50
  static let factLimitPerBucket = 200

  /// Backend rejects any evidence reference that is not device-local, which is
  /// the contract that keeps screen provenance from being promoted to canonical.
  static let evidenceScope = "device_local"
  static let evidenceKind = "local_screen"

  static func isoFormatter() -> ISO8601DateFormatter {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
  }

  /// Build the request body. Facts are grouped under the bucket they belong to;
  /// a fact whose bucket is not being published is dropped rather than orphaned,
  /// because the backend rejects a fact without its bucket.
  static func body(
    deviceID: String,
    buckets: [ContextBucketSyncBucket],
    facts: [ContextBucketSyncFact]
  ) -> [String: Any] {
    let formatter = isoFormatter()
    let publishedBuckets = Array(buckets.prefix(bucketLimit))
    let publishedIDs = Set(publishedBuckets.map(\.bucketID))
    var factsByBucket: [String: [ContextBucketSyncFact]] = [:]
    for fact in facts where publishedIDs.contains(fact.bucketID) {
      factsByBucket[fact.bucketID, default: []].append(fact)
    }

    let bucketPayloads: [[String: Any]] = publishedBuckets.map { bucket in
      var payload: [String: Any] = [
        "bucket_id": bucket.bucketID,
        "subject_kind": bucket.subjectKind,
        "subject_id": bucket.subjectID,
        "notify_worthiness": bucket.notifyWorthiness,
        "visit_count": bucket.visitCount,
        "device_updated_at": formatter.string(from: bucket.updatedAt),
        "facts": (factsByBucket[bucket.bucketID] ?? []).prefix(factLimitPerBucket).map {
          factPayload($0, formatter: formatter, deviceID: deviceID)
        },
      ]
      if let workstreamID = bucket.workstreamID { payload["workstream_id"] = workstreamID }
      if let displayLabel = bucket.displayLabel { payload["display_label"] = displayLabel }
      if let lastVisitedAt = bucket.lastVisitedAt {
        payload["last_visited_at"] = formatter.string(from: lastVisitedAt)
      }
      return payload
    }

    return ["device_id": deviceID, "buckets": bucketPayloads]
  }

  static func factPayload(
    _ fact: ContextBucketSyncFact,
    formatter: ISO8601DateFormatter,
    deviceID: String
  ) -> [String: Any] {
    var payload: [String: Any] = [
      "fact_id": fact.factID,
      "statement": fact.statement,
      "identifiers": fact.identifiers,
      "confidence": fact.confidence,
      "notify_worthiness": fact.notifyWorthiness,
      "disposition_state": fact.dispositionState,
      "device_updated_at": formatter.string(from: fact.updatedAt),
      "evidence_refs": [
        [
          "kind": evidenceKind,
          "id": fact.factID,
          "scope": evidenceScope,
          "device_id": deviceID,
        ]
      ],
    ]
    if let workstreamTag = fact.workstreamTag { payload["workstream_tag"] = workstreamTag }
    if let expiresAt = fact.expiresAt { payload["expires_at"] = formatter.string(from: expiresAt) }
    return payload
  }

  static func purgeBody(bucketIDs: [String]) -> [String: Any] {
    ["bucket_ids": Array(bucketIDs.prefix(200))]
  }

  static func parseRetryAfterSeconds(from response: HTTPURLResponse) -> Int? {
    guard let raw = response.value(forHTTPHeaderField: "Retry-After") else { return nil }
    guard let seconds = Int(raw.trimmingCharacters(in: .whitespaces)) else { return nil }
    return max(0, seconds)
  }
}

actor ContextBucketSyncClient {
  static let shared = ContextBucketSyncClient()
  static var backendBaseURL: String { DesktopBackendEnvironment.rustBackendURL() }

  private let session: URLSession
  private let baseURL: () -> String
  private let authorization: () async throws -> String

  init(
    session: URLSession = .shared,
    baseURL: @escaping () -> String = { ContextBucketSyncClient.backendBaseURL },
    authorization: (() async throws -> String)? = nil
  ) {
    self.session = session
    self.baseURL = baseURL
    self.authorization =
      authorization ?? {
        let authService = await MainActor.run { AuthService.shared }
        return try await authService.getAuthHeader()
      }
  }

  func sync(
    deviceID: String,
    accountGeneration: Int,
    buckets: [ContextBucketSyncBucket],
    facts: [ContextBucketSyncFact]
  ) async throws {
    guard !buckets.isEmpty else { return }
    let body = ContextBucketSyncPayload.body(deviceID: deviceID, buckets: buckets, facts: facts)
    try await post(path: "v1/context-buckets/sync", body: body, accountGeneration: accountGeneration)
  }

  func purge(bucketIDs: [String]) async throws {
    guard !bucketIDs.isEmpty else { return }
    let body = ContextBucketSyncPayload.purgeBody(bucketIDs: bucketIDs)
    try await post(path: "v1/context-buckets/purge", body: body, accountGeneration: nil)
  }

  private func post(path: String, body: [String: Any], accountGeneration: Int?) async throws {
    let root = baseURL().hasSuffix("/") ? baseURL() : baseURL() + "/"
    guard let url = URL(string: root + path) else { throw ContextBucketSyncError.invalidResponse }

    let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    guard let authorizationSnapshot else { throw ContextBucketSyncError.ownerChanged }

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue(try await authorization(), forHTTPHeaderField: "Authorization")
    if let accountGeneration {
      request.setValue(String(accountGeneration), forHTTPHeaderField: "X-Account-Generation")
    }
    request.timeoutInterval = 30
    request.httpBody = try JSONSerialization.data(withJSONObject: body)

    let (_, response) = try await session.data(for: request)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw ContextBucketSyncError.ownerChanged
    }
    guard let http = response as? HTTPURLResponse else { throw ContextBucketSyncError.invalidResponse }
    guard (200..<300).contains(http.statusCode) else {
      throw ContextBucketSyncError.http(
        status: http.statusCode,
        retryAfterSeconds: ContextBucketSyncPayload.parseRetryAfterSeconds(from: http))
    }
  }
}

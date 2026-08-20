import Foundation

/// Publishes validated context bucket facts to the backend.
///
/// Capture stays on this device. What crosses the boundary is a projection:
/// bucket identity and model-authored fact statements. No field carries text
/// copied from the screen: window titles, URLs, file paths, quoted evidence, and
/// extracted identifiers all stay on the device. See
/// `docs/agents/context-buckets.md` for the full boundary.
enum ContextBucketSyncError: LocalizedError, Equatable {
  case invalidResponse
  case http(status: Int)
  case ownerChanged

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "context bucket sync received an invalid response"
    case .http(let status):
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
  let workstreamID: String?
  let notifyWorthiness: Double
  let visitCount: Int
  let lastVisitedAt: Date?
  let updatedAt: Date
}

enum ContextBucketSyncPayload {
  /// Backend caps a sync request at this many buckets.
  static let bucketLimit = 50

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
        "notify_worthiness": bucket.notifyWorthiness,
        "visit_count": bucket.visitCount,
        "device_updated_at": formatter.string(from: bucket.updatedAt),
        "facts": (factsByBucket[bucket.bucketID] ?? []).map {
          factPayload($0, formatter: formatter, deviceID: deviceID)
        },
      ]
      if let workstreamID = bucket.workstreamID { payload["workstream_id"] = workstreamID }
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
      "confidence": fact.confidence,
      "notify_worthiness": fact.notifyWorthiness,
      "disposition_state": fact.dispositionState,
      "device_updated_at": formatter.string(from: fact.updatedAt),
    ]
    if let workstreamTag = fact.workstreamTag { payload["workstream_tag"] = workstreamTag }
    if let expiresAt = fact.expiresAt { payload["expires_at"] = formatter.string(from: expiresAt) }
    return payload
  }

  /// Backend caps one purge request at this many bucket ids.
  static let purgeBatchSize = 200

  static func purgeBody(bucketIDs: [String]) -> [String: Any] {
    ["bucket_ids": bucketIDs]
  }

  /// Split a retraction across requests rather than truncating it.
  ///
  /// Dropping the overflow would report success while leaving excluded-app
  /// buckets on the server, which is the one outcome purge exists to prevent.
  static func purgeBatches(bucketIDs: [String]) -> [[String]] {
    stride(from: 0, to: bucketIDs.count, by: purgeBatchSize).map {
      Array(bucketIDs[$0..<min($0 + purgeBatchSize, bucketIDs.count)])
    }
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
    facts: [ContextBucketSyncFact],
    authorizedBy authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws {
    guard !buckets.isEmpty else { return }
    let body = ContextBucketSyncPayload.body(deviceID: deviceID, buckets: buckets, facts: facts)
    try await post(
      path: "v1/context-buckets/sync",
      body: body,
      accountGeneration: accountGeneration,
      authorizationSnapshot: authorizationSnapshot)
  }

  func purge(
    bucketIDs: [String],
    authorizedBy authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws {
    guard !bucketIDs.isEmpty else { return }
    for batch in ContextBucketSyncPayload.purgeBatches(bucketIDs: bucketIDs) {
      let body = ContextBucketSyncPayload.purgeBody(bucketIDs: batch)
      try await post(
        path: "v1/context-buckets/purge",
        body: body,
        accountGeneration: nil,
        authorizationSnapshot: authorizationSnapshot)
    }
  }

  /// The caller passes the snapshot it captured before reading local rows.
  ///
  /// Capturing a fresh snapshot here would validate against whoever owns the
  /// process now, not the owner whose database the payload was read from, so an
  /// owner change mid-pass could upload one account's rows under another's
  /// token. The parameter is deliberately required: a default would let a new
  /// call site silently opt back into that.
  private func post(
    path: String,
    body: [String: Any],
    accountGeneration: Int?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws {
    let root = baseURL().hasSuffix("/") ? baseURL() : baseURL() + "/"
    guard let url = URL(string: root + path) else { throw ContextBucketSyncError.invalidResponse }

    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw ContextBucketSyncError.ownerChanged
    }

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
      throw ContextBucketSyncError.http(status: http.statusCode)
    }
  }
}

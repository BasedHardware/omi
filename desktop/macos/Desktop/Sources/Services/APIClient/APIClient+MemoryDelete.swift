import Foundation

// MARK: - Memory Delete

extension APIClient {

  /// Deletes a memory by ID.
  ///
  /// A 404 completes normally. The caller asked for this memory to be gone, and the
  /// backend reporting it absent already satisfies that — delete is idempotent in
  /// intent, so "it is not here" is the requested end state, not a failure.
  ///
  /// This is load-bearing rather than defensive. The desktop cache routinely outlives
  /// the backend row: orphaned rows whose memory was deleted on another device answer
  /// 404 on delete, and treating that as an error made the caller restore the row it
  /// had just removed — so the memory could never be cleared from this device at all.
  ///
  /// A 409 is different: it is the backend's account-wide destructive-operation gate
  /// (`account_gate_busy`, mapped by `account_gate_busy_http_exception`) asking for a
  /// short backoff while it finishes a retention cleanup. The response carries a
  /// `Retry-After` header; the generic `delete` helper discards response headers, so
  /// this method owns its request path and preserves the header in the thrown error
  /// for the caller's deferred retry.
  func deleteMemory(id: String) async throws {
    guard let url = URL(string: baseURL + "v3/memories/\(id)") else {
      throw APIError.invalidResponse
    }
    let authPolicy = try resolvedRequestAuthPolicy(expectedOwnerId: nil, authorizationSnapshot: nil)
    try validateExpectedOwner(authPolicy)
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true,
      includeBYOK: true,
      expectedAuthOwnerId: authPolicy.expectedAuthOwnerId)
    try validateExpectedOwner(authPolicy)

    let (data, httpResponse) = try await performAuthenticatedData(for: request, authPolicy: authPolicy)

    switch httpResponse.statusCode {
    case 200...299, 404:
      return
    case 409:
      throw APIError.memoryDeleteGateBusy(
        retryAfterSeconds: Self.memoryDeleteRetryAfterSeconds(from: httpResponse))
    default:
      throw APIError.httpError(
        statusCode: httpResponse.statusCode,
        detail: OmiHTTPTransport.extractErrorDetail(from: data))
    }
  }

  private static func memoryDeleteRetryAfterSeconds(from response: HTTPURLResponse) -> Int? {
    guard let raw = response.value(forHTTPHeaderField: "Retry-After") else { return nil }
    return Int(raw.trimmingCharacters(in: .whitespacesAndNewlines))
  }
}

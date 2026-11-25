import Foundation

// Owns the conversation DELETE request: bounded retry on 409/503 busy replies and
// the Retry-After parsing behind it. Kept out of APIClient.swift (1500-line ratchet).
extension APIClient {
  /// Deletes a conversation by ID
  @discardableResult
  func deleteConversation(
    id: String,
    now: @Sendable () -> Date = { Date() },
    wait: @Sendable (TimeInterval) async throws -> Void = { seconds in
      try await Task.sleep(for: .seconds(seconds))
    }
  ) async throws -> ConversationDeleteOutcome {
    let authPolicy = try resolvedRequestAuthPolicy(expectedOwnerId: nil, authorizationSnapshot: nil)
    try validateExpectedOwner(authPolicy)
    guard let url = URL(string: baseURL + "v1/conversations/\(id)?cascade=true") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "DELETE"
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true, includeBYOK: true, expectedAuthOwnerId: authPolicy.expectedAuthOwnerId)
    let deadline = now().addingTimeInterval(30)
    while true {
      try Task.checkCancellation()
      try validateExpectedOwner(authPolicy)
      request.timeoutInterval = max(1, deadline.timeIntervalSince(now()))
      let (data, response) = try await performAuthenticatedData(for: request, authPolicy: authPolicy)
      switch response.statusCode {
      case 200...299, 404:
        invalidateConversationsCountCache()
        return response.statusCode == 404
          || response.value(forHTTPHeaderField: "X-Omi-Delete-Outcome") == "already_deleted"
          ? .alreadyDeleted : .deleted
      case 409, 503:
        let delay = Self.conversationDeleteRetryDelay(response, now: now())
        guard now().addingTimeInterval(delay) < deadline else { return .busy(retryAfter: delay) }
        try await wait(delay)
      default:
        throw APIError.httpError(
          statusCode: response.statusCode, detail: OmiHTTPTransport.extractErrorDetail(from: data))
      }
    }
  }

  static func conversationDeleteRetryDelay(_ response: HTTPURLResponse, now: Date) -> TimeInterval {
    let raw = response.value(forHTTPHeaderField: "Retry-After") ?? ""
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"  // omi-ux-allow: date-format-string -- HTTP Retry-After protocol date, never displayed to the user
    let delay =
      TimeInterval(raw.trimmingCharacters(in: .whitespacesAndNewlines))
      ?? formatter.date(from: raw)?.timeIntervalSince(now) ?? 2
    return delay.isFinite ? min(10, max(1, delay)) : 2
  }
}

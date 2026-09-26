import Foundation

extension APIClient {
  /// Owner-bound transport for the realtime hub's kernel-authorized
  /// `think_deeper` escalation to the managed Luna thinking lane. The body can
  /// contain the pinned turn's private transcript, context, and screenshot
  /// pixels, so the initial credential, 401 refresh, and late response all
  /// remain bound to the same immutable owner.
  ///
  /// Heavy thinking legitimately spends longer than a normal completion, so the
  /// request timeout is bounded per level instead of leaving the escalation
  /// hanging on the shared 60-second window.
  func thinkDeeperForVoice(
    body: [String: Any],
    thinkingLevel: RealtimeHubTools.EscalationThinkingLevel,
    expectedOwnerID: String,
    customBaseURL: String? = nil
  ) async throws -> String {
    let base = customBaseURL ?? rustBackendURL
    guard !base.isEmpty else { throw APIError.invalidResponse }
    let normalized = base.hasSuffix("/") ? base : base + "/"
    guard let url = URL(string: normalized + "v2/chat/completions") else {
      throw APIError.invalidResponse
    }
    guard JSONSerialization.isValidJSONObject(body) else {
      throw APIError.invalidResponse
    }

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = thinkingLevel == .heavy ? 150 : 60
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true,
      expectedAuthOwnerId: expectedOwnerID)
    request.httpBody = try JSONSerialization.data(withJSONObject: body)

    let (data, response) = try await performAuthenticatedData(
      for: request,
      authPolicy: .ownerBound(expectedOwnerID))
    guard (200..<300).contains(response.statusCode) else {
      throw APIError.httpError(
        statusCode: response.statusCode,
        detail: OmiHTTPTransport.extractErrorDetail(from: data))
    }
    guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let choices = json["choices"] as? [[String: Any]],
      let message = choices.first?["message"] as? [String: Any],
      let text = message["content"] as? String
    else {
      throw APIError.invalidResponse
    }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { throw APIError.invalidResponse }
    return trimmed
  }
}

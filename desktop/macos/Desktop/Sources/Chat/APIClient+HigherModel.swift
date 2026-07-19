import Foundation

extension APIClient {
  /// Owner-bound transport for the realtime hub's kernel-authorized
  /// higher-model escalation. The body can contain the pinned turn's private
  /// transcript and context, so the initial credential, 401 refresh, and late
  /// response all remain bound to the same immutable owner.
  func askHigherModel(
    body: [String: Any],
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
    request.timeoutInterval = 30
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
    return text.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

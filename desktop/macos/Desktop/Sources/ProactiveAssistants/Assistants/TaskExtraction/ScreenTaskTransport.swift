import Foundation

struct ScreenTaskAdmission: Sendable {
  let shouldExtract: Bool
  let gateOutcome: String
  let auditSample: Bool
}

extension APIClient {
  func screenTaskGate(
    ocrText: String, app: String, profile: String, tasks: [String],
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ScreenTaskAdmission {
    let body = OmiAPI.ScreenTaskGateRequest(appName: app, ocrText: ocrText, relatedTasks: tasks, userContext: profile)
    let response: OmiAPI.ScreenTaskGateResponse = try await post(
      "/v1/screen-task/gate", body: body,
      customBaseURL: rustBackendURL, includeBYOK: false, authorizationSnapshot: authorization, requestTimeout: 4)
    return ScreenTaskAdmission(
      shouldExtract: response.shouldExtract, gateOutcome: response.gateOutcome, auditSample: response.auditSample)
  }

  func extractScreenTask(
    body: Data, authorization: RuntimeOwnerAuthorizationSnapshot,
    gateOutcome: String, auditSample: Bool
  ) async throws -> String {
    try await GeminiClient.enforceManagedProactivity()
    let policy = RequestAuthPolicy.ownerBound(authorization)
    try validateExpectedOwner(policy)
    let base = rustBackendURL.hasSuffix("/") ? rustBackendURL : rustBackendURL + "/"
    guard let url = URL(string: base + "v1/proxy/gemini/models/\(ScreenTaskPrompt.model):generateContent") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.httpBody = body
    request.timeoutInterval = 120
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true, includeBYOK: false, expectedAuthOwnerId: authorization.ownerID)
    request.setValue("extraction", forHTTPHeaderField: "X-Omi-Workload")
    request.setValue(gateOutcome, forHTTPHeaderField: "X-Omi-Screen-Task-Gate")
    request.setValue(auditSample ? "true" : "false", forHTTPHeaderField: "X-Omi-Screen-Task-Audit")
    try validateExpectedOwner(policy)
    let response: ScreenTaskGeminiResponse = try await performRequest(request, authPolicy: policy)
    return try response.text()
  }
}

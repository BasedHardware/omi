import Foundation

struct ScreenTaskAdmission: Sendable {
  let shouldExtract: Bool
  let gateOutcome: String
  let auditSample: Bool
  var clientBypass = false
}

struct ScreenTaskServerAdmission: Decodable {
  let enabled: Bool
  let lease_seconds: Int
}

extension APIClient {
  func screenTaskAdmissionStatus(authorization: RuntimeOwnerAuthorizationSnapshot) async throws -> Bool {
    let response: ScreenTaskServerAdmission = try await get(
      "/v1/screen-task/admission", customBaseURL: rustBackendURL,
      authorizationSnapshot: authorization)
    return response.enabled && (1...55).contains(response.lease_seconds)
  }

  func screenTaskGate(
    ocrText: String, app: String, profile: String, tasks: [String],
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ScreenTaskAdmission {
    let body = OmiAPI.ScreenTaskGateRequest(appName: app, ocrText: ocrText, relatedTasks: tasks, userContext: profile)
    let data = try JSONEncoder().encode(body)
    let response: OmiAPI.ScreenTaskGateResponse = try await screenTaskRequest(
      path: "v1/screen-task/gate", body: data, authorization: authorization, timeout: 4)
    guard ["passed", "rejected", "fail_open"].contains(response.gateOutcome),
      response.shouldExtract == (response.gateOutcome != "rejected" || response.auditSample),
      !response.auditSample || response.gateOutcome == "rejected"
    else { throw APIError.invalidResponse }
    return ScreenTaskAdmission(
      shouldExtract: response.shouldExtract, gateOutcome: response.gateOutcome, auditSample: response.auditSample)
  }

  func extractScreenTask(
    body: Data, authorization: RuntimeOwnerAuthorizationSnapshot,
    gateOutcome: String, auditSample: Bool, clientBypass: Bool = false
  ) async throws -> String {
    try await ScreenTaskFeature.enforceQuota()
    let response: ScreenTaskGeminiResponse = try await screenTaskRequest(
      path: "v1/proxy/gemini/models/\(ScreenTaskPrompt.model):generateContent", body: body,
      authorization: authorization, timeout: 120, lane: .taskExtraction, workload: .extraction,
      headers: [
        "X-Omi-Screen-Task-Gate": gateOutcome, "X-Omi-Screen-Task-Audit": auditSample ? "true" : "false",
        "X-Omi-Screen-Task-Client-Bypass": clientBypass ? "true" : "false",
      ])
    return try response.text()
  }

  private func screenTaskRequest<T: Decodable>(
    path: String, body: Data, authorization: RuntimeOwnerAuthorizationSnapshot,
    timeout: TimeInterval, lane: GeminiLane? = nil, workload: GeminiWorkloadClass? = nil,
    headers: [String: String] = [:]
  ) async throws -> T {
    var policy = RequestAuthPolicy.ownerBound(authorization)
    policy.allowsAuthRetry = false  // A logical frame never replays auth/quota failures.
    try validateExpectedOwner(policy)
    let base = rustBackendURL.hasSuffix("/") ? rustBackendURL : rustBackendURL + "/"
    guard let url = URL(string: base + path) else { throw APIError.invalidResponse }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.httpBody = body
    request.timeoutInterval = timeout
    request.allHTTPHeaderFields = try await buildHeaders(
      requireAuth: true, includeBYOK: false, expectedAuthOwnerId: authorization.ownerID)
    if let lane, let workload {
      guard let authorizationHeader = request.value(forHTTPHeaderField: "Authorization") else {
        throw APIError.invalidResponse
      }
      request.applyGeminiProxyHeaders(lane: lane, workload: workload, authorization: authorizationHeader)
    }
    for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
    try validateExpectedOwner(policy)
    let (data, urlResponse) = try await session.data(for: request)
    // A terminal denial wins over a concurrent feature stop. It must not become
    // rollback through the response-side feature validator. Original ownership
    // still gates every response; successful data also needs the full work lease.
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { throw ScreenTaskFailure.ownerRevoked }
    try Task.checkCancellation()
    guard let response = urlResponse as? HTTPURLResponse else { throw APIError.invalidResponse }
    guard (200...299).contains(response.statusCode) else {
      let failure = ScreenTaskHTTPFailure(response: response, data: data)
      if failure.stopped { ScreenTaskFeature.serverAuthority.disable() }
      ScreenTaskBackpressure.shared.record(failure, owner: authorization)
      throw failure
    }
    try validateExpectedOwner(policy)
    return try JSONDecoder().decode(T.self, from: data)
  }
}

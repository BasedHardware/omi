import Foundation

enum ClientTelemetryHTTP {
  static func endpoint(baseURL: String) -> URL? {
    var trimmed = baseURL
    while trimmed.hasSuffix("/") { trimmed.removeLast() }
    guard !trimmed.isEmpty else { return nil }
    return URL(string: trimmed + "/v1/telemetry/client/batches")
  }

  static func retryAfter(from response: HTTPURLResponse) -> TimeInterval? {
    guard let header = response.value(forHTTPHeaderField: "Retry-After") else { return nil }
    if let seconds = TimeInterval(header), seconds.isFinite { return max(0, seconds) }
    return nil
  }

  static func liveSend(_ request: ClientTelemetryRequest) async -> ClientTelemetryHTTPResult {
    let baseURL = await APIClient.shared.baseURL
    guard let url = endpoint(baseURL: baseURL) else { return .network }
    var urlRequest = URLRequest(url: url, timeoutInterval: request.timeout)
    urlRequest.httpMethod = "POST"
    urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
    urlRequest.setValue("Bearer \(request.token)", forHTTPHeaderField: "Authorization")
    urlRequest.httpBody = request.body
    do {
      let (data, response) = try await URLSession.shared.data(for: urlRequest)
      guard let http = response as? HTTPURLResponse else { return .network }
      return .response(status: http.statusCode, retryAfter: retryAfter(from: http), body: data)
    } catch let error as URLError where error.code == .timedOut {
      return .timeout
    } catch {
      return .network
    }
  }
}

struct ClientTelemetryDependencies: Sendable {
  var now: @Sendable () -> Date
  var sleep: @Sendable (TimeInterval) async -> Void
  var jitterUnit: @Sendable () -> Double
  var currentOwnerID: @Sendable () -> String?
  var token: @Sendable (_ ownerID: String, _ forceRefresh: Bool) async -> String?
  var endpointBaseURL: @Sendable () async -> String
  var send: @Sendable (ClientTelemetryRequest) async -> ClientTelemetryHTTPResult
  var automaticFlush: Bool

  static let production = ClientTelemetryDependencies(
    now: { Date() },
    sleep: { seconds in
      let nanoseconds = UInt64(max(0, seconds) * 1_000_000_000)
      try? await Task.sleep(nanoseconds: nanoseconds)
    },
    jitterUnit: { Double.random(in: 0...1) },
    currentOwnerID: { RuntimeOwnerIdentity.currentOwnerId() },
    token: { ownerID, forceRefresh in
      guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return nil }
      return try? await AuthService.shared.getIdToken(forceRefresh: forceRefresh)
    },
    endpointBaseURL: { await APIClient.shared.baseURL },
    send: { request in await ClientTelemetryHTTP.liveSend(request) },
    automaticFlush: true
  )
}

import Foundation

struct ScreenTaskHTTPFailure: Error {
  let status: Int
  let retryable: Bool?
  let retryAfter: TimeInterval?
  let stopped: Bool

  init(response: HTTPURLResponse, data: Data) {
    status = response.statusCode
    let header = response.value(forHTTPHeaderField: "X-Omi-Retryable")?.lowercased()
    retryable = header == "true" ? true : (header == "false" ? false : nil)
    retryAfter = response.value(forHTTPHeaderField: "Retry-After").flatMap { value in
      if let seconds = Double(value), seconds.isFinite { return max(0, seconds) }
      let formatter = DateFormatter()
      formatter.locale = Locale(identifier: "en_US_POSIX")
      formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
      return formatter.date(from: value).map { max(0, $0.timeIntervalSinceNow) }
    }
    let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    let detail = object?["detail"] as? [String: Any]
    stopped = status == 409 && detail?["error"] as? String == "screen_task_stopped"
  }
}

enum ScreenTaskErrorPolicy {
  static func outageReason(_ error: Error) -> String? {
    if let failure = error as? ScreenTaskHTTPFailure {
      // An explicit replay denial overrides even a 5xx. Auth/quota/backpressure never recover via another model.
      guard failure.retryable != false, !failure.stopped, (500...599).contains(failure.status) else { return nil }
      return "provider_5xx"
    }
    if let error = error as? URLError {
      switch error.code {
      case .timedOut: return "timeout"
      case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed:
        return "offline"
      default: return nil
      }
    }
    return nil
  }

  static func errorClass(_ error: Error) -> String {
    if error is CancellationError { return "cancelled" }
    if let failure = error as? ScreenTaskHTTPFailure {
      if failure.stopped { return "stopped" }
      switch failure.status {
      case 401: return "auth"
      case 402: return "plan_or_quota"
      case 429: return "backpressure"
      case 500...599: return failure.retryable == false ? "admission_denied" : "provider_5xx"
      default: return "http_terminal"
      }
    }
    if let failure = error as? ScreenTaskFailure {
      switch failure {
      case .stopped: return "stopped"
      case .backpressure: return "backpressure"
      case .planGated: return "plan_or_quota"
      case .ownerRevoked: return "owner_revoked"
      case .privacyRevoked: return "privacy_revoked"
      case .invalidResponse: return "invalid_response"
      }
    }
    if case APIError.unauthorized = error { return "auth" }
    if let error = error as? GeminiClient.GeminiClientError {
      switch error {
      case .planGated: return "plan_or_quota"
      case .apiError(let message, let retryable):
        if message.hasPrefix("HTTP 401:") { return "auth" }
        if message.hasPrefix("HTTP 402:") { return "plan_or_quota" }
        if message.hasPrefix("HTTP 429:") { return "backpressure" }
        return retryable == false ? "http_terminal" : "provider_error"
      case .networkError: return "offline"
      case .invalidResponse: return "invalid_response"
      case .missingAPIKey: return "auth"
      }
    }
    if error is DecodingError { return "invalid_response" }
    return outageReason(error) ?? "local_failure"
  }
}

final class ScreenTaskBackpressure: @unchecked Sendable {
  static let shared = ScreenTaskBackpressure()
  private let lock = NSLock()
  private let now: @Sendable () -> TimeInterval
  init(now: @escaping @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) { self.now = now }
  private var until: [String: TimeInterval] = [:]
  func record(_ error: Error, owner: RuntimeOwnerAuthorizationSnapshot) {
    guard let failure = error as? ScreenTaskHTTPFailure, let wait = failure.retryAfter else { return }
    let key = "\(owner.ownerID):\(owner.authorizationGeneration):\(owner.authorizationNonce)"
    lock.withLock {
      let current = now()
      until = until.filter { $0.value > current }
      until[key] = max(until[key] ?? 0, current + wait)
    }
  }
  func isBlocked(_ owner: RuntimeOwnerAuthorizationSnapshot) -> Bool {
    let key = "\(owner.ownerID):\(owner.authorizationGeneration):\(owner.authorizationNonce)"
    return lock.withLock { (until[key] ?? 0) > now() }
  }
}

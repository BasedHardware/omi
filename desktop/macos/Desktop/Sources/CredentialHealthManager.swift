import Foundation

enum CredentialAuthMode: String, Equatable {
  case managed
  case byok
}

enum CredentialFailureClass: Equatable {
  case backendUnauthorized
  case requiresLogin
  case paywalled
  case byokEnrollmentMismatch(provider: BYOKProvider?)
  case providerAuthFailed(provider: RealtimeHubProvider, mode: CredentialAuthMode)
  case providerQuotaExceeded(provider: RealtimeHubProvider)
  case backendTransient(statusCode: Int?)
  case providerTransient(provider: RealtimeHubProvider)
  case providerPolicyClose(provider: RealtimeHubProvider)
  case unknown

  var isAccountWide: Bool {
    switch self {
    case .backendUnauthorized, .requiresLogin, .paywalled, .byokEnrollmentMismatch:
      return true
    default:
      return false
    }
  }

  var logValue: String {
    switch self {
    case .backendUnauthorized: return "backend_unauthorized"
    case .requiresLogin: return "requires_login"
    case .paywalled: return "paywalled"
    case .byokEnrollmentMismatch: return "byok_enrollment_mismatch"
    case .providerAuthFailed: return "provider_auth_failed"
    case .providerQuotaExceeded: return "provider_quota_exceeded"
    case .backendTransient: return "backend_transient"
    case .providerTransient: return "provider_transient"
    case .providerPolicyClose: return "provider_policy_close"
    case .unknown: return "unknown"
    }
  }

  var httpStatusCode: Int? {
    switch self {
    case .backendTransient(let statusCode):
      return statusCode
    default:
      return nil
    }
  }
}

struct CredentialRecoveryIssue: Equatable {
  let failureClass: CredentialFailureClass
  let message: String
  let provider: RealtimeHubProvider?
  let authMode: CredentialAuthMode?
}

enum CredentialHealthError: LocalizedError, Equatable {
  case requiresLogin(message: String)
  case paywalled(message: String)
  case byokMismatch(provider: BYOKProvider?, message: String)
  case providerAuth(provider: RealtimeHubProvider, mode: CredentialAuthMode, message: String)
  case providerQuota(provider: RealtimeHubProvider, message: String)
  case backendTransient(statusCode: Int?, message: String)
  case providerTransient(provider: RealtimeHubProvider, message: String)
  case unknown(message: String)

  var failureClass: CredentialFailureClass {
    switch self {
    case .requiresLogin:
      return .requiresLogin
    case .paywalled:
      return .paywalled
    case .byokMismatch(let provider, _):
      return .byokEnrollmentMismatch(provider: provider)
    case .providerAuth(let provider, let mode, _):
      return .providerAuthFailed(provider: provider, mode: mode)
    case .providerQuota(let provider, _):
      return .providerQuotaExceeded(provider: provider)
    case .backendTransient(let statusCode, _):
      return .backendTransient(statusCode: statusCode)
    case .providerTransient(let provider, _):
      return .providerTransient(provider: provider)
    case .unknown:
      return .unknown
    }
  }

  var provider: RealtimeHubProvider? {
    switch self {
    case .providerAuth(let provider, _, _), .providerQuota(let provider, _), .providerTransient(let provider, _):
      return provider
    default:
      return nil
    }
  }

  var authMode: CredentialAuthMode? {
    switch self {
    case .providerAuth(_, let mode, _):
      return mode
    default:
      return nil
    }
  }

  var errorDescription: String? {
    switch self {
    case .requiresLogin(let message),
      .paywalled(let message),
      .byokMismatch(_, let message),
      .providerAuth(_, _, let message),
      .providerQuota(_, let message),
      .backendTransient(_, let message),
      .providerTransient(_, let message),
      .unknown(let message):
      return message
    }
  }
}

@MainActor
final class CredentialHealthManager: ObservableObject {
  static let shared = CredentialHealthManager()

  @Published private(set) var visibleRecovery: CredentialRecoveryIssue?

  private var invalidBYOKFingerprints: [BYOKProvider: String] = [:]

  private init() {}

  func reset() {
    visibleRecovery = nil
    invalidBYOKFingerprints.removeAll()
  }

  func canUseBYOK(provider: BYOKProvider, fingerprint: String?) -> Bool {
    guard let fingerprint, let invalid = invalidBYOKFingerprints[provider] else { return true }
    return invalid != fingerprint
  }

  func record(_ error: CredentialHealthError, context: String) {
    record(
      failureClass: error.failureClass,
      provider: error.provider,
      authMode: error.authMode,
      message: error.localizedDescription,
      context: context)
  }

  func recordProviderFailure(
    _ failureClass: CredentialFailureClass,
    provider: RealtimeHubProvider,
    authMode: CredentialAuthMode,
    fingerprint: String?,
    context: String
  ) {
    if case .providerAuthFailed(_, .byok) = failureClass, let fingerprint {
      invalidBYOKFingerprints[provider.byokProvider] = fingerprint
    }
    record(
      failureClass: failureClass,
      provider: provider,
      authMode: authMode,
      message: recoveryMessage(for: failureClass, provider: provider),
      context: context)
  }

  private func record(
    failureClass: CredentialFailureClass,
    provider: RealtimeHubProvider?,
    authMode: CredentialAuthMode?,
    message: String,
    context: String
  ) {
    visibleRecovery = CredentialRecoveryIssue(
      failureClass: failureClass,
      message: message,
      provider: provider,
      authMode: authMode)
    log(
      "CredentialHealth: context=\(context) failure_class=\(failureClass.logValue)"
        + " provider=\(provider?.rawValue ?? "none") auth_mode=\(authMode?.rawValue ?? "none")")
  }

  private func recoveryMessage(for failureClass: CredentialFailureClass, provider: RealtimeHubProvider) -> String {
    switch failureClass {
    case .providerAuthFailed(_, .byok):
      return "Your \(provider.displayName) key was rejected. Update it in Settings."
    case .providerAuthFailed:
      return "\(provider.displayName) authentication failed. Voice responses are using fallback."
    case .providerQuotaExceeded:
      return "Your \(provider.displayName) quota is exhausted. Add quota or switch providers."
    case .providerPolicyClose:
      return "\(provider.displayName) rejected the realtime session. Voice responses are using fallback."
    case .providerTransient:
      return "\(provider.displayName) is temporarily unavailable. Voice responses are using fallback."
    default:
      return "Voice credential recovery is required."
    }
  }

  nonisolated static func realtimeProvider(from raw: String) -> RealtimeHubProvider? {
    switch raw.lowercased() {
    case "openai": return .openai
    case "gemini": return .gemini
    default: return nil
    }
  }

  nonisolated static func classifyHTTPFailure(
    statusCode: Int,
    payload: APIErrorPayload?,
    provider: RealtimeHubProvider?
  ) -> CredentialHealthError {
    let message = payload?.preferredMessage ?? HTTPURLResponse.localizedString(forStatusCode: statusCode)
    switch statusCode {
    case 401:
      return .requiresLogin(message: "Please sign in again to use voice responses.")
    case 402:
      return .paywalled(message: message.isEmpty ? "Upgrade or add BYOK keys to use voice responses." : message)
    case 403:
      return .byokMismatch(provider: nil, message: message.isEmpty ? "Revalidate your BYOK keys in Settings." : message)
    case 429:
      if let provider {
        return .providerQuota(provider: provider, message: message)
      }
      return .backendTransient(statusCode: statusCode, message: message)
    case 500...599:
      return .backendTransient(statusCode: statusCode, message: message)
    default:
      if let provider, containsProviderAuthSignal(message) {
        return .providerAuth(provider: provider, mode: .managed, message: message)
      }
      return .unknown(message: message)
    }
  }

  nonisolated static func classifyProviderClose(
    message: String,
    provider: RealtimeHubProvider
  ) -> CredentialFailureClass {
    let lower = message.lowercased()
    if lower.contains("insufficient_quota") || lower.contains("quota") || lower.contains("resource exhausted")
      || lower.contains("429")
    {
      return .providerQuotaExceeded(provider: provider)
    }
    if containsProviderAuthSignal(lower) {
      return .providerAuthFailed(provider: provider, mode: .byok)
    }
    if lower.contains("websocket closed (1008)") || lower.contains("policy") {
      return .providerPolicyClose(provider: provider)
    }
    return .providerTransient(provider: provider)
  }

  nonisolated private static func containsProviderAuthSignal(_ text: String) -> Bool {
    let lower = text.lowercased()
    return lower.contains("invalid api key")
      || lower.contains("api key not valid")
      || lower.contains("invalid authentication credentials")
      || lower.contains("unauthorized")
      || lower.contains("authentication failed")
      || lower.contains("permission denied")
  }
}

struct APIErrorPayload: Decodable, Equatable {
  let error: String?
  let code: String?
  let message: String?
  let detail: String?
  let provider: String?
  let reason: String?
  let backendRoute: String?
  let upstreamStatusCode: Int?
  let retryable: Bool?
  let retryAfterSeconds: Int?

  enum CodingKeys: String, CodingKey {
    case error
    case code
    case message
    case detail
    case provider
    case reason
    case backendRoute = "backend_route"
    case upstreamStatusCode = "upstream_status_code"
    case retryable
    case retryAfterSeconds = "retry_after_seconds"
  }

  var preferredMessage: String? {
    detail ?? message ?? error ?? code
  }
}

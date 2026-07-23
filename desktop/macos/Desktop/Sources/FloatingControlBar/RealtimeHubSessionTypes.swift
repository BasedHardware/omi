import Foundation
import Network
import VoiceTurnDomain

struct SessionCallbackBox<T>: @unchecked Sendable {
  let value: T
  init(_ value: T) { self.value = value }
}

enum RealtimePostToolContinuationStartResult: Equatable {
  case started
  case alreadyInFlight
  case stale
  case exhausted
  case transportUnavailable
}

@MainActor
protocol RealtimeHubSessionDelegate: AnyObject {
  func hubDidConnect(source: RealtimeHubSession)
  func hubDidReceiveInputTranscript(
    _ text: String, isFinal: Bool, identity: RealtimeHubEventIdentity?, source: RealtimeHubSession)
  func hubDidReceiveAudio(
    _ pcm24k: Data, identity: RealtimeHubEventIdentity?, source: RealtimeHubSession)
  func hubDidEmitText(
    _ text: String, isFinal: Bool, identity: RealtimeHubEventIdentity?, source: RealtimeHubSession)
  func hubDidRequestTool(
    name: String, callId: String, argumentsJSON: String,
    identity: RealtimeHubEventIdentity?, source: RealtimeHubSession)
  func hubDidFinishTurn(identity: RealtimeHubEventIdentity?, source: RealtimeHubSession)
  func hubDidError(_ failure: RealtimeHubTransportFailure, source: RealtimeHubSession)
  /// The session became able to accept injected (non-PTT) context — a warm
  /// Gemini activity window just opened. The capability signal that retries a
  /// background-agent completion left unadvanced while the session was idle.
  func hubDidOpenInputWindow(source: RealtimeHubSession)
}

extension RealtimeHubSessionDelegate {
  /// Default no-op: only the controller that owns background-completion delivery
  /// needs the "ready for injected context" signal.
  func hubDidOpenInputWindow(source: RealtimeHubSession) {}
}

enum RealtimeHubTransportFailureKind: String, Equatable, Sendable {
  case localAddressUnavailable = "local_address_unavailable"
  case providerClose = "provider_close"
  case providerError = "provider_error"
  case configuration
  case connect
  case handshake
  case receive
  case send
  case protocolViolation = "protocol_violation"
  case unknown
}

struct RealtimeHubTransportFailure: Equatable, Sendable {
  let kind: RealtimeHubTransportFailureKind
  let message: String
  let systemDomain: String?
  let systemCode: Int?

  static func rawWebSocket(_ failure: RealtimeRawWebSocketFailure) -> Self {
    if let underlyingError = failure.underlyingError,
      isLocalAddressUnavailable(underlyingError)
    {
      return Self(
        kind: .localAddressUnavailable,
        message: failure.message,
        systemDomain: "posix",
        systemCode: Int(POSIXErrorCode.EADDRNOTAVAIL.rawValue))
    }
    return Self(
      kind: kind(for: failure.phase),
      message: failure.message,
      systemDomain: boundedSystemDomain(failure.underlyingError),
      systemCode: failure.underlyingError.map { ($0 as NSError).code })
  }

  static func providerClose(code: Int, reason: String) -> Self {
    Self(
      kind: .providerClose,
      message: "WebSocket closed (\(code)) \(reason)",
      systemDomain: nil,
      systemCode: code)
  }

  static func providerError(_ message: String) -> Self {
    Self(kind: .providerError, message: message, systemDomain: nil, systemCode: nil)
  }

  static func system(_ error: Error, phase: RealtimeHubTransportFailureKind) -> Self {
    if isLocalAddressUnavailable(error) {
      return Self(
        kind: .localAddressUnavailable,
        message: error.localizedDescription,
        systemDomain: "posix",
        systemCode: Int(POSIXErrorCode.EADDRNOTAVAIL.rawValue))
    }
    return Self(
      kind: phase,
      message: error.localizedDescription,
      systemDomain: boundedSystemDomain(error),
      systemCode: (error as NSError).code)
  }

  private static func kind(
    for phase: RealtimeRawWebSocketFailurePhase
  ) -> RealtimeHubTransportFailureKind {
    switch phase {
    case .configuration: return .configuration
    case .connect: return .connect
    case .handshake: return .handshake
    case .receive: return .receive
    case .send: return .send
    case .protocolViolation: return .protocolViolation
    }
  }

  private static func isLocalAddressUnavailable(_ error: Error) -> Bool {
    if let networkError = error as? NWError,
      case .posix(let code) = networkError
    {
      return code == .EADDRNOTAVAIL
    }
    let nsError = error as NSError
    return nsError.domain == NSPOSIXErrorDomain
      && nsError.code == Int(POSIXErrorCode.EADDRNOTAVAIL.rawValue)
  }

  private static func boundedSystemDomain(_ error: Error?) -> String? {
    guard let error else { return nil }
    if error is NWError { return "network" }
    let domain = (error as NSError).domain
    if domain == NSPOSIXErrorDomain { return "posix" }
    if domain == NSURLErrorDomain { return "url" }
    return "other"
  }
}

struct RealtimeHubEventIdentity: Equatable, Sendable {
  let turnID: VoiceTurnID
  let responseID: VoiceResponseID
}

enum GeminiRealtimeEventOwnership {
  static func inputIdentity(
    active: RealtimeHubEventIdentity?,
    completed: RealtimeHubEventIdentity?
  ) -> RealtimeHubEventIdentity? {
    guard let completed else { return active }
    guard active == nil || active == completed else { return nil }
    return completed
  }
}

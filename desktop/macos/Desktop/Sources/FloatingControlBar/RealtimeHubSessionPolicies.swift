import Foundation

/// Safe, non-sensitive classification for realtime WebSocket teardown messages.
///
/// Gemini can idle-close warm sessions with WebSocket 1008 after the socket has
/// lived for a while, and OpenAI has a known maximum-session-duration close.
/// OpenAI's transport can also surface an already-retired socket as an ENOTCONN
/// ("Socket is not connected") write race, typically right after the 60-minute
/// rotation. All of these expected lifecycle paths should re-warm quietly rather
/// than page Sentry as production errors. Fast 1008 closes are different: they
/// usually mean provider policy/auth/config rejection and should still be
/// reported, but with a stable category instead of raw provider text.
enum RealtimeHubCloseCategory: String {
  case expectedIdleTeardown = "expected_idle_teardown"
  case expectedSessionRotation = "expected_session_rotation"
  case providerAuthFailed = "provider_auth_failed"
  case providerQuotaExceeded = "provider_quota_exceeded"
  case providerPolicyCloseFast = "provider_policy_close_fast"
  case providerTransient = "provider_transient"
}

/// The controller owns transport replacement, while the voice-turn reducer owns
/// any active logical turn. Keeping this plan typed prevents provider-close text
/// from leaking into lifecycle decisions outside the classifier boundary.
enum RealtimeHubSessionRotationPlan: Equatable {
  case rewarmIdleTransport
  case terminateActiveTurnAndRewarm
}

enum RealtimeHubCloseClassifier {
  static let idleTeardownThreshold: TimeInterval = 60

  static func category(
    message: String,
    aliveFor: TimeInterval,
    hasActiveTurn: Bool = false,
    provider: RealtimeHubProvider = .openai
  ) -> RealtimeHubCloseCategory? {
    let lower = message.lowercased()
    if provider == .openai,
      lower.contains("your session hit the maximum duration")
      && lower.contains("60 minutes")
    {
      return .expectedSessionRotation
    }
    // A retired socket surfaces later writes as ENOTCONN. On an aged socket with
    // no active turn (e.g. the window right after a 60-minute rotation) this is
    // an expected transport teardown, not a provider error: re-warm quietly. A
    // fast ENOTCONN, or one during an active turn, falls through and stays a
    // reportable error so genuine transport failures remain observable.
    if !hasActiveTurn,
      aliveFor >= idleTeardownThreshold,
      lower.contains("socket is not connected")
    {
      return .expectedIdleTeardown
    }
    guard lower.contains("websocket closed (1008)") else { return nil }
    if CredentialHealthManager.classifyProviderClose(
      message: message,
      provider: provider) == .providerQuotaExceeded(provider: provider)
    {
      return .providerQuotaExceeded
    }
    if CredentialHealthManager.classifyProviderClose(
      message: message,
      provider: provider) == .providerAuthFailed(provider: provider, mode: .byok)
    {
      return .providerAuthFailed
    }
    if !hasActiveTurn && aliveFor >= idleTeardownThreshold { return .expectedIdleTeardown }
    return .providerPolicyCloseFast
  }

  static func sessionRotationPlan(
    for category: RealtimeHubCloseCategory?,
    hasActiveTurn: Bool
  ) -> RealtimeHubSessionRotationPlan? {
    guard category == .expectedSessionRotation else { return nil }
    return hasActiveTurn ? .terminateActiveTurnAndRewarm : .rewarmIdleTransport
  }

  static func isExpectedLifecycleClose(_ category: RealtimeHubCloseCategory?) -> Bool {
    category == .expectedIdleTeardown || category == .expectedSessionRotation
  }

  static func shouldReportToSentry(_ category: RealtimeHubCloseCategory?) -> Bool {
    !isExpectedLifecycleClose(category)
  }
}

enum RealtimeHubCommitResult: Equatable {
  case accepted
  case deferredForReplacement
  case deferredForReconnect
  case alreadyOwned
  case rejectedNoSession
}

enum RealtimeHubCommitOwnershipPolicy {
  static func isAlreadyOwned(turn: VoiceTurn?, requestedTurnID: VoiceTurnID) -> Bool {
    guard let turn, turn.id == requestedTurnID, turn.phase == .awaitingResponse,
      turn.hubCommitPending
    else { return false }
    if case .hub = turn.route { return true }
    return false
  }
}

struct RealtimeProviderToolResult: Equatable {
  let output: String
  let originalByteCount: Int
  let wasOversized: Bool
}

enum RealtimeProviderToolResultPolicy {
  static let maximumByteCount = 48 * 1024

  /// The sole model-visible result boundary for both realtime providers.
  /// Provider-specific transport only happens after this method returns a
  /// canonical envelope, including rejected/authorization error paths.
  static func prepare(
    provider: RealtimeHubProvider = .openai,
    name: String,
    output: String
  ) -> RealtimeProviderToolResult {
    let originalByteCount = output.utf8.count
    var providerOutput = output
    if name == HubTool.spawnAgent.rawValue,
      let payload = try? JSONSerialization.jsonObject(with: Data(output.utf8)) as? [String: Any],
      let providerResult = payload["providerResult"] as? [String: Any],
      isCanonicalToolResultEnvelope(providerResult["toolResultEnvelope"]),
      let data = try? JSONSerialization.data(withJSONObject: providerResult, options: [.sortedKeys]),
      let compact = String(data: data, encoding: .utf8)
    {
      providerOutput = compact
    }
    guard providerOutput.utf8.count <= maximumByteCount else {
      return oversizedFailure(
        provider: provider,
        name: name,
        originalOutput: output,
        originalByteCount: originalByteCount)
    }
    let finalized = finalize(provider: provider, name: name, output: providerOutput)
    guard finalized.utf8.count <= maximumByteCount else {
      return oversizedFailure(
        provider: provider,
        name: name,
        originalOutput: output,
        originalByteCount: originalByteCount)
    }
    return RealtimeProviderToolResult(
      output: finalized,
      originalByteCount: originalByteCount,
      wasOversized: false)
  }

  static func rejectedOutput(
    code: String,
    message: String,
    preservingCanonicalEnvelopeFrom sourceOutput: String? = nil
  ) -> String {
    var payload: [String: Any] = [
      "ok": false,
      "error": ["code": String(code.prefix(128)), "message": String(message.prefix(512))],
    ]
    // Node owns the capability tuple. A Swift classification may refine the
    // user-facing error, but it must never replace a valid external-run
    // envelope with synthetic realtime provenance.
    if let sourceOutput,
      let sourcePayload = try? JSONSerialization.jsonObject(with: Data(sourceOutput.utf8)) as? [String: Any],
      isCanonicalToolResultEnvelope(sourcePayload["toolResultEnvelope"])
    {
      payload["toolResultEnvelope"] = sourcePayload["toolResultEnvelope"]
    }
    let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return data.flatMap { String(data: $0, encoding: .utf8) }
      ?? #"{"ok":false,"error":{"code":"realtime_tool_rejected","message":"The tool could not be completed."}}"#
  }

  private static func oversizedFailure(
    provider: RealtimeHubProvider,
    name: String,
    originalOutput: String,
    originalByteCount: Int
  ) -> RealtimeProviderToolResult {
    let error: [String: Any] = [
      "code": "tool_result_too_large",
      "message": "The tool returned too much detail. Retry with narrower filters.",
      "tool": String(name.prefix(128)),
      "originalBytes": originalByteCount,
    ]
    let payload: [String: Any] = [
      "ok": false,
      "error": error,
      "toolResultEnvelope": providerFailureEnvelope(
        provider: provider, name: name, error: error, originalOutput: originalOutput),
    ]
    let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    let bounded = data.flatMap { String(data: $0, encoding: .utf8) }
      ?? #"{"ok":false,"error":{"code":"tool_result_too_large"}}"#
    return RealtimeProviderToolResult(
      output: bounded,
      originalByteCount: originalByteCount,
      wasOversized: true)
  }

  private static func finalize(provider: RealtimeHubProvider, name: String, output: String) -> String {
    if parsedCanonicalToolResultEnvelope(from: output) != nil { return output }
    guard var payload = try? JSONSerialization.jsonObject(with: Data(output.utf8)) as? [String: Any]
    else {
      return rejectedOutputEnvelope(
        provider: provider,
        name: name,
        code: "realtime_tool_result_unstructured",
        message: "The tool returned an invalid response.")
    }
    let status = payload["ok"] as? Bool == true ? "succeeded" : "failed"
    let payloadBytes =
      (try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]))?.count ?? 0
    payload["toolResultEnvelope"] = [
      "version": 1,
      "status": status,
      "truncated": false,
      "originalBytes": payloadBytes,
      "projectedBytes": payloadBytes,
      "fullOutputRef": NSNull(),
      "provenance": [
        "invocationId": "realtime-\(provider.rawValue)-\(String(name.prefix(64)))",
        "runId": "unknown",
        "attemptId": "unknown",
        "toolName": String(name.prefix(128)),
      ],
    ]
    let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return data.flatMap { String(data: $0, encoding: .utf8) }
      ?? rejectedOutputEnvelope(
        provider: provider,
        name: name,
        code: "realtime_tool_result_encoding_failed",
        message: "The tool response could not be prepared.")
  }

  private static func rejectedOutputEnvelope(
    provider: RealtimeHubProvider,
    name: String,
    code: String,
    message: String
  ) -> String {
    let error: [String: Any] = [
      "code": String(code.prefix(128)), "message": String(message.prefix(512)),
    ]
    let payload: [String: Any] = [
      "ok": false,
      "error": error,
      "toolResultEnvelope": providerFailureEnvelope(
        provider: provider,
        name: name,
        error: error,
        originalOutput: ""),
    ]
    let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return data.flatMap { String(data: $0, encoding: .utf8) }
      ?? #"{"ok":false}"#
  }

  /// The Node bridge owns artifacts. Swift never replaces a canonical reference
  /// with a provider-only payload; it either forwards that envelope or returns
  /// a typed provider-budget error which preserves an existing artifact ref.
  private static func providerFailureEnvelope(
    provider: RealtimeHubProvider,
    name: String,
    error: [String: Any],
    originalOutput: String
  ) -> [String: Any] {
    let sourceEnvelope = parsedCanonicalToolResultEnvelope(from: originalOutput)
    let errorBytes =
      (try? JSONSerialization.data(withJSONObject: error, options: [.sortedKeys]))?.count ?? 0
    let sourceOriginalBytes = sourceEnvelope?["originalBytes"] as? Int
    let sourceRef = sourceEnvelope?["fullOutputRef"] as? String
    let preservesArtifact = sourceRef != nil && (sourceOriginalBytes ?? 0) > errorBytes
    let sourceProvenance = sourceEnvelope?["provenance"] as? [String: Any]
    return [
      "version": 1,
      "status": "failed",
      "truncated": preservesArtifact,
      "originalBytes": preservesArtifact ? sourceOriginalBytes! : errorBytes,
      "projectedBytes": errorBytes,
      "fullOutputRef": preservesArtifact ? sourceRef! : NSNull(),
      "provenance": sourceProvenance ?? [
        "invocationId": "realtime-\(provider.rawValue)-provider-budget-\(String(name.prefix(64)))",
        "runId": "unknown",
        "attemptId": "unknown",
        "toolName": String(name.prefix(128)),
      ],
    ]
  }

  private static func parsedCanonicalToolResultEnvelope(from output: String) -> [String: Any]? {
    guard let payload = try? JSONSerialization.jsonObject(with: Data(output.utf8)) as? [String: Any]
    else {
      return nil
    }
    if let envelope = payload["toolResultEnvelope"] as? [String: Any],
      isCanonicalToolResultEnvelope(envelope)
    {
      return envelope
    }
    if let providerResult = payload["providerResult"] as? [String: Any],
      let envelope = providerResult["toolResultEnvelope"] as? [String: Any],
      isCanonicalToolResultEnvelope(envelope)
    {
      return envelope
    }
    return nil
  }

  private static func isCanonicalToolResultEnvelope(_ value: Any?) -> Bool {
    guard let envelope = value as? [String: Any],
      envelope["version"] as? Int == 1,
      ["succeeded", "failed", "cancelled"].contains(envelope["status"] as? String ?? ""),
      let originalBytes = envelope["originalBytes"] as? Int,
      let projectedBytes = envelope["projectedBytes"] as? Int,
      let truncated = envelope["truncated"] as? Bool,
      originalBytes >= projectedBytes,
      truncated == (projectedBytes < originalBytes),
      let provenance = envelope["provenance"] as? [String: Any]
    else { return false }
    guard
      ["invocationId", "runId", "attemptId", "toolName"].allSatisfy({
        (provenance[$0] as? String)?.isEmpty == false
      })
    else { return false }
    if projectedBytes < originalBytes { return envelope["fullOutputRef"] as? String != nil }
    return envelope["fullOutputRef"] is NSNull || envelope["fullOutputRef"] == nil
  }
}

struct RealtimeHubLifecycleSnapshot: Equatable {
  let capturingInput: Bool
  let providerActive: Bool
  let playbackActive: Bool
  let pendingToolCount: Int
  let coordinatorTurnActive: Bool
  let minting: Bool
}

enum RealtimeHubLifecyclePolicy {
  static func canReplaceSession(_ snapshot: RealtimeHubLifecycleSnapshot) -> Bool {
    !snapshot.capturingInput
      && !snapshot.providerActive
      && !snapshot.playbackActive
      && snapshot.pendingToolCount == 0
      && !snapshot.coordinatorTurnActive
      && !snapshot.minting
  }

  static func canStartGeneralWarmSession(replacementPending: Bool) -> Bool {
    !replacementPending
  }

  static func shouldResumeCanceledTurnRefresh(
    fenceTurnID: VoiceTurnID?,
    terminalTurnID: VoiceTurnID
  ) -> Bool {
    fenceTurnID != terminalTurnID
  }
}

/// Immutable account identity attached to a realtime socket, its context, and
/// every token mint that may create or replace it. `signedOut` is a real scope,
/// distinct from the absence of a session, so a later sign-in cannot inherit a
/// socket that was warmed from signed-out/BYOK state.
enum RealtimeHubOwnerScope: Equatable, Sendable {
  case authenticated(String)
  case signedOut

  static func capture(currentOwnerID: String?) -> RealtimeHubOwnerScope {
    guard let ownerID = currentOwnerID?.trimmingCharacters(in: .whitespacesAndNewlines),
      !ownerID.isEmpty
    else { return .signedOut }
    return .authenticated(ownerID)
  }

  var authenticatedOwnerID: String? {
    guard case .authenticated(let ownerID) = self else { return nil }
    return ownerID
  }

  func isCurrent(currentOwnerID: String?) -> Bool {
    self == Self.capture(currentOwnerID: currentOwnerID)
  }
}

#if DEBUG
struct RealtimeHubOwnerBoundarySnapshot: Equatable {
  let hasPhysicalSession: Bool
  let physicalOwnerID: String?
  let prefetchedOwnerID: String?
  let prefetchedContextIsEmpty: Bool
  let hasPendingOwnerWork: Bool
  let hubConnected: Bool
  let turnAudioByteCount: Int
}

/// Exact non-production capability for the hermetic local-profile transport.
/// A process-wide "test mode" boolean is not enough: the authority is bound to
/// one physical session and one immutable owner scope, so a replaced socket or
/// an owner transition cannot inherit the provider-warm bypass.
struct RealtimeLocalProfileTransportAuthority: Equatable {
  let sourceID: ObjectIdentifier
  let ownerScope: RealtimeHubOwnerScope
  let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot

  func accepts(
    sourceID candidateSourceID: ObjectIdentifier?,
    currentOwnerID: String?,
    localProfileEnabled: Bool,
    authorizationIsCurrent: Bool
  ) -> Bool {
    localProfileEnabled
      && candidateSourceID == sourceID
      && ownerScope.isCurrent(currentOwnerID: currentOwnerID)
      && authorizationIsCurrent
  }
}
#endif

/// Shared owner policy used by warm reuse, delayed mint completion, and
/// barge-in replacement. Keeping these three paths on one decision surface
/// prevents a future reconnect path from accidentally weakening the fence.
enum RealtimeHubOwnerFence {
  static func canReuseWarmSession(
    sessionOwner: RealtimeHubOwnerScope?,
    currentOwnerID: String?
  ) -> Bool {
    guard let sessionOwner else { return false }
    return sessionOwner.isCurrent(currentOwnerID: currentOwnerID)
  }

  static func acceptsMintCompletion(
    mintOwner: RealtimeHubOwnerScope,
    currentOwnerID: String?
  ) -> Bool {
    mintOwner.isCurrent(currentOwnerID: currentOwnerID)
  }

  static func acceptsBargeInReplacement(
    sessionOwner: RealtimeHubOwnerScope?,
    replacementOwner: RealtimeHubOwnerScope?,
    currentOwnerID: String?
  ) -> Bool {
    guard let sessionOwner, let replacementOwner, sessionOwner == replacementOwner else {
      return false
    }
    return replacementOwner.isCurrent(currentOwnerID: currentOwnerID)
  }
}

enum RealtimeNativeAudioScheduleFailureAction: Equatable {
  case keepTextFallback
  case failTurnAfterPartialPlayback

  static func decide(playbackAlreadyStarted: Bool) -> RealtimeNativeAudioScheduleFailureAction {
    playbackAlreadyStarted ? .failTurnAfterPartialPlayback : .keepTextFallback
  }
}

enum RealtimeHubToolFailureKind: String, Equatable {
  case backendUnauthorized = "backend_unauthorized"
  case backendRateLimited = "backend_rate_limited"
  case backendClientRejected = "backend_client_rejected"
  case backendServerError = "backend_server_error"
  case backendTransport = "backend_transport"
  case responseDecode = "response_decode"
  case providerCredential = "provider_credential"
  case toolExecution = "tool_execution"

  static func classify(_ error: Error) -> RealtimeHubToolFailureKind {
    if error is DecodingError { return .responseDecode }
    if let apiError = error as? APIError {
      switch apiError {
      case .unauthorized:
        return .backendUnauthorized
      case .syncRateLimited:
        return .backendRateLimited
      case .invalidResponse, .decodingError:
        return .responseDecode
      case .httpError(let statusCode, _):
        switch statusCode {
        case 401, 403:
          return .backendUnauthorized
        case 408, 425, 429:
          return .backendRateLimited
        case 400..<500:
          return .backendClientRejected
        case 500..<600:
          return .backendServerError
        default:
          return .backendTransport
        }
      case .unsupportedTierScopedBulkMutation, .syncUploadRejected:
        return .backendClientRejected
      }
    }
    if let credentialError = error as? CredentialHealthError {
      switch credentialError.failureClass {
      case .requiresLogin, .backendUnauthorized:
        return .backendUnauthorized
      case .paywalled, .byokEnrollmentMismatch, .providerAuthFailed, .providerQuotaExceeded:
        return .providerCredential
      case .backendTransient:
        return .backendServerError
      case .providerTransient, .providerPolicyClose, .unknown:
        return .backendTransport
      }
    }
    let nsError = error as NSError
    if nsError.domain == NSURLErrorDomain { return .backendTransport }
    return .toolExecution
  }

  var userFacingReason: String {
    switch self {
    case .backendUnauthorized:
      return "Sign-in or account access needs attention."
    case .backendRateLimited:
      return "The service is rate limited; try again shortly."
    case .backendClientRejected:
      return "The request was rejected."
    case .backendServerError:
      return "The backend is temporarily unavailable."
    case .backendTransport:
      return "The network request failed."
    case .responseDecode:
      return "The response could not be read."
    case .providerCredential:
      return "The provider credential needs attention."
    case .toolExecution:
      return "The tool failed while running."
    }
  }
}

struct RealtimeHubToolFailure: Equatable {
  let kind: RealtimeHubToolFailureKind

  static func classify(_ error: Error) -> RealtimeHubToolFailure {
    RealtimeHubToolFailure(kind: RealtimeHubToolFailureKind.classify(error))
  }

  func userFacingOutput(base: String) -> String {
    "\(base) \(kind.userFacingReason)"
  }
}

/// A physical socket replacement must not invalidate the logical response
/// identity carried by buffered PTT input. The fresh session replays that
/// buffer with this response ID, and its callbacks must remain attributable to
/// the same reducer-owned turn. Ordinary teardown deliberately clears it.
enum RealtimeHubReconnectIdentityPolicy {
  static func responseIDAfterSessionDetach(
    preservingReconnectAudio: Bool,
    pendingReconnect: RealtimeReconnectAudioBuffer?
  ) -> VoiceResponseID? {
    guard preservingReconnectAudio, let pendingReconnect else { return nil }
    return pendingReconnect.responseID
  }

  /// Production boundary that admits/fences provider session callbacks before
  /// they become reducer events. Live-session object match is required so a
  /// replaced socket cannot speak for the current hub; owner currency matches
  /// `RealtimeHubOwnerFence.canReuseWarmSession`.
  static func admitsSessionCallback(
    isLiveSessionObject: Bool,
    sessionOwnerIsCurrent: Bool
  ) -> Bool {
    isLiveSessionObject && sessionOwnerIsCurrent
  }

  /// After a successful reconnect handshake, only the newly admitted session ID
  /// may complete the reducer path; a late callback carrying the superseded ID
  /// is fenced.
  static func admitsReconnectedSessionID(
    callbackSessionID: VoiceSessionID,
    liveSessionID: VoiceSessionID
  ) -> Bool {
    callbackSessionID == liveSessionID
  }
}

enum RealtimeHubEventOwnership {
  static func accepts(
    _ identity: RealtimeHubEventIdentity?,
    activeTurnID: VoiceTurnID?,
    activeResponseID: VoiceResponseID?
  ) -> Bool {
    guard let identity else { return false }
    return identity.turnID == activeTurnID && identity.responseID == activeResponseID
  }
}

enum VoiceAudioIngressOwnership {
  static func accepts(
    turnID: VoiceTurnID,
    activeTurnID: VoiceTurnID?,
    capturingInput: Bool
  ) -> Bool {
    turnID == activeTurnID && capturingInput
  }
}

enum RealtimeHubErrorOwnership {
  static func owns(
    route: VoiceTurnRoute?,
    activeSessionID: VoiceSessionID?
  ) -> Bool {
    guard case .hub(let expectedSessionID) = route else { return false }
    return expectedSessionID == nil || expectedSessionID == activeSessionID
  }
}

enum RealtimeHubBargeInAction: Equatable {
  case none
  case stopPlaybackTail
  case cancelInSession
  case replaceSession

  static func decide(
    providerResponseInFlight: Bool,
    playbackActive: Bool,
    strategy: RealtimeHubBargeInStrategy
  ) -> RealtimeHubBargeInAction {
    if providerResponseInFlight {
      return strategy == .freshSession ? .replaceSession : .cancelInSession
    }
    return playbackActive ? .stopPlaybackTail : .none
  }
}

enum RealtimeProviderTurnDoneDisposition: Equatable {
  case awaitToolContinuation
  case finalizeLogicalTurn

  static func decide(
    pendingToolCount: Int,
    postToolContinuationRequired: Bool
  ) -> Self {
    pendingToolCount > 0 || postToolContinuationRequired
      ? .awaitToolContinuation
      : .finalizeLogicalTurn
  }
}

/// A headless harness may retry only a turn whose request was actually lost.
/// Once the kernel has accepted a canonical spawn receipt, a session refresh is
/// expected completion work and replaying would create a second child run.
enum RealtimeHeadlessPTTSessionSwapPolicy {
  static func shouldRedrive(
    sessionChanged: Bool,
    hasCanonicalSpawnReceipt: Bool
  ) -> Bool {
    sessionChanged && !hasCanonicalSpawnReceipt
  }
}

enum RealtimeHubBargeInContinuity {
  enum Outcome: Equatable {
    case started
    case interruptedTurnPersistenceFailed
    case contextUnavailable
    case cancelled
  }

  static let maximumContextRefreshAttempts = 8

  static func prepareReplacementSession(
    resolveInterruptedTurn: () async -> InterruptedTurnPayload?,
    recordInterruptedTurn: (InterruptedTurnPayload) async -> Bool,
    refreshVoiceContext: () async -> Set<String>?,
    startReplacementSession: () -> Void
  ) async -> Outcome {
    let interruptedTurn = await resolveInterruptedTurn()
    if let interruptedTurn {
      guard await recordInterruptedTurn(interruptedTurn) else {
        return .interruptedTurnPersistenceFailed
      }
    }
    var requiredTurnIDs = Set<String>()
    if let interruptedTurn {
      if !interruptedTurn.userText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        requiredTurnIDs.insert(
          KernelTurnProjection.stableTurnID(
            continuityKey: interruptedTurn.idempotencyKey,
            role: "user"))
      }
      if !interruptedTurn.assistantText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        requiredTurnIDs.insert(
          KernelTurnProjection.stableTurnID(
            continuityKey: interruptedTurn.idempotencyKey,
            role: "assistant"))
      }
    }
    for _ in 0..<maximumContextRefreshAttempts {
      guard !Task.isCancelled else { return .cancelled }
      guard let refreshedTurnIDs = await refreshVoiceContext(),
        requiredTurnIDs.isSubset(of: refreshedTurnIDs)
      else {
        await Task.yield()
        continue
      }
      startReplacementSession()
      return .started
    }
    return Task.isCancelled ? .cancelled : .contextUnavailable
  }
}

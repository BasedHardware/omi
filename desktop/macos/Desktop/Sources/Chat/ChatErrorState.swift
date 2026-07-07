import Foundation

// MARK: - ChatErrorState
//
// Defines the five user-visible failure classes the chat surface needs
// explicit, recoverable UI for, and maps `BridgeError` onto them.
//
// Deliberately out of scope (kept as their own dedicated sheets, since
// they are product flows rather than generic error recovery):
//   - `ClaudeAuthSheet`        (Claude paywall flow)
//   - `showOmiThresholdAlert`  (usage-cap upgrade alert)

/// Why the bridge process is unavailable. Used to drive copy and choose
/// whether the primary recovery opens runtime install docs or retries.
enum BridgeUnavailableReason: Equatable, Sendable {
  /// Node.js binary not found on PATH (e.g. fresh install, dev build before
  /// `./run.sh`). Maps from `BridgeError.nodeNotFound`.
  case nodeMissing
  /// Bridge JS / AI components not on disk. Maps from
  /// `BridgeError.bridgeScriptNotFound`.
  case runtimeMissing
  /// Bridge process started but exited / OOM'd. Maps from
  /// `BridgeError.processExited` and `.outOfMemory`.
  case crashed
  /// Catch-all for "we don't know why it's not running"; maps from
  /// `BridgeError.notRunning`, `.restarting`, and any other un-classified
  /// start failure.
  case unknown
}

/// The five recoverable error states the chat UI renders inline.
///
/// Anything that does NOT map to a case here (e.g. `BridgeError.encodingError`,
/// `.quotaExceeded`, opaque `.agentError`) is intentionally left to the existing
/// `errorMessage` banner / sheets. The `from(_:)` factory returns `nil` in
/// those cases so callers can fall through.
enum ChatErrorState: Equatable, Sendable {
  /// Token expired or the bridge emitted `auth_required` mid-turn. Recovery:
  /// re-sign-in. Distinct from the Claude OAuth paywall.
  case authRequired

  /// Per-turn or per-tool timeout. `toolName` is the offending tool
  /// when the timeout was scoped (nil = full-turn timeout).
  case timeout(toolName: String?)

  /// Bridge process can't run. Reason picks the recovery: nodeMissing /
  /// runtimeMissing open runtime install docs; crashed / unknown retry.
  case bridgeUnavailable(reason: BridgeUnavailableReason)

  /// User pressed Stop / Cancel mid-turn. Recovery: resume (replay last
  /// user turn with a fresh `turnId`) or discard.
  case interrupted

  /// Tools returned empty payloads and the model produced no text. Recovery:
  /// nudge the user to try a different question instead of an infinite spinner.
  /// Intentionally has no `BridgeError` mapping yet; empty-result detection
  /// should set `currentError = .noDataFound` directly when that signal exists.
  case noDataFound
}

// MARK: - Recovery actions

/// One primary recovery action per error card. Multiple cases may share the
/// same recovery (e.g. timeout + interrupted both → retry) — that's intentional.
enum ChatErrorRecoveryAction: Equatable, Sendable, CaseIterable {
  /// Replay the last user turn with a fresh `turnId`.
  case retry
  /// Open the sign-in flow (Firebase / OAuth, NOT the Claude paywall).
  case signIn
  /// Show installation instructions for the bridge runtime (Node.js / AI
  /// components). Currently routes to a docs URL.
  case installRuntime
  /// Dismiss the card with no further action.
  case dismiss
}

extension ChatErrorState {
  /// The single primary CTA shown on the error card.
  ///
  /// Design note: we deliberately surface only ONE recovery per card. A
  /// "Show details" disclosure can offer secondary affordances, but the card
  /// itself stays scannable.
  var primaryRecovery: ChatErrorRecoveryAction {
    switch self {
    case .authRequired:
      return .signIn
    case .timeout:
      return .retry
    case .bridgeUnavailable(let reason):
      switch reason {
      case .nodeMissing, .runtimeMissing:
        return .installRuntime
      case .crashed, .unknown:
        return .retry
      }
    case .interrupted:
      return .retry
    case .noDataFound:
      return .dismiss
    }
  }
}

// MARK: - BridgeError mapping

extension ChatErrorState {
  /// Lift a `BridgeError` into a `ChatErrorState` when one of the five
  /// recoverable cases applies. Returns `nil` for errors that should keep
  /// flowing into the existing `errorMessage` banner (encoding errors,
  /// quota / paywall, generic agent errors).
  ///
  /// Cases handled:
  ///   - `.timeout`              → `.timeout(toolName: nil)`
  ///   - `.stopped`              → `.interrupted`
  ///   - `.nodeNotFound`         → `.bridgeUnavailable(.nodeMissing)`
  ///   - `.bridgeScriptNotFound` → `.bridgeUnavailable(.runtimeMissing)`
  ///   - `.processExited`        → `.bridgeUnavailable(.crashed)`
  ///   - `.outOfMemory`          → `.bridgeUnavailable(.crashed)`
  ///   - `.notRunning`           → `.bridgeUnavailable(.unknown)`
  ///   - `.restarting`           → `.bridgeUnavailable(.unknown)`
  ///   - `.authMissing`          → `.authRequired`
  ///
  /// Cases conditionally handled:
  ///   - `.agentError` session-token auth strings → `.authRequired`
  ///
  /// Cases intentionally returning `nil` (fall through to existing banner):
  ///   - `.encodingError`        (internal error, retry won't help)
  ///   - `.quotaExceeded`        (paywall — kept as separate sheet)
  ///   - opaque `.agentError`    (varied; existing banner already classifies)
  ///   - `.agentRuntimeFailure`  (already carries runtime-specific copy)
  ///   - `.requestAlreadyActive` (the existing banner explains the active turn)
  static func from(_ bridgeError: BridgeError) -> ChatErrorState? {
    switch bridgeError {
    case .timeout:
      return .timeout(toolName: nil)
    case .stopped:
      return .interrupted
    case .nodeNotFound:
      return .bridgeUnavailable(reason: .nodeMissing)
    case .bridgeScriptNotFound:
      return .bridgeUnavailable(reason: .runtimeMissing)
    case .processExited, .outOfMemory:
      return .bridgeUnavailable(reason: .crashed)
    case .notRunning, .restarting:
      return .bridgeUnavailable(reason: .unknown)
    case .authMissing:
      return .authRequired
    case .agentError(let message):
      return BridgeError.agentError(message).isSessionAuthenticationFailure ? .authRequired : nil
    case .encodingError, .quotaExceeded, .agentRuntimeFailure, .requestAlreadyActive:
      return nil
    }
  }
}

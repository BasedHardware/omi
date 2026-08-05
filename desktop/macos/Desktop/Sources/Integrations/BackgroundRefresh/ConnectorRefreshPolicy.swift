import Foundation

/// Machine-wide conditions the scheduler consults before running anything.
///
/// `isOnline` is part of the model so ``ConnectorRefreshPolicy/decide(supportsUnattendedRefresh:isConnected:refreshInterval:state:environment:isRunning:now:)``
/// is complete and testable, but the production probe always reports `true`:
/// this codebase has no reachability service and adding one to gate a
/// six-hourly import would be more moving parts than the problem needs.
/// Offline is absorbed by the transient-failure path instead — every connector
/// already classifies `URLError` into `.network`/`.timeout`, which backs off
/// and retries exactly as an offline window should.
struct ConnectorRefreshEnvironment: Equatable, Sendable {
  var isSignedIn: Bool
  var isOnline: Bool
  var isBatteryCritical: Bool

  init(isSignedIn: Bool = false, isOnline: Bool = true, isBatteryCritical: Bool = false) {
    self.isSignedIn = isSignedIn
    self.isOnline = isOnline
    self.isBatteryCritical = isBatteryCritical
  }
}

/// Why a connector was not refreshed on a given tick. Closed set, ordered by
/// how structural the reason is — see ``ConnectorRefreshPolicy/decide(supportsUnattendedRefresh:isConnected:refreshInterval:state:environment:isRunning:now:)``.
enum ConnectorRefreshSkipReason: String, Equatable, Sendable {
  case notEligibleForUnattendedRefresh
  case notConnected
  case needsUserAction
  case alreadyRunning
  case signedOut
  case offline
  case batteryCritical
  case backoffNotElapsed
  case intervalNotElapsed
}

enum ConnectorRefreshDecision: Equatable, Sendable {
  case refresh
  case skip(ConnectorRefreshSkipReason)
}

/// The pure core of background refresh: given a connector's declared
/// properties, its persisted state, and the machine environment, decide whether
/// to run and how state advances afterwards.
///
/// Nothing here touches UserDefaults, timers, the network, or the clock — every
/// input including `now` and `jitter` is passed in, so the whole decision
/// surface is deterministically testable.
enum ConnectorRefreshPolicy {
  /// First retry delay after a transient failure.
  static let baseBackoff: TimeInterval = 15 * 60
  /// Ceiling for exponential backoff.
  static let maxBackoff: TimeInterval = 6 * 3600
  /// Transient failures at which the connector escalates to `needsUserAction`
  /// and stops retrying. Five failures spans roughly eight hours of backoff —
  /// long enough that "the network is flaky" has been ruled out.
  static let maxConsecutiveFailures = 5
  /// Backoff is spread by ±15% so several Macs waking together do not retry in
  /// lockstep against the same backend.
  static let jitterFraction = 0.15
  /// A connected, eligible connector deferred past this multiple of its own
  /// interval is reported as a degraded fallback.
  static let stalenessFallbackMultiple = 2.0
  /// At most one fallback report per connector per day.
  static let fallbackReportCooldown: TimeInterval = 24 * 3600

  /// Skip reasons that represent "we wanted to refresh and could not", as
  /// opposed to expected steady state. Only these can escalate to a `deferred`
  /// fallback report; `intervalNotElapsed`, `notConnected`,
  /// `notEligibleForUnattendedRefresh`, `signedOut`, and `alreadyRunning` are
  /// normal and must never emit telemetry.
  static let deferralSkipReasons: Set<ConnectorRefreshSkipReason> = [
    .offline,
    .batteryCritical,
    .backoffNotElapsed,
  ]

  /// Decides whether a connector may refresh right now.
  ///
  /// Precedence is most-structural-first and is part of the contract:
  /// `notEligibleForUnattendedRefresh` → `notConnected` → `needsUserAction` →
  /// `alreadyRunning` → `signedOut` → `offline` → `batteryCritical` →
  /// `backoffNotElapsed` → `intervalNotElapsed`.
  ///
  /// The first gate is the consent-prompt guard: an ineligible connector is
  /// never refreshed in the background no matter how stale it is, because
  /// running it would raise a macOS permission dialog behind the user's back.
  static func decide(
    supportsUnattendedRefresh: Bool,
    isConnected: Bool,
    refreshInterval: TimeInterval,
    state: ConnectorRefreshState,
    environment: ConnectorRefreshEnvironment,
    isRunning: Bool,
    now: Date
  ) -> ConnectorRefreshDecision {
    guard supportsUnattendedRefresh else { return .skip(.notEligibleForUnattendedRefresh) }
    guard isConnected else { return .skip(.notConnected) }
    guard state.needsUserAction == nil else { return .skip(.needsUserAction) }
    guard !isRunning else { return .skip(.alreadyRunning) }
    guard environment.isSignedIn else { return .skip(.signedOut) }
    guard environment.isOnline else { return .skip(.offline) }
    guard !environment.isBatteryCritical else { return .skip(.batteryCritical) }
    if let nextEligibleAt = state.nextEligibleAt, now < nextEligibleAt {
      return .skip(.backoffNotElapsed)
    }
    guard isDue(lastSuccessAt: state.lastSuccessAt, refreshInterval: refreshInterval, now: now) else {
      return .skip(.intervalNotElapsed)
    }
    return .refresh
  }

  /// Due once the data is at least `refreshInterval` old. A connector that has
  /// never synced is always due — that is the "Google Calendar: never" case
  /// this whole subsystem exists to fix.
  static func isDue(lastSuccessAt: Date?, refreshInterval: TimeInterval, now: Date) -> Bool {
    guard let lastSuccessAt else { return true }
    return now.timeIntervalSince(lastSuccessAt) >= refreshInterval
  }

  /// Exponential backoff with injected jitter. `jitter` is clamped to [-1, 1]
  /// and supplied by the caller so tests are deterministic.
  static func backoffDelay(consecutiveFailures: Int, jitter: Double) -> TimeInterval {
    guard consecutiveFailures > 0 else { return 0 }
    let clampedJitter = min(max(jitter, -1), 1)
    let exponent = Double(consecutiveFailures - 1)
    let base = min(maxBackoff, baseBackoff * pow(2, exponent))
    return base * (1 + jitterFraction * clampedJitter)
  }

  /// Advances persisted state for a terminal refresh outcome.
  ///
  /// - success: clears failures, backoff, and any parked attention.
  /// - transientFailure: increments and schedules backoff; `lastSuccessAt` is
  ///   deliberately untouched so a failing connector keeps aging and the UI
  ///   keeps telling the truth about how stale it is.
  /// - transientFailure reaching ``maxConsecutiveFailures``: escalates to
  ///   `needsUserAction` and stops retrying.
  /// - needsUserAction: parks immediately with no backoff.
  static func applying(
    result: ConnectorRefreshResult,
    to state: ConnectorRefreshState,
    now: Date,
    jitter: Double
  ) -> ConnectorRefreshState {
    var next = state
    next.lastAttemptAt = now

    switch result {
    case .success:
      next.lastSuccessAt = now
      next.consecutiveFailures = 0
      next.nextEligibleAt = nil
      next.needsUserAction = nil

    case .transientFailure(let reason):
      next.consecutiveFailures += 1
      if next.consecutiveFailures >= maxConsecutiveFailures {
        next.needsUserAction = reason
        next.nextEligibleAt = nil
      } else {
        next.nextEligibleAt = now.addingTimeInterval(
          backoffDelay(consecutiveFailures: next.consecutiveFailures, jitter: jitter)
        )
      }

    case .needsUserAction(let reason):
      next.consecutiveFailures += 1
      next.needsUserAction = reason
      next.nextEligibleAt = nil
    }

    return next
  }

  /// Clears the failure bookkeeping a user-initiated success invalidates, while
  /// preserving the fallback dedupe stamp and any proven grant. This is the
  /// re-arm path: reconnecting from the Apps tab must unpark a connector
  /// without an app restart.
  static func reArmed(_ state: ConnectorRefreshState, now: Date) -> ConnectorRefreshState {
    var next = state
    next.lastSuccessAt = now
    next.lastAttemptAt = now
    next.consecutiveFailures = 0
    next.nextEligibleAt = nil
    next.needsUserAction = nil
    return next
  }

  /// Most-stale-first ordering. A connector that has never synced sorts ahead of
  /// every connector that has. Ties break on `connectorID` so a tick is
  /// deterministic.
  static func nextDue(_ candidates: [(connectorID: String, state: ConnectorRefreshState)], now: Date) -> String? {
    candidates
      .sorted { lhs, rhs in
        let lhsStaleness = staleness(lhs.state.lastSuccessAt, now: now)
        let rhsStaleness = staleness(rhs.state.lastSuccessAt, now: now)
        if lhsStaleness == rhsStaleness { return lhs.connectorID < rhs.connectorID }
        return lhsStaleness > rhsStaleness
      }
      .first?
      .connectorID
  }

  /// True when a fallback report is outside the dedupe window.
  static func shouldReportFallback(lastReportedAt: Date?, now: Date) -> Bool {
    guard let lastReportedAt else { return true }
    return now.timeIntervalSince(lastReportedAt) >= fallbackReportCooldown
  }

  /// True when a skip is a genuine deferral *and* the connector's data is now
  /// more than ``stalenessFallbackMultiple``× its interval old. A single
  /// deferred tick is normal; being stuck deferred past two intervals is a
  /// degraded sync path worth reporting once a day.
  static func shouldReportDeferral(
    skipReason: ConnectorRefreshSkipReason,
    state: ConnectorRefreshState,
    refreshInterval: TimeInterval,
    now: Date
  ) -> Bool {
    guard deferralSkipReasons.contains(skipReason) else { return false }
    guard shouldReportFallback(lastReportedAt: state.lastFallbackReportedAt, now: now) else { return false }
    // A connector that has neither succeeded nor been attempted has not been
    // deferred — there is nothing to be stale about yet.
    guard let reference = state.lastSuccessAt ?? state.lastAttemptAt else { return false }
    return now.timeIntervalSince(reference) > refreshInterval * stalenessFallbackMultiple
  }

  private static func staleness(_ lastSuccessAt: Date?, now: Date) -> TimeInterval {
    guard let lastSuccessAt else { return .greatestFiniteMagnitude }
    return now.timeIntervalSince(lastSuccessAt)
  }
}

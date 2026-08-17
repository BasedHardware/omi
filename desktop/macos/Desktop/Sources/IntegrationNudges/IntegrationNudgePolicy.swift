import Foundation

/// Pure, synchronous decision layer for proactive integration nudges.
///
/// A nudge fires when the user brings an app to the front that Omi has an
/// integration for and has not connected yet. The value of that nudge decays
/// fast: the first one is useful, the fourth is nagging. Every suppression rule
/// below exists to bound that, and lives here — not in the service — so the
/// nagging behavior is testable without a window server, a signed-in session, or
/// a notification center.
///
/// The decision is deliberately total: every call returns either `.deliver` or a
/// named `.suppress` reason, so telemetry can report *why* a nudge did not fire
/// without the service re-deriving it.
enum IntegrationNudgePolicy {
  /// Why a candidate nudge was not delivered. Closed set — this is also the
  /// bounded `suppression_reason` telemetry dimension, so every case must be a
  /// state the policy can actually reach.
  enum Suppression: String, Equatable, CaseIterable {
    /// The integration is already connected. The nudge has no job to do.
    case alreadyConnected = "already_connected"
    /// The user turned integration suggestions off in Settings.
    case featureDisabled = "feature_disabled"
    /// No signed-in owner, so "Connect" has nowhere to connect to.
    case notSignedIn = "not_signed_in"
    /// Onboarding already asks for connectors; nudging over it is duplicative.
    case onboardingIncomplete = "onboarding_incomplete"
    /// The user chose "Don't show again" for this integration.
    case optedOut = "opted_out"
    /// The user chose "Not now" for this integration recently.
    case snoozed = "snoozed"
    /// This integration was nudged recently enough that repeating is nagging.
    case connectorCooldown = "connector_cooldown"
    /// This integration has used up its lifetime nudge budget.
    case connectorLifetimeCap = "connector_lifetime_cap"
    /// Some other integration was nudged very recently.
    case globalCooldown = "global_cooldown"
    /// The per-day budget across all integrations is spent.
    case dailyCap = "daily_cap"
    /// The app was foregrounded but left again before the dwell threshold — an
    /// alt-tab flick past the window, not a session of work in it.
    case dwellTooShort = "dwell_too_short"
  }

  enum Decision: Equatable {
    case deliver
    case suppress(Suppression)

    var isDeliver: Bool { self == .deliver }

    var suppression: Suppression? {
      guard case .suppress(let reason) = self else { return nil }
      return reason
    }
  }

  /// Per-integration nudge history. Persisted by ``IntegrationNudgeStore``.
  struct ConnectorState: Equatable {
    var shownCount: Int = 0
    var lastShownAt: Date?
    var snoozedUntil: Date?
    var optedOut: Bool = false

    init(
      shownCount: Int = 0,
      lastShownAt: Date? = nil,
      snoozedUntil: Date? = nil,
      optedOut: Bool = false
    ) {
      self.shownCount = shownCount
      self.lastShownAt = lastShownAt
      self.snoozedUntil = snoozedUntil
      self.optedOut = optedOut
    }
  }

  /// Everything the decision depends on, gathered by the caller so the policy
  /// itself reads no globals and no clock.
  struct Input: Equatable {
    var isConnected: Bool
    var isFeatureEnabled: Bool
    var isSignedIn: Bool
    var isOnboardingComplete: Bool
    var connector: ConnectorState
    /// When any integration nudge was last delivered, across all connectors.
    var lastAnyNudgeAt: Date?
    /// Integration nudges already delivered inside the current day window.
    var nudgesInCurrentDay: Int
    /// How long the triggering app has been continuously frontmost.
    var dwell: TimeInterval
    var now: Date

    init(
      isConnected: Bool,
      isFeatureEnabled: Bool = true,
      isSignedIn: Bool = true,
      isOnboardingComplete: Bool = true,
      connector: ConnectorState = ConnectorState(),
      lastAnyNudgeAt: Date? = nil,
      nudgesInCurrentDay: Int = 0,
      dwell: TimeInterval = IntegrationNudgePolicy.requiredDwell,
      now: Date = Date()
    ) {
      self.isConnected = isConnected
      self.isFeatureEnabled = isFeatureEnabled
      self.isSignedIn = isSignedIn
      self.isOnboardingComplete = isOnboardingComplete
      self.connector = connector
      self.lastAnyNudgeAt = lastAnyNudgeAt
      self.nudgesInCurrentDay = nudgesInCurrentDay
      self.dwell = dwell
      self.now = now
    }
  }

  // MARK: - Budgets

  /// How long the app must stay frontmost before it counts as "the user opened
  /// it". Short on purpose — the nudge is supposed to land while the user is
  /// still looking at the app that prompted it — but long enough that cycling
  /// through windows with ⌘-Tab does not fire one.
  static let requiredDwell: TimeInterval = 3

  /// Minimum gap before the *same* integration may be nudged again.
  static let connectorCooldown: TimeInterval = 3 * 24 * 60 * 60

  /// Lifetime nudges per integration. After this, the Apps tab is the only
  /// remaining surface — the user has seen the pitch and not taken it.
  static let connectorLifetimeCap = 3

  /// Minimum gap between nudges for *any two* integrations, so opening Notion
  /// right after Gmail does not produce a second banner.
  static let globalCooldown: TimeInterval = 30 * 60

  /// Maximum integration nudges per rolling day, across all integrations.
  static let dailyCap = 2

  /// How long "Not now" silences one integration.
  static let snoozeDuration: TimeInterval = 7 * 24 * 60 * 60

  /// The rolling window `nudgesInCurrentDay` is counted over.
  static let dayWindow: TimeInterval = 24 * 60 * 60

  // MARK: - Decision

  /// Order matters only for which reason is reported; the gates are otherwise
  /// independent. Cheap, permanent facts come first so telemetry attributes a
  /// suppression to the durable cause (opted out) rather than an incidental one
  /// (global cooldown) that happened to also be true.
  static func decide(_ input: Input) -> Decision {
    if input.isConnected { return .suppress(.alreadyConnected) }
    if !input.isFeatureEnabled { return .suppress(.featureDisabled) }
    if !input.isSignedIn { return .suppress(.notSignedIn) }
    if !input.isOnboardingComplete { return .suppress(.onboardingIncomplete) }
    if input.connector.optedOut { return .suppress(.optedOut) }

    if let snoozedUntil = input.connector.snoozedUntil, input.now < snoozedUntil {
      return .suppress(.snoozed)
    }

    if input.connector.shownCount >= connectorLifetimeCap {
      return .suppress(.connectorLifetimeCap)
    }

    if let lastShownAt = input.connector.lastShownAt,
      input.now.timeIntervalSince(lastShownAt) < connectorCooldown
    {
      return .suppress(.connectorCooldown)
    }

    if input.dwell < requiredDwell { return .suppress(.dwellTooShort) }

    if input.nudgesInCurrentDay >= dailyCap { return .suppress(.dailyCap) }

    if let lastAnyNudgeAt = input.lastAnyNudgeAt,
      input.now.timeIntervalSince(lastAnyNudgeAt) < globalCooldown
    {
      return .suppress(.globalCooldown)
    }

    return .deliver
  }

  // MARK: - State transitions

  /// The state after a nudge for this integration was actually delivered.
  static func stateAfterDelivery(_ state: ConnectorState, now: Date) -> ConnectorState {
    var next = state
    next.shownCount += 1
    next.lastShownAt = now
    // A delivered nudge clears a lapsed snooze so the field cannot outlive the
    // decision that set it.
    if let snoozedUntil = next.snoozedUntil, snoozedUntil <= now {
      next.snoozedUntil = nil
    }
    return next
  }

  /// The state after the user dismissed a nudge with "Not now".
  static func stateAfterSnooze(_ state: ConnectorState, now: Date) -> ConnectorState {
    var next = state
    next.snoozedUntil = now.addingTimeInterval(snoozeDuration)
    return next
  }

  /// The state after the user chose "Don't show again" for this integration.
  static func stateAfterOptOut(_ state: ConnectorState) -> ConnectorState {
    var next = state
    next.optedOut = true
    return next
  }

  /// The state after the user connected the integration. Connecting is the goal
  /// state, so the history is cleared: if the user later disconnects, the pitch
  /// is allowed to start over rather than being permanently spent.
  static func stateAfterConnect(_ state: ConnectorState) -> ConnectorState {
    var next = state
    next.snoozedUntil = nil
    next.shownCount = 0
    next.lastShownAt = nil
    return next
  }
}

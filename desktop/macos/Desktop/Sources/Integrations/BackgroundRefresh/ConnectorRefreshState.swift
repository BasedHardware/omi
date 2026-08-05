import Foundation

/// Durable per-connector background refresh bookkeeping.
///
/// Deliberately distinct from `ImportConnectorStatusStore`'s display metrics:
/// that store answers "what should the Apps tab show", this one answers "may
/// the scheduler run this connector right now, and what happened last time".
struct ConnectorRefreshState: Codable, Equatable, Sendable {
  /// Last attempt that actually imported. `nil` means never synced, which the
  /// policy treats as maximally stale.
  var lastSuccessAt: Date?
  /// Last attempt of any kind. Diagnostic only — the policy never gates on it.
  var lastAttemptAt: Date?
  var consecutiveFailures: Int
  /// Earliest time a retry may run after a transient failure. `nil` means no
  /// backoff is in effect.
  var nextEligibleAt: Date?
  /// Non-nil parks the connector indefinitely: a credential or grant died and
  /// only a user-initiated reconnect can clear it. There is no backoff loop in
  /// this state — retrying would either fail identically or raise a prompt.
  var needsUserAction: ConnectorRefreshFailureReason?
  /// Dedupe stamp for `record_fallback`, so a parked connector reports at most
  /// once per ``ConnectorRefreshPolicy/fallbackReportCooldown``.
  var lastFallbackReportedAt: Date?
  /// Set only by a user-initiated run that proved a full, prompt-free grant
  /// (for local files: a scan that came back with no denied user folders).
  /// Backs `supportsUnattendedRefresh` for grant-gated connectors.
  var unattendedGrantProven: Bool

  init(
    lastSuccessAt: Date? = nil,
    lastAttemptAt: Date? = nil,
    consecutiveFailures: Int = 0,
    nextEligibleAt: Date? = nil,
    needsUserAction: ConnectorRefreshFailureReason? = nil,
    lastFallbackReportedAt: Date? = nil,
    unattendedGrantProven: Bool = false
  ) {
    self.lastSuccessAt = lastSuccessAt
    self.lastAttemptAt = lastAttemptAt
    self.consecutiveFailures = consecutiveFailures
    self.nextEligibleAt = nextEligibleAt
    self.needsUserAction = needsUserAction
    self.lastFallbackReportedAt = lastFallbackReportedAt
    self.unattendedGrantProven = unattendedGrantProven
  }
}

/// Persists the closed telemetry class by raw value and degrades an unknown
/// raw value to `.unknown` rather than throwing, so a case rename can never
/// wipe a user's whole refresh state blob.
extension IntegrationConnectTelemetry.ErrorClass: Codable {
  init(from decoder: any Decoder) throws {
    let rawValue = try decoder.singleValueContainer().decode(String.self)
    self = IntegrationConnectTelemetry.ErrorClass(rawValue: rawValue) ?? .unknown
  }

  func encode(to encoder: any Encoder) throws {
    var container = encoder.singleValueContainer()
    try container.encode(rawValue)
  }
}

/// User-scoped persistence for ``ConnectorRefreshState``, one JSON blob per
/// connector.
///
/// Key layout mirrors `ImportConnectorStatusStore.storageKey(prefix:connectorID:)`
/// exactly — `"<prefix>user.<userID>.<connectorID>"` — so a second signed-in
/// account never inherits the first account's refresh schedule. Keys are
/// computed at runtime rather than declared in `DefaultsKey.swift` for the same
/// reason all six `ImportConnectorStatusStore` prefixes are: they are
/// per-user/per-connector, not a fixed vocabulary.
@MainActor
final class ConnectorRefreshStateStore {
  private static let keyPrefix = "connectorBackgroundRefreshState."

  private let defaults: UserDefaults
  private var sessionUserID: String?

  init(defaults: UserDefaults = .standard, sessionUserID: String? = nil) {
    self.defaults = defaults
    self.sessionUserID = Self.normalizedUserID(
      sessionUserID ?? defaults.string(forKey: .authUserId)
    )
  }

  func setSessionUserID(_ userID: String?) {
    sessionUserID = Self.normalizedUserID(userID)
  }

  func state(for connectorID: String) -> ConnectorRefreshState {
    guard let data = defaults.data(forKey: storageKey(connectorID: connectorID)),
      let decoded = try? JSONDecoder().decode(ConnectorRefreshState.self, from: data)
    else {
      return ConnectorRefreshState()
    }
    return decoded
  }

  func setState(_ state: ConnectorRefreshState, for connectorID: String) {
    guard let encoded = try? JSONEncoder().encode(state) else {
      log("ConnectorRefreshStateStore: Failed to encode refresh state for \(connectorID)")
      return
    }
    defaults.set(encoded, forKey: storageKey(connectorID: connectorID))
  }

  func reset(connectorID: String) {
    defaults.removeObject(forKey: storageKey(connectorID: connectorID))
  }

  /// Records that a user-initiated run proved (or lost) a prompt-free grant.
  /// The only supported way to flip a grant-gated connector's
  /// `supportsUnattendedRefresh`.
  func recordUnattendedGrant(proven: Bool, for connectorID: String) {
    var state = state(for: connectorID)
    guard state.unattendedGrantProven != proven else { return }
    state.unattendedGrantProven = proven
    setState(state, for: connectorID)
  }

  private func storageKey(connectorID: String) -> String {
    guard let sessionUserID else { return Self.keyPrefix + connectorID }
    return "\(Self.keyPrefix)user.\(sessionUserID).\(connectorID)"
  }

  private static func normalizedUserID(_ userID: String?) -> String? {
    let trimmed = userID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? nil : trimmed
  }
}

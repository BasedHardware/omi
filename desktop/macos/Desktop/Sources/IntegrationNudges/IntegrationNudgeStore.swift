import Foundation

/// Durable nudge history, scoped to the signed-in owner.
///
/// Owner scoping matters here for the same reason it does in
/// `ImportConnectorStatusStore`: "you already declined this three times" is a
/// statement about a person, not about a Mac. A second account signing in on
/// the same machine starts with a clean slate rather than inheriting someone
/// else's dismissals.
///
/// `UserDefaults` is the right store: it is a handful of counters and dates
/// that must survive relaunch, and losing them degrades to "the user sees one
/// more nudge", never to broken state.
@MainActor
final class IntegrationNudgeStore {
  static let shared = IntegrationNudgeStore()

  private let defaults: UserDefaults
  /// Resolved on every access rather than cached.
  ///
  /// A cached snapshot has to be refreshed on `runtimeOwnerDidChange`, and that
  /// notification is posted *during* the revocation — so any refresh scheduled
  /// from it races the transition fence and can latch nil, leaving every read
  /// and write a no-op for the rest of the session. Resolving per access has no
  /// such window, and costs a dictionary lookup.
  private let resolveOwnerID: @MainActor () -> String?

  private var ownerID: String? { Self.normalized(resolveOwnerID()) }

  private enum Field {
    static let shownCount = "shownCount"
    static let lastShownAt = "lastShownAt"
    static let snoozedUntil = "snoozedUntil"
    static let optedOut = "optedOut"
    static let lastAnyNudgeAt = "lastAnyAt"
    static let recentDeliveries = "recentDeliveries"
  }

  init(
    defaults: UserDefaults = .standard,
    resolveOwnerID: @escaping @MainActor () -> String? = { RuntimeOwnerIdentity.currentOwnerId() }
  ) {
    self.defaults = defaults
    self.resolveOwnerID = resolveOwnerID
  }

  /// Convenience for tests and for callers that already hold a fixed owner.
  convenience init(defaults: UserDefaults, ownerID: String?) {
    self.init(defaults: defaults, resolveOwnerID: { ownerID })
  }

  // MARK: - Reads

  func state(for telemetryID: String, now: Date = Date()) -> IntegrationNudgePolicy.ConnectorState {
    guard ownerID != nil else { return IntegrationNudgePolicy.ConnectorState() }
    return IntegrationNudgePolicy.ConnectorState(
      shownCount: defaults.integer(forKey: key(Field.shownCount, telemetryID)),
      lastShownAt: pastDate(forKey: key(Field.lastShownAt, telemetryID), now: now),
      snoozedUntil: date(forKey: key(Field.snoozedUntil, telemetryID)),
      optedOut: defaults.bool(forKey: key(Field.optedOut, telemetryID))
    )
  }

  func lastAnyNudgeAt(now: Date = Date()) -> Date? {
    guard let budgetKey = budgetKey(Field.lastAnyNudgeAt) else { return nil }
    return pastDate(forKey: budgetKey, now: now)
  }

  /// Deliveries inside the trailing day window. Stored as raw timestamps rather
  /// than a counter plus a reset date so the window rolls continuously — a
  /// counter keyed to calendar days would let two nudges at 23:58 be followed
  /// immediately by two more at 00:01.
  func nudgesInCurrentDay(now: Date) -> Int {
    recentDeliveries(now: now).count
  }

  // MARK: - Writes

  func recordDelivery(telemetryID: String, now: Date) {
    guard ownerID != nil else { return }
    write(IntegrationNudgePolicy.stateAfterDelivery(state(for: telemetryID, now: now), now: now), for: telemetryID)

    guard let lastKey = budgetKey(Field.lastAnyNudgeAt),
      let recentKey = budgetKey(Field.recentDeliveries)
    else { return }
    defaults.set(now.timeIntervalSince1970, forKey: lastKey)
    var deliveries = recentDeliveries(now: now)
    deliveries.append(now.timeIntervalSince1970)
    defaults.set(deliveries, forKey: recentKey)
  }

  func recordSnooze(telemetryID: String, now: Date) {
    guard ownerID != nil else { return }
    write(IntegrationNudgePolicy.stateAfterSnooze(state(for: telemetryID, now: now), now: now), for: telemetryID)
  }

  func recordOptOut(telemetryID: String, now: Date = Date()) {
    guard ownerID != nil else { return }
    write(
      IntegrationNudgePolicy.stateAfterOptOut(state(for: telemetryID, now: now)), for: telemetryID)
  }

  func recordConnected(telemetryID: String, now: Date = Date()) {
    guard ownerID != nil else { return }
    write(
      IntegrationNudgePolicy.stateAfterConnect(state(for: telemetryID, now: now)), for: telemetryID)
  }

  /// Clears every nudge record for the current owner. Backs the Settings
  /// "Show integration suggestions again" affordance, so a user who dismissed
  /// everything early can get the pitches back without editing defaults.
  func resetAll(telemetryIDs: [String] = IntegrationNudgeCatalog.allTelemetryIDs) {
    guard ownerID != nil else { return }
    for telemetryID in telemetryIDs {
      defaults.removeObject(forKey: key(Field.shownCount, telemetryID))
      defaults.removeObject(forKey: key(Field.lastShownAt, telemetryID))
      defaults.removeObject(forKey: key(Field.snoozedUntil, telemetryID))
      defaults.removeObject(forKey: key(Field.optedOut, telemetryID))
    }
    if let lastKey = budgetKey(Field.lastAnyNudgeAt) { defaults.removeObject(forKey: lastKey) }
    if let recentKey = budgetKey(Field.recentDeliveries) { defaults.removeObject(forKey: recentKey) }
  }

  // MARK: - Internals

  private func write(_ state: IntegrationNudgePolicy.ConnectorState, for telemetryID: String) {
    defaults.set(state.shownCount, forKey: key(Field.shownCount, telemetryID))
    setDate(state.lastShownAt, forKey: key(Field.lastShownAt, telemetryID))
    setDate(state.snoozedUntil, forKey: key(Field.snoozedUntil, telemetryID))
    defaults.set(state.optedOut, forKey: key(Field.optedOut, telemetryID))
  }

  private func recentDeliveries(now: Date) -> [Double] {
    guard let recentKey = budgetKey(Field.recentDeliveries),
      let stored = defaults.array(forKey: recentKey) as? [Double]
    else { return [] }
    let cutoff = now.addingTimeInterval(-IntegrationNudgePolicy.dayWindow).timeIntervalSince1970
    // A clock rolled backwards would otherwise strand future-dated entries in
    // the window forever; drop anything that cannot be a past delivery.
    return stored.filter { $0 >= cutoff && $0 <= now.timeIntervalSince1970 }
  }

  private func date(forKey key: ScopedDefaultsKey) -> Date? {
    let timestamp = defaults.double(forKey: key)
    guard timestamp > 0 else { return nil }
    return Date(timeIntervalSince1970: timestamp)
  }

  /// Reads an instant that can only ever be in the past, discarding one that is
  /// not.
  ///
  /// A clock that moves backwards would otherwise leave `lastShownAt` and
  /// `lastAnyNudgeAt` permanently ahead of `now`, and the cooldown gates — which
  /// compare elapsed time against a positive budget — would silence every nudge
  /// until the skew passed. The rolling day window already drops future entries
  /// for the same reason.
  ///
  /// Deliberately *not* applied to `snoozedUntil`, which is a deadline and is in
  /// the future by definition: sanitizing that one would mean "Not now" never
  /// snoozed anything.
  private func pastDate(forKey key: ScopedDefaultsKey, now: Date) -> Date? {
    guard let value = date(forKey: key), value <= now else { return nil }
    return value
  }

  private func setDate(_ date: Date?, forKey key: ScopedDefaultsKey) {
    guard let date else {
      defaults.removeObject(forKey: key)
      return
    }
    defaults.set(date.timeIntervalSince1970, forKey: key)
  }

  /// Only ever called behind an `ownerID != nil` guard; a signed-out store
  /// reads and writes nothing.
  private func key(_ field: String, _ telemetryID: String) -> ScopedDefaultsKey {
    .integrationNudge(field, scope: "\(telemetryID).\(ownerID ?? "")")
  }

  private func budgetKey(_ field: String) -> ScopedDefaultsKey? {
    guard let ownerID else { return nil }
    return .integrationNudgeBudget(field, ownerID: ownerID)
  }

  private static func normalized(_ userID: String?) -> String? {
    guard let trimmed = userID?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
      return nil
    }
    return trimmed
  }
}

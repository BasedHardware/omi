import Foundation

/// Network seam for notification-settings GET/PATCH so the durable sync can be
/// exercised without a live backend.
protocol NotificationSettingsRemote: Sendable {
  func get() async throws -> NotificationSettingsResponse
  func update(enabled: Bool?, frequency: Int?) async throws -> NotificationSettingsResponse
}

struct LiveNotificationSettingsRemote: NotificationSettingsRemote {
  func get() async throws -> NotificationSettingsResponse {
    try await APIClient.shared.getNotificationSettings()
  }

  func update(enabled: Bool?, frequency: Int?) async throws -> NotificationSettingsResponse {
    try await APIClient.shared.updateNotificationSettings(enabled: enabled, frequency: frequency)
  }
}

enum NotificationSettingsSyncBackoff {
  static let initialNanoseconds: UInt64 = 1_000_000_000
  static let maxNanoseconds: UInt64 = 900_000_000_000

  /// Exponential delay capped at `maxNanoseconds` (15 minutes), so a client that
  /// stays offline settles at one PATCH attempt per 15 minutes instead of a
  /// retry storm. `attempt` is zero-based.
  static func delayNanoseconds(attempt: Int) -> UInt64 {
    let shift = min(max(attempt, 0), 10)
    let raw = initialNanoseconds &<< UInt64(shift)
    return min(raw, maxNanoseconds)
  }
}

/// Durable owner of notification-settings GET/PATCH. Local UserDefaults stay
/// authoritative for the delivery gate; this type only mirrors them to the
/// server and hydrates when no local mutation is in flight.
@MainActor
final class NotificationSettingsSyncCoordinator {
  static let shared = NotificationSettingsSyncCoordinator()

  typealias Sleeper = @Sendable (UInt64) async throws -> Void

  private let remote: NotificationSettingsRemote
  private let defaults: UserDefaults
  private let sleeper: Sleeper
  private let isSignedIn: () -> Bool

  private var pushTail: Task<Void, Never>?
  private var retryTask: Task<Void, Never>?
  private var reconcileTail: Task<Void, Never>?
  private var retryAttempt = 0
  private var authObserver: NSObjectProtocol?
  private var started = false
  /// True after a reconcile saw the server mirror disagree with the local pair.
  /// Cleared (with a heal log line) once they agree again — via hydration or a
  /// confirmed PATCH — so drift episodes are visible in published logs.
  private var driftObserved = false

  init(
    remote: NotificationSettingsRemote = LiveNotificationSettingsRemote(),
    defaults: UserDefaults = .standard,
    sleeper: @escaping Sleeper = { try await Task.sleep(nanoseconds: $0) },
    isSignedIn: @escaping () -> Bool = { AuthState.shared.isSignedIn }
  ) {
    self.remote = remote
    self.defaults = defaults
    self.sleeper = sleeper
    self.isSignedIn = isSignedIn
  }

  /// Launch entry point. Also listens for later sign-in so a pending PATCH is
  /// retried without opening Settings. Does not touch capture plugins.
  func start() {
    if !started {
      started = true
      authObserver = NotificationCenter.default.addObserver(
        forName: .sessionDidAuthenticate,
        object: nil,
        queue: nil
      ) { [weak self] _ in
        Task { @MainActor in
          self?.enqueueReconcile()
        }
      }
    }
    enqueueReconcile()
  }

  func cancel() {
    retryTask?.cancel()
    retryTask = nil
    pushTail?.cancel()
    pushTail = nil
    reconcileTail?.cancel()
    reconcileTail = nil
    if let authObserver {
      NotificationCenter.default.removeObserver(authObserver)
      self.authObserver = nil
    }
    started = false
  }

  private func enqueueReconcile() {
    let previous = reconcileTail
    reconcileTail = Task { [weak self] in
      await previous?.value
      await self?.reconcileOnce()
    }
  }

  /// Serial PATCH of the desired pair. Failures leave the pending journal set and
  /// arm bounded backoff until a later attempt completes the matching revision.
  func enqueue(enabled: Bool?, frequency: Int, revision: Int) {
    let previous = pushTail
    pushTail = Task { [weak self] in
      await previous?.value
      await self?.pushOnce(enabled: enabled, frequency: frequency, revision: revision)
    }
  }

  /// Serialized GET/hydrate entry point: concurrent callers (launch, sign-in,
  /// a Settings load) coalesce onto one tail so two GETs never race each other
  /// or interleave their hydrate decisions.
  func reconcile() async {
    let previous = reconcileTail
    let current = Task { [weak self] in
      await previous?.value
      await self?.reconcileOnce()
    }
    reconcileTail = current
    await current.value
  }

  /// GET then either hydrate UserDefaults or preserve local and retry PATCH.
  /// Uses `shouldPreserveLocalNotificationSettings` unchanged. The whole
  /// snapshot/decide/write sequence after the GET is synchronous on the main
  /// actor — no `await` may sit between the pending/revision snapshot and the
  /// hydrate write, or a local mutation in that window would be overwritten by
  /// the stale server pair. Telemetry is therefore recorded only afterwards.
  private func reconcileOnce() async {
    guard isSignedIn() else { return }
    let revisionAtStart = defaults.integer(forKey: NotificationService.settingsSyncRevisionDefaultsKey)
    let pendingAtStart = NotificationService.hasPendingNotificationSettingsSync(defaults: defaults)
    do {
      let server = try await remote.get()
      let revisionNow = defaults.integer(forKey: NotificationService.settingsSyncRevisionDefaultsKey)
      let pendingNow = NotificationService.hasPendingNotificationSettingsSync(defaults: defaults)
      let localEnabled = NotificationService.areNotificationsEnabled(defaults: defaults)
      let localFrequency = NotificationService.currentFrequencyLevel(defaults: defaults)
      let drifted = localEnabled != server.enabled || localFrequency != server.frequency
      var driftNewlyDetected = false
      if drifted, !driftObserved {
        driftObserved = true
        driftNewlyDetected = true
        log(
          "NotificationSettingsSync: drift detected — local enabled=\(localEnabled) "
            + "frequency=\(localFrequency), server enabled=\(server.enabled) "
            + "frequency=\(server.frequency), pendingSync=\(pendingNow)")
      } else if !drifted, driftObserved {
        driftObserved = false
        log("NotificationSettingsSync: drift healed — local and server mirror agree")
      }
      if NotificationService.shouldPreserveLocalNotificationSettings(
        revisionAtLoadStart: revisionAtStart,
        currentRevision: revisionNow,
        pendingAtLoadStart: pendingAtStart,
        pendingNow: pendingNow)
      {
        if pendingNow {
          enqueue(
            enabled: locallyDecidedEnabledForPatch(),
            frequency: localFrequency,
            revision: revisionNow)
        }
      } else {
        defaults.set(server.enabled, forKey: NotificationService.masterEnabledDefaultsKey)
        defaults.set(server.frequency, forKey: NotificationService.frequencyDefaultsKey)
        if driftObserved {
          driftObserved = false
          log("NotificationSettingsSync: drift healed — hydrated local mirror from server")
        }
      }
      if driftNewlyDetected {
        await ContextProactivityTelemetry.recordSettingsDrift(
          localEnabled: localEnabled,
          serverEnabled: server.enabled,
          localFrequency: localFrequency,
          serverFrequency: server.frequency,
          pendingSync: pendingNow)
      }
    } catch {
      logError("Failed to reconcile notification settings", error: error)
      if NotificationService.hasPendingNotificationSettingsSync(defaults: defaults) {
        scheduleRetry()
      }
    }
  }

  /// The master toggle to send when retrying a pending PATCH. Only a value the
  /// user (or a hydrate) actually wrote locally may be pushed: before the key
  /// exists — first launch, where only the frequency migration is pending — the
  /// PATCH sends nil so the server keeps a toggle another client may have set,
  /// instead of overwriting it with the absent-key default of `true`.
  private func locallyDecidedEnabledForPatch() -> Bool? {
    guard defaults.object(forKey: NotificationService.masterEnabledDefaultsKey) != nil else {
      return nil
    }
    return NotificationService.areNotificationsEnabled(defaults: defaults)
  }

  func waitUntilIdleForTesting() async {
    await reconcileTail?.value
    await pushTail?.value
    await retryTask?.value
  }

  private func pushOnce(enabled: Bool?, frequency: Int, revision: Int) async {
    guard isSignedIn() else {
      scheduleRetry()
      return
    }
    do {
      _ = try await remote.update(enabled: enabled, frequency: frequency)
      NotificationService.completeNotificationSettingsSync(revision: revision, defaults: defaults)
      if !NotificationService.hasPendingNotificationSettingsSync(defaults: defaults) {
        retryAttempt = 0
        retryTask?.cancel()
        retryTask = nil
        if driftObserved {
          driftObserved = false
          log("NotificationSettingsSync: drift healed — server confirmed the local pair")
        }
      }
    } catch {
      logError("Failed to update notification settings", error: error)
      scheduleRetry()
    }
  }

  private func scheduleRetry() {
    guard retryTask == nil else { return }
    retryTask = Task { [weak self] in
      await self?.retryPendingUntilConfirmed()
    }
  }

  private func retryPendingUntilConfirmed() async {
    while !Task.isCancelled {
      guard NotificationService.hasPendingNotificationSettingsSync(defaults: defaults) else {
        retryAttempt = 0
        retryTask = nil
        return
      }
      let delay = NotificationSettingsSyncBackoff.delayNanoseconds(attempt: retryAttempt)
      retryAttempt = min(retryAttempt + 1, 10)
      do {
        try await sleeper(delay)
      } catch {
        retryTask = nil
        return
      }
      guard !Task.isCancelled else {
        retryTask = nil
        return
      }
      guard NotificationService.hasPendingNotificationSettingsSync(defaults: defaults) else {
        retryAttempt = 0
        retryTask = nil
        return
      }
      let revision = defaults.integer(forKey: NotificationService.settingsSyncRevisionDefaultsKey)
      enqueue(
        enabled: locallyDecidedEnabledForPatch(),
        frequency: NotificationService.currentFrequencyLevel(defaults: defaults),
        revision: revision)
      await pushTail?.value
    }
    retryTask = nil
  }
}

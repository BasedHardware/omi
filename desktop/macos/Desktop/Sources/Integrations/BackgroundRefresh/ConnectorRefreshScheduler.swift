import AppKit
import Combine
import Foundation

/// A connector the user has to do something about before it can sync again.
/// Bounded and content-free: a closed failure class, a timestamp, and a short
/// message built from the connector's display name.
struct ConnectorRefreshAttention: Equatable, Sendable {
  var reason: ConnectorRefreshFailureReason
  var since: Date
  var message: String
}

/// Reports a background refresh fallback. Wraps
/// `DesktopDiagnosticsManager.recordFallback` so tests can observe emissions
/// without a diagnostics singleton.
typealias ConnectorRefreshFallbackReporter =
  @MainActor (
    _ connectorID: String,
    _ to: String,
    _ reason: String,
    _ outcome: DesktopFallbackOutcome
  ) -> Void

/// Drives periodic, unattended refreshes of import connectors.
///
/// Before this existed there was no scheduler anywhere in the desktop app:
/// "Connected" on the Apps tab was a UserDefaults timestamp latch, and a
/// connector that had last synced weeks earlier looked exactly like one that
/// synced this morning. `INV-INT-1` forbids gating connected state on a
/// timestamp latch or a one-time success; keeping the data actually fresh is
/// the other half of honoring it.
///
/// Design constraints worth keeping in mind before changing this class:
///
/// - **Never prompt.** Eligibility is declared per connector
///   (``BackgroundRefreshableConnector/supportsUnattendedRefresh``) and is the
///   first gate in ``ConnectorRefreshPolicy``. Nothing here may infer
///   eligibility from a connector id.
/// - **At most one connector per tick**, chosen most-stale-first. That is both
///   the anti-thundering-herd rule and an implicit global single-flight.
/// - **Single-flight is delegated**, not rebuilt: `ConnectorImportRunner.start`
///   already returns `nil` when a run for that connector is in flight, and it
///   already owns run state and terminal telemetry.
/// - **`tick()` is `internal` on purpose** so tests drive it directly and never
///   install a `Timer`.
@MainActor
final class ConnectorRefreshScheduler: ObservableObject {
  static let shared = ConnectorRefreshScheduler()

  /// Delay before the first tick after `start()`. Launch is already busy with
  /// auth restore, database open, and window setup; an import on top of that is
  /// the worst possible time.
  static let firstTickDelay: TimeInterval = 90
  static let tickInterval: TimeInterval = 5 * 60

  /// Connectors currently parked awaiting a user reconnect. UI reads this to
  /// stop showing a stale connector as healthy.
  @Published private(set) var attention: [String: ConnectorRefreshAttention] = [:]

  private let defaults: UserDefaults
  private let stateStore: ConnectorRefreshStateStore
  private let now: @MainActor () -> Date
  private let jitter: @MainActor () -> Double
  private let environmentProbe: @MainActor () -> ConnectorRefreshEnvironment
  private let recordFallback: ConnectorRefreshFallbackReporter

  private var connectors: [any BackgroundRefreshableConnector] = []
  private var statusStoreProvider: (@MainActor () -> ImportConnectorStatusStore?)?

  private var timer: Timer?
  private var firstTickTimer: Timer?
  private var observers: [any NSObjectProtocol] = []
  private var cancellables: Set<AnyCancellable> = []
  private var isTicking = false
  /// Guards the re-arm subscription against the scheduler's own
  /// `markSynced` write, which would otherwise echo back and clobber the state
  /// transition that just produced it.
  private var isApplyingRefreshResult = false
  /// Terminal results handed back from inside the runner's operation closure.
  private var pendingResults: [String: ConnectorRefreshResult] = [:]

  init(
    defaults: UserDefaults = .standard,
    stateStore: ConnectorRefreshStateStore? = nil,
    now: @escaping @MainActor () -> Date = { Date() },
    jitter: @escaping @MainActor () -> Double = { Double.random(in: -1...1) },
    environmentProbe: @escaping @MainActor () -> ConnectorRefreshEnvironment = {
      ConnectorRefreshScheduler.liveEnvironment()
    },
    recordFallback: @escaping ConnectorRefreshFallbackReporter = ConnectorRefreshScheduler.liveFallbackReporter
  ) {
    self.defaults = defaults
    self.stateStore = stateStore ?? ConnectorRefreshStateStore(defaults: defaults)
    self.now = now
    self.jitter = jitter
    self.environmentProbe = environmentProbe
    self.recordFallback = recordFallback
  }

  // MARK: - Configuration

  /// Wires the scheduler to its collaborators.
  ///
  /// The status store arrives as a **provider closure**, not a direct
  /// reference: the canonical store is owned by the view-model container and is
  /// not guaranteed to exist when the scheduler is constructed. A closure
  /// resolves it lazily at tick time and removes the init-ordering hazard.
  func configure(
    statusStoreProvider: @escaping @MainActor () -> ImportConnectorStatusStore?,
    connectors: [any BackgroundRefreshableConnector]
  ) {
    self.statusStoreProvider = statusStoreProvider
    self.connectors = connectors
  }

  /// Rescopes persisted refresh state when the signed-in account changes.
  func setSessionUserID(_ userID: String?) {
    stateStore.setSessionUserID(userID)
    attention.removeAll()
  }

  // MARK: - Lifecycle

  /// Idempotent. Installs the tick timer, a delayed first tick, wake and
  /// termination observers, and the user-sync re-arm subscription.
  func start() {
    guard timer == nil else { return }
    guard !connectors.isEmpty else {
      log("ConnectorRefreshScheduler: no connectors configured — not starting")
      return
    }

    log(
      "ConnectorRefreshScheduler: Starting (first tick in \(Int(Self.firstTickDelay))s, "
        + "interval \(Int(Self.tickInterval))s, \(connectors.count) connectors)"
    )

    timer = Timer.scheduledTimer(withTimeInterval: Self.tickInterval, repeats: true) { [weak self] _ in
      Task { @MainActor in
        await self?.tick()
      }
    }
    firstTickTimer = Timer.scheduledTimer(withTimeInterval: Self.firstTickDelay, repeats: false) { [weak self] _ in
      Task { @MainActor in
        await self?.tick()
      }
    }

    observers.append(
      NotificationCenter.default.addObserver(
        forName: NSApplication.willTerminateNotification,
        object: nil,
        queue: .main
      ) { [weak self] _ in
        Task { @MainActor in
          self?.stop()
        }
      }
    )
    // Waking from sleep is the single best moment to catch up: the machine has
    // usually been idle for hours and the tick timer did not fire while asleep.
    observers.append(
      NotificationCenter.default.addObserver(
        forName: .systemDidWake,
        object: nil,
        queue: .main
      ) { [weak self] _ in
        Task { @MainActor in
          await self?.tick()
        }
      }
    )

    statusStoreProvider?()?.connectorDidSync
      .sink { [weak self] connectorID in
        Task { @MainActor in
          self?.handleUserInitiatedSync(connectorID: connectorID)
        }
      }
      .store(in: &cancellables)
  }

  func stop() {
    timer?.invalidate()
    timer = nil
    firstTickTimer?.invalidate()
    firstTickTimer = nil
    for observer in observers {
      NotificationCenter.default.removeObserver(observer)
    }
    observers.removeAll()
    cancellables.removeAll()
    log("ConnectorRefreshScheduler: Stopped")
  }

  // MARK: - Ticking

  /// Evaluates every configured connector and refreshes at most one.
  ///
  /// Returns the policy decision per connector. A `.refresh` decision means the
  /// connector was eligible this tick, not that it was the one dispatched —
  /// only the most-stale eligible connector actually runs.
  @discardableResult
  func tick() async -> [String: ConnectorRefreshDecision] {
    guard !isTicking else { return [:] }
    isTicking = true
    defer { isTicking = false }

    let currentTime = now()
    let environment = environmentProbe()
    let statusStore = statusStoreProvider?()

    var decisions: [String: ConnectorRefreshDecision] = [:]
    var eligible: [(connectorID: String, state: ConnectorRefreshState)] = []

    for connector in connectors {
      let connectorID = connector.connectorID
      let state = stateStore.state(for: connectorID)
      let decision = ConnectorRefreshPolicy.decide(
        supportsUnattendedRefresh: connector.supportsUnattendedRefresh,
        isConnected: isConnected(connectorID: connectorID, statusStore: statusStore),
        refreshInterval: connector.refreshInterval,
        state: state,
        environment: environment,
        isRunning: ConnectorImportRunner.shared.isRunning(connectorID),
        now: currentTime
      )
      decisions[connectorID] = decision

      switch decision {
      case .refresh:
        eligible.append((connectorID: connectorID, state: state))
      case .skip(let reason):
        reportDeferralIfNeeded(
          connectorID: connectorID,
          skipReason: reason,
          state: state,
          refreshInterval: connector.refreshInterval,
          now: currentTime
        )
      }
    }

    guard let chosenID = ConnectorRefreshPolicy.nextDue(eligible, now: currentTime),
      let chosen = connectors.first(where: { $0.connectorID == chosenID })
    else {
      return decisions
    }

    await performRefresh(chosen, statusStore: statusStore, now: currentTime)
    return decisions
  }

  /// Clears failure bookkeeping after a user-initiated sync succeeds.
  ///
  /// This is the required re-arm path: a parked connector must come back to
  /// life the moment the user reconnects it, with no app restart. Invoked by
  /// the `connectorDidSync` subscription and callable directly.
  func handleUserInitiatedSync(connectorID: String) {
    guard !isApplyingRefreshResult else { return }
    let currentTime = now()
    let reArmed = ConnectorRefreshPolicy.reArmed(stateStore.state(for: connectorID), now: currentTime)
    stateStore.setState(reArmed, for: connectorID)
    attention[connectorID] = nil
  }

  // MARK: - Refresh dispatch

  private func performRefresh(
    _ connector: any BackgroundRefreshableConnector,
    statusStore: ImportConnectorStatusStore?,
    now currentTime: Date
  ) async {
    let connectorID = connector.connectorID
    let name = IntegrationConnectTelemetry.integrationName(forConnectorID: connectorID)

    // Single-flight is the runner's job: `start` returns nil when a run for the
    // same connector is already in flight, so there is no second mechanism here.
    let task = ConnectorImportRunner.shared.start(
      connectorID: connectorID,
      progressTitle: "Syncing \(name)",
      progressDetail: "Checking for new items.",
      // The runner is the single terminal telemetry boundary for imports, so an
      // unattended tick emits the same `Integration Connect
      // Attempted/Succeeded/Failed` events a user-initiated connect does.
      // Reporting them as `.apps` would fold timer-driven runs into the
      // user-initiated connect funnel and silently change what every existing
      // PostHog query measures.
      surface: .background
    ) { [weak self] sink in
      let result = await connector.refresh(progress: sink)
      self?.pendingResults[connectorID] = result
      return ConnectorRefreshOutcomeMapper.runOutcome(for: result, connectorID: connectorID)
    }

    guard let task else {
      log("ConnectorRefreshScheduler: \(connectorID) already running — deferring to the in-flight run")
      return
    }
    await task.value

    let result = pendingResults.removeValue(forKey: connectorID) ?? .transientFailure(reason: .unknown)
    apply(result: result, connectorID: connectorID, statusStore: statusStore, now: currentTime)
  }

  private func apply(
    result: ConnectorRefreshResult,
    connectorID: String,
    statusStore: ImportConnectorStatusStore?,
    now currentTime: Date
  ) {
    let updated = ConnectorRefreshPolicy.applying(
      result: result,
      to: stateStore.state(for: connectorID),
      now: currentTime,
      jitter: jitter()
    )
    stateStore.setState(updated, for: connectorID)

    switch result {
    case .success(let metrics):
      attention[connectorID] = nil
      // Only a real import advances the visible "Synced …" timestamp. A failure
      // must never move it — that is exactly the latch this subsystem replaces.
      isApplyingRefreshResult = true
      statusStore?.markSynced(
        connectorID: connectorID,
        sourceCount: metrics.sourceCount,
        memoryCount: metrics.memoryCount,
        lastDeltaCount: metrics.newItems,
        syncedAt: currentTime
      )
      isApplyingRefreshResult = false

    case .transientFailure, .needsUserAction:
      guard let reason = updated.needsUserAction else { return }
      attention[connectorID] = ConnectorRefreshAttention(
        reason: reason,
        since: currentTime,
        message: attentionMessage(connectorID: connectorID, reason: reason)
      )
      reportExhaustionIfNeeded(connectorID: connectorID, state: updated, reason: reason, now: currentTime)
    }
  }

  // MARK: - Fallback telemetry

  /// Retries are exhausted or a credential died: background refresh has
  /// degraded to manual-only for this connector until the user reconnects.
  private func reportExhaustionIfNeeded(
    connectorID: String,
    state: ConnectorRefreshState,
    reason: ConnectorRefreshFailureReason,
    now currentTime: Date
  ) {
    guard ConnectorRefreshPolicy.shouldReportFallback(lastReportedAt: state.lastFallbackReportedAt, now: currentTime)
    else { return }

    recordFallback(
      connectorID,
      "manual_only",
      ConnectorRefreshOutcomeMapper.isUserActionClass(reason) ? "auth" : "other",
      .exhausted
    )
    stampFallbackReport(connectorID: connectorID, now: currentTime)
  }

  /// The connector is connected and eligible but policy has kept deferring it
  /// past twice its own interval — the sync path is degraded even though
  /// nothing has failed outright.
  private func reportDeferralIfNeeded(
    connectorID: String,
    skipReason: ConnectorRefreshSkipReason,
    state: ConnectorRefreshState,
    refreshInterval: TimeInterval,
    now currentTime: Date
  ) {
    guard
      ConnectorRefreshPolicy.shouldReportDeferral(
        skipReason: skipReason,
        state: state,
        refreshInterval: refreshInterval,
        now: currentTime
      )
    else { return }

    recordFallback(connectorID, "deferred", "policy", .degraded)
    stampFallbackReport(connectorID: connectorID, now: currentTime)
  }

  private func stampFallbackReport(connectorID: String, now currentTime: Date) {
    var state = stateStore.state(for: connectorID)
    state.lastFallbackReportedAt = currentTime
    stateStore.setState(state, for: connectorID)
  }

  // MARK: - Collaborator reads

  private func isConnected(connectorID: String, statusStore: ImportConnectorStatusStore?) -> Bool {
    guard let statusStore,
      let connector = ImportConnector.all.first(where: { $0.id == connectorID })
    else {
      // Fail closed: with no authoritative connected state, do not import.
      return false
    }
    return statusStore.snapshot(for: connector).isConnected
  }

  private func attentionMessage(connectorID: String, reason: ConnectorRefreshFailureReason) -> String {
    let name = IntegrationConnectTelemetry.integrationName(forConnectorID: connectorID)
    if IntegrationConnectTelemetry.failureRequiresReconnect(reason) {
      return "\(name) needs to be reconnected."
    }
    return "\(name) can't sync automatically right now."
  }

  // MARK: - Live probes

  @MainActor
  static func liveEnvironment() -> ConnectorRefreshEnvironment {
    ConnectorRefreshEnvironment(
      isSignedIn: AuthState.shared.isSignedIn,
      // No reachability service exists in this app, and offline is already
      // handled correctly downstream: connectors classify `URLError` into
      // `.network`/`.timeout`, which backs off and retries. See
      // `ConnectorRefreshEnvironment`.
      isOnline: true,
      isBatteryCritical: ConnectorRefreshPowerProbe.isBatteryCritical()
    )
  }

  @MainActor
  static func liveFallbackReporter(
    connectorID: String,
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome
  ) {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "sync_dispatch",
      from: "background_refresh",
      to: to,
      reason: reason,
      outcome: outcome,
      extra: ["connector_id": connectorID]
    )
  }
}

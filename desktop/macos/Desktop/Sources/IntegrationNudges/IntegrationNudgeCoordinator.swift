import AppKit
import Combine
import Foundation

/// Watches which app the user brings to the front and, when it is one Omi
/// integrates with but the user has not connected, offers the connection once.
///
/// **Why this is not a `ProactiveAssistant`.** The assistant pipeline only runs
/// while screen monitoring is active, which requires Screen Recording
/// permission. Connecting Gmail is exactly the kind of setup a user does
/// *before* granting broad capture, so gating the offer on capture would hide
/// it from the people who need it most. This coordinator owns a plain
/// `NSWorkspace` activation observer instead — the same shape as
/// `TrialBannerService` — and works with no permissions at all for native-app
/// triggers. Window titles (used only for browser sites) are read
/// opportunistically and their absence simply means fewer nudges.
///
/// Delivery goes straight to `FloatingControlBarManager` rather than through
/// `NotificationService`. That is deliberate: `NotificationService` applies the
/// proactive-AI frequency slider, which ships at 0 (Off), so routing through it
/// would mean this feature is dark for almost every user. The master
/// Notifications toggle is still honored — it is checked explicitly in
/// ``decide(entry:isConnected:dwell:)`` — as is the floating bar's own snooze,
/// which `showNotification` enforces.
@MainActor
final class IntegrationNudgeCoordinator {
  static let shared = IntegrationNudgeCoordinator()

  /// The `assistantId` this feature's cards carry. Drives the card view chosen
  /// in `FloatingControlBarView.barNotification` and its longer auto-dismiss.
  static let assistantID = "integration_connect"

  /// Seconds between browser re-checks while a browser stays frontmost.
  private static let browserRecheckInterval: TimeInterval = 10
  /// How many re-checks one browser activation is allowed. Bounded on purpose:
  /// an unbounded poll would read the active window title for as long as the
  /// user keeps a browser focused, which is most of the day.
  private static let browserRecheckLimit = 6

  typealias Presenter =
    @MainActor (
      _ ownerID: String,
      _ entry: IntegrationNudgeCatalogEntry
    ) -> OwnerBoundNotificationPresentationResult

  /// The default presenter: the real floating-bar card.
  static let floatingBarPresenter: Presenter = { ownerID, entry in
    FloatingControlBarManager.shared.showNotification(
      ownerID: ownerID,
      title: "Connect \(entry.displayName) to Omi",
      message: entry.pitch,
      assistantId: IntegrationNudgeCoordinator.assistantID,
      sound: .none,
      action: .connectIntegration(telemetryID: entry.telemetryID)
    )
  }

  /// The app-wide switches a nudge decision depends on, read together at
  /// decision time. Grouped and injected so the coordinator's own rules can be
  /// tested without mutating `UserDefaults.standard` — which is shared process
  /// state that would leak between tests.
  struct Environment {
    var isFeatureEnabled: Bool
    var notificationsEnabled: Bool
    var isOnboardingComplete: Bool

    @MainActor
    static var live: Environment {
      Environment(
        isFeatureEnabled: IntegrationNudgeCoordinator.isFeatureEnabled,
        notificationsEnabled: NotificationService.areNotificationsEnabled(),
        isOnboardingComplete: UserDefaults.standard.bool(forKey: .hasCompletedOnboarding)
      )
    }
  }

  private let store: IntegrationNudgeStore
  private let now: () -> Date
  private let presenter: Presenter
  private let ownerID: @MainActor () -> String?
  private let environment: @MainActor () -> Environment
  private let frontmostBundleID: @MainActor () -> String?
  private let windowTitleProvider: @MainActor (_ bundleIdentifier: String, _ appName: String?) async -> String?
  private let connectionInspector: @MainActor (IntegrationNudgeRoute) async -> Bool
  private var activationObserver: NSObjectProtocol?
  private var ownerObserver: NSObjectProtocol?
  private var pendingEvaluation: Task<Void, Never>?
  private var browserRecheck: Task<Void, Never>?

  init(
    store: IntegrationNudgeStore = .shared,
    now: @escaping () -> Date = Date.init,
    presenter: @escaping Presenter = IntegrationNudgeCoordinator.floatingBarPresenter,
    ownerID: @escaping @MainActor () -> String? = { RuntimeOwnerIdentity.currentOwnerId() },
    environment: @escaping @MainActor () -> Environment = { .live },
    frontmostBundleID: @escaping @MainActor () -> String? = {
      NSWorkspace.shared.frontmostApplication?.bundleIdentifier
    },
    windowTitleProvider: @escaping @MainActor (String, String?) async -> String? = {
      await IntegrationNudgeCoordinator.liveWindowTitle(bundleIdentifier: $0, appName: $1)
    },
    connectionInspector: @escaping @MainActor (IntegrationNudgeRoute) async -> Bool = {
      await IntegrationConnectionInspector.isConnected($0)
    }
  ) {
    self.store = store
    self.now = now
    self.presenter = presenter
    self.ownerID = ownerID
    self.environment = environment
    self.frontmostBundleID = frontmostBundleID
    self.windowTitleProvider = windowTitleProvider
    self.connectionInspector = connectionInspector
  }

  // MARK: - Lifecycle

  func start() {
    guard activationObserver == nil else { return }

    store.setOwnerID(ownerID())

    activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
      forName: NSWorkspace.didActivateApplicationNotification,
      object: nil,
      queue: .main
    ) { notification in
      let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
      let bundleIdentifier = app?.bundleIdentifier
      let appName = app?.localizedName
      Task { @MainActor in
        IntegrationNudgeCoordinator.shared.handleActivation(
          bundleIdentifier: bundleIdentifier,
          appName: appName
        )
      }
    }

    log("IntegrationNudgeCoordinator: observing app activations")

    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange,
      object: nil,
      queue: .main
    ) { _ in
      MainActor.assumeIsolated {
        IntegrationNudgeCoordinator.shared.handleOwnerChange()
      }
    }
  }

  func stop() {
    if let activationObserver {
      NSWorkspace.shared.notificationCenter.removeObserver(activationObserver)
      self.activationObserver = nil
    }
    if let ownerObserver {
      NotificationCenter.default.removeObserver(ownerObserver)
      self.ownerObserver = nil
    }
    cancelPendingWork()
  }

  private func handleOwnerChange() {
    cancelPendingWork()
    store.setOwnerID(ownerID())
  }

  private func cancelPendingWork() {
    pendingEvaluation?.cancel()
    pendingEvaluation = nil
    browserRecheck?.cancel()
    browserRecheck = nil
  }

  // MARK: - Activation

  func handleActivation(bundleIdentifier: String?, appName: String?) {
    cancelPendingWork()
    guard let bundleIdentifier, !bundleIdentifier.isEmpty else { return }
    // Omi's own windows are not a trigger; nudging the user about an
    // integration while they are already looking at the Apps tab is noise.
    guard bundleIdentifier != Bundle.main.bundleIdentifier else { return }

    let dwell = IntegrationNudgePolicy.requiredDwell
    pendingEvaluation = Task { [weak self] in
      try? await Task.sleep(nanoseconds: UInt64(dwell * 1_000_000_000))
      guard !Task.isCancelled else { return }
      await self?.evaluate(bundleIdentifier: bundleIdentifier, appName: appName, dwell: dwell)
      guard !Task.isCancelled else { return }
      self?.startBrowserRecheckIfNeeded(bundleIdentifier: bundleIdentifier, appName: appName)
    }
  }

  /// A browser activation only tells us a browser is frontmost; the site the
  /// user actually opens may arrive a moment later, or on a tab switch that
  /// fires no activation at all. Re-check a bounded number of times.
  private func startBrowserRecheckIfNeeded(bundleIdentifier: String, appName: String?) {
    guard IntegrationNudgeMatcher.isBrowser(bundleIdentifier: bundleIdentifier) else { return }
    browserRecheck = Task { [weak self] in
      for _ in 0..<Self.browserRecheckLimit {
        try? await Task.sleep(nanoseconds: UInt64(Self.browserRecheckInterval * 1_000_000_000))
        guard !Task.isCancelled, let self, self.frontmostBundleID() == bundleIdentifier else { return }
        await self.evaluate(
          bundleIdentifier: bundleIdentifier,
          appName: appName,
          dwell: IntegrationNudgePolicy.requiredDwell
        )
      }
    }
  }

  /// Recognize the frontmost window and, if it earns one, offer its integration.
  ///
  /// Both lookups below are genuinely slow — reading the active window title
  /// goes through the Accessibility API with a timeout, and inspecting an export
  /// destination scans local MCP config files — so the user can easily switch
  /// apps while one is in flight. The identity captured before the first await
  /// is therefore re-verified after each one: a card that says "Connect Apple
  /// Notes" delivered while the user is now in Slack is worse than no card, and
  /// task cancellation alone cannot prevent it, because cancelling a task does
  /// not interrupt an `await` already in progress.
  func evaluate(bundleIdentifier: String, appName: String?, dwell: TimeInterval) async {
    let expectedOwner = ownerID()
    guard stillOnSameWindow(bundleIdentifier, expectedOwner: expectedOwner) else { return }

    let windowTitle = await windowTitleProvider(bundleIdentifier, appName)
    guard stillOnSameWindow(bundleIdentifier, expectedOwner: expectedOwner) else { return }

    let window = IntegrationNudgeMatcher.Window(
      bundleIdentifier: bundleIdentifier,
      windowTitle: windowTitle
    )
    guard let match = IntegrationNudgeMatcher.match(window) else { return }

    let isConnected = await connectionInspector(match.entry.route)
    guard stillOnSameWindow(bundleIdentifier, expectedOwner: expectedOwner) else { return }

    offer(match: match, isConnected: isConnected, dwell: dwell)
  }

  /// Whether the app that triggered this evaluation is still the one in front,
  /// for the same signed-in person, and the work has not been cancelled.
  private func stillOnSameWindow(_ bundleIdentifier: String, expectedOwner: String?) -> Bool {
    !Task.isCancelled
      && frontmostBundleID() == bundleIdentifier
      && ownerID() == expectedOwner
  }

  /// Decide, deliver, and record — the whole nudge lifecycle for one recognized
  /// window, with no I/O of its own beyond the injected presenter. Returns
  /// whether a card was actually delivered.
  @discardableResult
  func offer(
    match: IntegrationNudgeMatcher.Match,
    isConnected: Bool,
    dwell: TimeInterval
  ) -> Bool {
    let decision = decide(entry: match.entry, isConnected: isConnected, dwell: dwell)
    log(
      "IntegrationNudgeCoordinator: \(match.entry.telemetryID) trigger=\(match.trigger.id) "
        + "connected=\(isConnected) decision=\(decision.suppression?.rawValue ?? "deliver")"
    )

    if let reason = decision.suppression {
      // Only report suppressions the user could plausibly have wanted a nudge
      // for. `alreadyConnected` is the steady state for every integration the
      // user already set up, and would swamp the funnel.
      if reason != .alreadyConnected {
        AnalyticsManager.shared.integrationNudgeSuppressed(
          entry: match.entry,
          trigger: match.trigger,
          reason: reason
        )
      }
      return false
    }

    guard let ownerID = ownerID() else { return false }
    let result = presenter(ownerID, match.entry)
    // Record only on real presentation. Recording before the bar has accepted
    // the card would spend the integration's lifetime budget on a nudge the
    // user never saw — the exact defect the screen-capture-reset notice hit
    // (see `NotificationService.screenCaptureResetShownKey`).
    guard result == .presented || result == .queued else { return false }

    let shownCountBefore = store.state(for: match.entry.telemetryID).shownCount
    store.recordDelivery(telemetryID: match.entry.telemetryID, now: now())
    AnalyticsManager.shared.integrationNudgeShown(
      entry: match.entry,
      trigger: match.trigger,
      shownCount: shownCountBefore + 1
    )
    return true
  }

  /// Window titles are content. Do not read one for an app the user excluded
  /// from Rewind capture — that list is their statement about which apps Omi
  /// may look at, and it does not stop being true because a different feature
  /// is asking. Non-browsers need no title at all, so they never pay the
  /// Accessibility round-trip.
  static func liveWindowTitle(bundleIdentifier: String, appName: String?) async -> String? {
    guard IntegrationNudgeMatcher.isBrowser(bundleIdentifier: bundleIdentifier) else { return nil }
    if let appName, RewindSettings.shared.isAppExcluded(appName) { return nil }
    return await ScreenCaptureService.getActiveWindowInfoAsync().windowTitle
  }

  // MARK: - Decision

  func decide(
    entry: IntegrationNudgeCatalogEntry,
    isConnected: Bool,
    dwell: TimeInterval
  ) -> IntegrationNudgePolicy.Decision {
    let timestamp = now()
    let environment = environment()
    let input = IntegrationNudgePolicy.Input(
      isConnected: isConnected,
      isFeatureEnabled: environment.isFeatureEnabled && environment.notificationsEnabled,
      isSignedIn: ownerID() != nil,
      isOnboardingComplete: environment.isOnboardingComplete,
      connector: store.state(for: entry.telemetryID),
      lastAnyNudgeAt: store.lastAnyNudgeAt(),
      nudgesInCurrentDay: store.nudgesInCurrentDay(now: timestamp),
      dwell: dwell,
      now: timestamp
    )
    return IntegrationNudgePolicy.decide(input)
  }

  // MARK: - Card actions

  /// The user accepted. Open the real connector sheet — the same one the Apps
  /// tab opens — rather than a nudge-only connect path that could drift.
  func acceptPresentedNudge(telemetryID: String) {
    guard let entry = IntegrationNudgeCatalog.all.first(where: { $0.telemetryID == telemetryID }) else { return }
    AnalyticsManager.shared.integrationNudgeActioned(entry: entry, action: .connect)
    // Claim the connect that follows, so it lands in the funnel as a nudge
    // conversion rather than as an Apps-tab connect.
    IntegrationConnectOrigin.recordNudgeOpened(connectorID: entry.connectorID)

    AppDelegate.summonWindowTarget()?.openMainAppWindow()
    NotificationCenter.default.post(
      name: .navigateToSidebarItem,
      object: nil,
      userInfo: ["rawValue": SidebarNavItem.apps.rawValue]
    )
    let target: DesktopAutomationPresentationTarget =
      switch entry.route {
      case .importConnector(let id): .importConnector(id)
      case .exportDestination(let id): .exportDestination(id)
      }
    // One runloop hop so the Apps tab is mounted and listening before the
    // presentation command is issued — the same ordering
    // `ContextualTaskNavigationRouter` uses.
    DispatchQueue.main.async {
      DesktopAutomationPresentationCoordinator.shared.beginPresentation(target)
    }
  }

  /// "Not now" — snooze this integration.
  func snoozePresentedNudge(telemetryID: String) {
    guard let entry = IntegrationNudgeCatalog.all.first(where: { $0.telemetryID == telemetryID }) else { return }
    store.recordSnooze(telemetryID: telemetryID, now: now())
    AnalyticsManager.shared.integrationNudgeActioned(entry: entry, action: .notNow)
  }

  /// "Don't show again" — opt this integration out permanently.
  func dismissPresentedNudgeForever(telemetryID: String) {
    guard let entry = IntegrationNudgeCatalog.all.first(where: { $0.telemetryID == telemetryID }) else { return }
    store.recordOptOut(telemetryID: telemetryID)
    AnalyticsManager.shared.integrationNudgeActioned(entry: entry, action: .dismissForever)
  }

  /// Called when a connector finishes connecting, from any surface, so a later
  /// disconnect can start the pitch over instead of finding a spent budget.
  func noteConnected(route: IntegrationNudgeRoute) {
    store.recordConnected(telemetryID: route.telemetryID)
  }

  // MARK: - Settings

  static var isFeatureEnabled: Bool {
    // Absent means on: this is an opt-out, and the per-integration budgets are
    // what keep it from being noise.
    UserDefaults.standard.object(forKey: .integrationNudgesEnabled) as? Bool ?? true
  }

  static func setFeatureEnabled(_ enabled: Bool) {
    UserDefaults.standard.set(enabled, forKey: .integrationNudgesEnabled)
  }
}

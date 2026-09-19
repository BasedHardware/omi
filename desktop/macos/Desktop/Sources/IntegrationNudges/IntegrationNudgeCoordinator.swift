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
/// Notifications toggle is still honored — it is read in ``handleActivation``
/// before any window inspection, and again by the policy. The floating bar's
/// "hide for 2 hours" is deliberately *not* a gate: it is a statement about the
/// bar, not about notifications, and `NotificationService` documents the same
/// position — a hidden bar still delivers through the temp-show path.
@MainActor
final class IntegrationNudgeCoordinator {
  static let shared = IntegrationNudgeCoordinator()

  /// The `assistantId` this feature's cards carry. Selects the card view in
  /// `FloatingControlBarView.barNotification`. The card uses the bar's standard
  /// 6s dismissal like every other; giving this one longer meant editing a
  /// shared timeout whose SwiftLint baseline is down-only, so it is tracked as
  /// follow-up rather than smuggled in here.
  static let assistantID = "integration_connect"

  /// Seconds between browser re-checks while a browser stays frontmost.
  private static let browserRecheckInterval: TimeInterval = 10
  /// How many re-checks one browser activation is allowed. Bounded on purpose:
  /// an unbounded poll would read the active window title for as long as the
  /// user keeps a browser focused, which is most of the day.
  private static let browserRecheckLimit = 6

  /// `onPresented` fires only when the bar actually puts the card on screen.
  /// The nudge budget is spent from there, never from the return value: a
  /// `.queued` card is admitted to a queue, not shown, and a queue entry that
  /// is later dropped would otherwise burn one of the integration's three
  /// lifetime offers on a card nobody saw.
  typealias Presenter =
    @MainActor (
      _ ownerID: String,
      _ match: IntegrationNudgeMatcher.Match,
      _ onPresented: @escaping @MainActor () -> Void,
      _ onDropped: @escaping @MainActor () -> Void
    ) -> OwnerBoundNotificationPresentationResult

  /// The default presenter: the real floating-bar card.
  ///
  /// Goes through `NotificationService` rather than the floating-bar primitive
  /// so the card is subject to the master toggle, frequency throttle, snooze and
  /// presence gates. An integration pitch is a suggestion, not a functional
  /// notice: a user who silenced suggestions, or who is on a call with their
  /// screen shared, is exactly who should not be offered one. The budget is
  /// unaffected by a suppression — `onPresented` only fires on a real
  /// presentation, so a withheld offer stays unspent.
  static let floatingBarPresenter: Presenter = { ownerID, match, onPresented, onDropped in
    NotificationService.shared.presentActionableProactiveNotification(
      ownerID: ownerID,
      title: "Connect \(match.entry.displayName)",
      message: match.entry.pitch,
      assistantId: IntegrationNudgeCoordinator.assistantID,
      kind: .integration,
      action: .connectIntegration(
        telemetryID: match.entry.telemetryID,
        triggerID: match.trigger.id
      ),
      sound: .none,
      onPresented: onPresented,
      onDropped: onDropped
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

    activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
      forName: NSWorkspace.didActivateApplicationNotification,
      object: nil,
      queue: .main
    ) { [weak self] notification in
      let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
      let bundleIdentifier = app?.bundleIdentifier
      let appName = app?.localizedName
      Task { @MainActor in
        self?.handleActivation(bundleIdentifier: bundleIdentifier, appName: appName)
      }
    }

    log("IntegrationNudgeCoordinator: observing app activations")

    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.handleOwnerChange()
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

  /// The store resolves the owner per access, so nothing needs re-scoping here
  /// — which is deliberate: `runtimeOwnerDidChange` is posted *during* the
  /// revocation, so any snapshot taken from this handler, immediately or after a
  /// hop, races the transition fence. What does have to happen is dropping the
  /// caches and pending work that belong to the person who just left.
  private func handleOwnerChange() {
    cancelPendingWork()
    IntegrationConnectOrigin.reset()
    IntegrationConnectionInspector.invalidateCaches()
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
    // Switched off means switched off: no Accessibility window-title read, no
    // connector inspection, no telemetry. Consulting the toggle later — inside
    // the policy — would leave a disabled feature doing all of its work and
    // discarding the answer.
    guard isEnabledNow else { return }

    pendingEvaluation = Task { [weak self] in
      try? await Task.sleep(
        nanoseconds: UInt64(IntegrationNudgePolicy.requiredDwell * 1_000_000_000))
      guard !Task.isCancelled, let self else { return }
      let (outcome, title) = await self.evaluate(
        bundleIdentifier: bundleIdentifier, appName: appName, lastTitle: nil)
      guard !Task.isCancelled, outcome.shouldKeepWatching else { return }
      // Hand the title forward so the first re-check does not redo the work the
      // short-circuit exists to skip.
      self.startBrowserRecheckIfNeeded(
        bundleIdentifier: bundleIdentifier, appName: appName, lastTitle: title)
    }
  }

  /// A browser activation only tells us a browser is frontmost; the site the
  /// user actually opens may arrive a moment later, or on a tab switch that
  /// fires no activation at all. Re-check a bounded number of times.
  ///
  /// The loop stops as soon as the answer is settled — a card was delivered, or
  /// a suppression that cannot change while the user stays in this window. It
  /// used to run all six rounds regardless, which multiplied the suppressed
  /// event (documented as the funnel's denominator) by six per activation and
  /// re-read the window title for a decision already made.
  private func startBrowserRecheckIfNeeded(
    bundleIdentifier: String,
    appName: String?,
    lastTitle initialTitle: String?
  ) {
    guard IntegrationNudgeMatcher.isBrowser(bundleIdentifier: bundleIdentifier) else { return }
    browserRecheck = Task { [weak self] in
      var lastTitle = initialTitle
      for _ in 0..<Self.browserRecheckLimit {
        try? await Task.sleep(nanoseconds: UInt64(Self.browserRecheckInterval * 1_000_000_000))
        guard !Task.isCancelled, let self, self.isEnabledNow,
          self.frontmostBundleID() == bundleIdentifier
        else { return }
        let (outcome, title) = await self.evaluate(
          bundleIdentifier: bundleIdentifier, appName: appName, lastTitle: lastTitle)
        lastTitle = title
        guard outcome.shouldKeepWatching else { return }
      }
    }
  }

  /// Whether a nudge is possible at all right now, independent of which window
  /// is in front. Read before any inspection, not as part of the nudge decision.
  ///
  /// Signed-out and mid-onboarding are included deliberately: without them a
  /// signed-out user emits a suppressed event on every Finder activation — and
  /// Finder is activated constantly — for a state that cannot change until they
  /// sign in.
  private var isEnabledNow: Bool {
    let environment = environment()
    return environment.isFeatureEnabled
      && environment.notificationsEnabled
      && environment.isOnboardingComplete
      && ownerID() != nil
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
  @discardableResult
  func evaluate(bundleIdentifier: String, appName: String?) async -> Outcome {
    await evaluate(bundleIdentifier: bundleIdentifier, appName: appName, lastTitle: nil).0
  }

  /// Returns the outcome and the title it was decided from, so a re-check can
  /// skip the work entirely when nothing on screen changed.
  private func evaluate(
    bundleIdentifier: String,
    appName: String?,
    lastTitle: String?
  ) async -> (Outcome, String?) {
    let expectedOwner = ownerID()
    guard stillOnSameWindow(bundleIdentifier, expectedOwner: expectedOwner) else {
      return (.abandoned, lastTitle)
    }

    let windowTitle = await windowTitleProvider(bundleIdentifier, appName)
    guard stillOnSameWindow(bundleIdentifier, expectedOwner: expectedOwner) else {
      return (.abandoned, lastTitle)
    }
    // Same tab as last round: the answer cannot have changed, so skip the match,
    // the connection check and the decision entirely.
    if let lastTitle, lastTitle == windowTitle { return (.noMatchYet, windowTitle) }

    let window = IntegrationNudgeMatcher.Window(
      bundleIdentifier: bundleIdentifier,
      windowTitle: windowTitle
    )
    // No integration recognized yet — in a browser the user may still be about
    // to open one, so this is the one outcome worth watching for.
    guard let match = IntegrationNudgeMatcher.match(window) else { return (.noMatchYet, windowTitle) }

    // Settle everything that does not need the connection state first. For an
    // export destination the inspection is a local MCP config scan, and a user
    // who pressed "Never" should not pay for it on every activation.
    if let settled = decideWithoutConnectionState(entry: match.entry) {
      return (.settled(settled), windowTitle)
    }

    let isConnected = await connectionInspector(match.entry.route)
    guard stillOnSameWindow(bundleIdentifier, expectedOwner: expectedOwner) else {
      return (.abandoned, windowTitle)
    }

    return (offer(match: match, isConnected: isConnected), windowTitle)
  }

  /// What one evaluation concluded, and whether re-checking this window could
  /// still change the answer.
  enum Outcome: Equatable {
    /// The window changed, the owner changed, or the work was cancelled.
    case abandoned
    /// Nothing recognized — a browser tab may still become one.
    case noMatchYet
    /// A card was handed to the bar.
    case delivered
    /// Suppressed for a reason that cannot change while the user stays here.
    case settled(IntegrationNudgePolicy.Suppression)

    /// Whether re-checking this browser could still produce a different answer.
    ///
    /// An unrecognized window obviously can — the user may not have opened the
    /// site yet. So can a settlement that was about *one integration*: someone
    /// whose Gmail is already connected should still be offered ChatGPT when
    /// they switch tabs. What ends the session is a global refusal or a card
    /// already delivered.
    var shouldKeepWatching: Bool {
      switch self {
      case .noMatchYet: return true
      case .settled(let reason): return IntegrationNudgePolicy.isPerIntegration(reason)
      case .delivered, .abandoned: return false
      }
    }
  }

  /// The gates that do not need the connection state, evaluated against the
  /// same live inputs `decide` uses.
  private func decideWithoutConnectionState(
    entry: IntegrationNudgeCatalogEntry
  ) -> IntegrationNudgePolicy.Suppression? {
    IntegrationNudgePolicy.decideWithoutConnectionState(
      policyInput(entry: entry, isConnected: false)
    )?.suppression
  }

  /// Whether the app that triggered this evaluation is still the one in front,
  /// for the same signed-in person, and the work has not been cancelled.
  private func stillOnSameWindow(_ bundleIdentifier: String, expectedOwner: String?) -> Bool {
    !Task.isCancelled
      && frontmostBundleID() == bundleIdentifier
      && ownerID() == expectedOwner
  }

  /// Decide, deliver, and record — the whole nudge lifecycle for one recognized
  /// window, with no I/O of its own beyond the injected presenter.
  @discardableResult
  func offer(
    match: IntegrationNudgeMatcher.Match,
    isConnected: Bool
  ) -> Outcome {
    let decision = decide(entry: match.entry, isConnected: isConnected)
    log(
      "IntegrationNudgeCoordinator: \(match.entry.telemetryID) trigger=\(match.trigger.id) "
        + "connected=\(isConnected) decision=\(decision.suppression?.rawValue ?? "deliver")"
    )

    if let reason = decision.suppression { return .settled(reason) }

    guard let ownerID = ownerID() else { return .settled(.notSignedIn) }

    // The budget is spent from the bar's presentation callback, not from the
    // return value. A `.queued` card has been admitted to a queue, not shown,
    // and a queue entry that is later dropped would otherwise burn one of the
    // integration's three lifetime offers on a card nobody saw — the same shape
    // as the screen-capture-reset defect (see
    // `NotificationService.screenCaptureResetShownKey`).
    var recorded = false

    let onPresented: @MainActor () -> Void = { [weak self] in
      // This fires only when the bar actually drew the card, so the user saw
      // the offer and it counts — whatever they are looking at by then. Gating
      // it on the app still being frontmost would let the same integration be
      // offered again and again, each time free, which is the opposite of the
      // budget's purpose.
      guard let self else { return }
      recorded = true
      let shownCountBefore = self.store.state(for: match.entry.telemetryID).shownCount
      self.store.recordDelivery(telemetryID: match.entry.telemetryID, now: self.now())
      AnalyticsManager.shared.integrationNudgeShown(
        entry: match.entry,
        trigger: match.trigger,
        shownCount: shownCountBefore + 1
      )
    }

    // A dropped card needs no handling: the budget simply stays unspent, so the
    // next activation offers it again.
    let result = presenter(ownerID, match, onPresented, {})

    // `.presented` invokes the callback synchronously; `.queued` invokes it
    // later, if and only if the card reaches the screen. Either way the bar owns
    // the card now and this window's answer is settled.
    guard recorded || result == .queued else {
      // The bar refused it — a changed owner, or no window to draw in. Neither
      // gets better by re-reading the title in ten seconds. `showNotification`
      // calls `onDropped` *and then* returns the refusal, so only report here
      // when it did not already.
      return .settled(.barUnavailable)
    }
    return .delivered
  }

  /// Window titles are content. Do not read one for an app the user excluded
  /// from Rewind capture — that list is their statement about which apps Omi
  /// may look at, and it does not stop being true because a different feature
  /// is asking. Non-browsers need no title at all, so they never pay the
  /// Accessibility round-trip.
  static func liveWindowTitle(bundleIdentifier: String, appName: String?) async -> String? {
    guard IntegrationNudgeMatcher.isBrowser(bundleIdentifier: bundleIdentifier) else { return nil }
    if let appName, RewindSettings.shared.isAppExcluded(appName) { return nil }

    let info = await ScreenCaptureService.getActiveWindowInfoAsync()
    // The lookup can answer from a cache up to a couple of seconds old, and that
    // snapshot may belong to whatever app was in front before this activation.
    // Pairing someone else's title with this app is how a TextEdit window named
    // "Gmail integration notes" becomes a Gmail nudge in the browser you just
    // switched to, so the title is only used when its own app agrees.
    guard let appName, info.appName == appName else { return nil }
    return info.windowTitle
  }

  // MARK: - Decision

  func decide(
    entry: IntegrationNudgeCatalogEntry,
    isConnected: Bool
  ) -> IntegrationNudgePolicy.Decision {
    IntegrationNudgePolicy.decide(policyInput(entry: entry, isConnected: isConnected))
  }

  private func policyInput(
    entry: IntegrationNudgeCatalogEntry,
    isConnected: Bool
  ) -> IntegrationNudgePolicy.Input {
    let timestamp = now()
    let environment = environment()
    return IntegrationNudgePolicy.Input(
      isConnected: isConnected,
      isFeatureEnabled: environment.isFeatureEnabled && environment.notificationsEnabled,
      isSignedIn: ownerID() != nil,
      isOnboardingComplete: environment.isOnboardingComplete,
      connector: store.state(for: entry.telemetryID, now: timestamp),
      lastAnyNudgeAt: store.lastAnyNudgeAt(now: timestamp),
      nudgesInCurrentDay: store.nudgesInCurrentDay(now: timestamp),
      now: timestamp
    )
  }

  // MARK: - Card actions

  /// The user accepted. Open the real connector sheet — the same one the Apps
  /// tab opens — rather than a nudge-only connect path that could drift.
  func acceptPresentedNudge(telemetryID: String, triggerID: String) {
    guard let entry = IntegrationNudgeCatalog.entry(telemetryID: telemetryID) else { return }
    AnalyticsManager.shared.integrationNudgeActioned(
      entry: entry, action: .connect, triggerID: triggerID)
    // Claim the connect that follows, so it lands in the connect funnel as a
    // nudge conversion rather than as an Apps-tab connect. Only imports have a
    // connect funnel; exports are measured by the Actioned event above.
    IntegrationConnectOrigin.recordNudgeOpened(for: entry.route)

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
  func snoozePresentedNudge(telemetryID: String, triggerID: String) {
    guard let entry = IntegrationNudgeCatalog.entry(telemetryID: telemetryID) else { return }
    store.recordSnooze(telemetryID: telemetryID, now: now())
    AnalyticsManager.shared.integrationNudgeActioned(
      entry: entry, action: .notNow, triggerID: triggerID)
  }

  /// "Don't show again" — opt this integration out permanently.
  func dismissPresentedNudgeForever(telemetryID: String, triggerID: String) {
    guard let entry = IntegrationNudgeCatalog.entry(telemetryID: telemetryID) else { return }
    store.recordOptOut(telemetryID: telemetryID)
    AnalyticsManager.shared.integrationNudgeActioned(
      entry: entry, action: .dismissForever, triggerID: triggerID)
  }

  /// Called when a connector finishes connecting, from any surface, so a later
  /// disconnect can start the pitch over instead of finding a spent budget.
  func noteConnected(route: IntegrationNudgeRoute) {
    store.recordConnected(telemetryID: route.telemetryID)
    // Only an export connect changes what the export scan would find; a routine
    // Gmail sync should not throw away a cache it cannot have invalidated.
    if case .exportDestination = route {
      IntegrationConnectionInspector.invalidateExportStatuses()
    }
  }

  // MARK: - Settings

  static var isFeatureEnabled: Bool {
    // Absent means on: this is an opt-out, and the per-integration budgets are
    // what keep it from being noise.
    UserDefaults.standard.object(forKey: .integrationNudgesEnabled) as? Bool ?? true
  }

}

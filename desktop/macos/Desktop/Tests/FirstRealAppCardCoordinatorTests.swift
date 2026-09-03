import XCTest

@testable import Omi_Computer

/// Deterministic stand-in for the main run loop. Both timed behaviours the card
/// has — the 3s dwell and the 60s visible window — go through this, so the
/// tests below assert real timing rules without sleeping for a minute.
@MainActor
private final class ManualScheduler: FirstRealAppCardScheduling {
  private final class Work: FirstRealAppCardScheduledWork {
    var isCancelled = false
    @MainActor func cancel() { isCancelled = true }
  }

  private var pending: [(delay: TimeInterval, work: Work, body: @MainActor () -> Void)] = []

  func schedule(
    after delay: TimeInterval,
    _ work: @escaping @MainActor () -> Void
  ) -> FirstRealAppCardScheduledWork {
    let handle = Work()
    pending.append((delay, handle, work))
    return handle
  }

  var pendingDelays: [TimeInterval] { pending.filter { !$0.work.isCancelled }.map(\.delay) }

  /// Runs every live item scheduled for exactly `delay`.
  func fire(after delay: TimeInterval) {
    let due = pending.filter { $0.delay == delay && !$0.work.isCancelled }
    pending.removeAll { $0.delay == delay }
    for item in due { item.body() }
  }
}

/// The whole first-real-app card lifecycle, driven through the real coordinator
/// against an injected clock, an injected `UserDefaults` suite, and recorded
/// effects. Nothing here reads process-wide state, and nothing waits.
@MainActor
final class FirstRealAppCardCoordinatorTests: XCTestCase {
  private let realApp = (bundleIdentifier: "com.apple.Safari", appName: "Safari")
  private let omiBundleID = "com.omi.computer-macos"

  private var suiteName = ""
  private var defaults = UserDefaults.standard
  private var scheduler = ManualScheduler()
  private var presented: [(ownerID: String, title: String, body: String)] = []
  private var dismissals: [NotificationDismissalKind] = []
  private var openedChatPrompts: [String] = []
  private var telemetry: [(String, [String: Any])] = []
  private var pttStart: (@MainActor () -> Void)?
  private var warmCaptureRequests = 0
  private var pttObservationStopped = false
  private var frontmost: (bundleIdentifier: String?, localizedName: String?) = (nil, nil)
  private var isOnboardingComplete = true
  private var ownerID: String? = "owner-1"
  private var pttChordTokens = ["⌃", "⌥"]

  // Async hooks without `super` calls: awaiting the pinned SDK's nonisolated
  // super.setUp()/tearDown() would transfer the non-Sendable test instance
  // across actors (see scripts/check-main-actor-xctest-hooks.py).
  override func setUp() async throws {
    suiteName = "FirstRealAppCardCoordinatorTests.\(UUID().uuidString)"
    defaults = UserDefaults(suiteName: suiteName) ?? .standard
    scheduler = ManualScheduler()
    presented = []
    dismissals = []
    openedChatPrompts = []
    telemetry = []
    pttStart = nil
    warmCaptureRequests = 0
    pttObservationStopped = false
    frontmost = (realApp.bundleIdentifier, realApp.appName)
    isOnboardingComplete = true
    ownerID = "owner-1"
    pttChordTokens = ["⌃", "⌥"]
    FirstRealAppCardTelemetry.captureForTests = { [weak self] event, properties in
      self?.telemetry.append((event, properties))
    }
  }

  override func tearDown() async throws {
    FirstRealAppCardTelemetry.captureForTests = nil
    UserDefaults.standard.removePersistentDomain(forName: suiteName)
  }

  private func makeCoordinator() -> FirstRealAppCardCoordinator {
    FirstRealAppCardCoordinator(
      defaults: defaults,
      environment: { [weak self] in
        FirstRealAppCardCoordinator.Environment(
          isOnboardingComplete: self?.isOnboardingComplete ?? true,
          ownerID: self?.ownerID,
          pttChordTokens: self?.pttChordTokens ?? [],
          omiBundleIdentifier: self?.omiBundleID
        )
      },
      frontmostApp: { [weak self] in self?.frontmost ?? (nil, nil) },
      presenter: { [weak self] ownerID, title, body in
        self?.presented.append((ownerID, title, body))
      },
      dismisser: { [weak self] kind in self?.dismissals.append(kind) },
      pttObserver: { [weak self] onStart in
        self?.pttStart = onStart
        return { self?.pttObservationStopped = true }
      },
      warmCapture: { [weak self] in self?.warmCaptureRequests += 1 },
      openChat: { [weak self] prompt in self?.openedChatPrompts.append(prompt) },
      scheduler: scheduler
    )
  }

  /// Activate a real app and let the dwell elapse.
  private func activateRealApp(on coordinator: FirstRealAppCardCoordinator) {
    coordinator.handleActivation(
      bundleIdentifier: realApp.bundleIdentifier, appName: realApp.appName)
    scheduler.fire(after: FirstRealAppCardPolicy.requiredDwell)
  }

  private var telemetryPhases: [String] {
    telemetry.filter { $0.0 == FirstRealAppCardTelemetry.eventName }
      .compactMap { $0.1["phase"] as? String }
  }

  // MARK: - The one-shot

  func testFreshInstallFiresOnceOnTheFirstRealApp() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()

    // Onboarding finishes, then the user opens something real.
    isOnboardingComplete = true
    coordinator.beginObservingActivationsIfReady()
    activateRealApp(on: coordinator)

    XCTAssertEqual(presented.count, 1)
    XCTAssertEqual(presented.first?.ownerID, "owner-1")
    XCTAssertEqual(presented.first?.title, "I can see Safari")
    XCTAssertEqual(telemetryPhases, ["shown"])
  }

  /// The card tells the user to hold ⌥. On a fresh install that press is the one
  /// measured failing — `capture_never_operational` — because CoreAudio has not
  /// opened the microphone yet. Showing the card is the moment to have it running.
  func testShowingTheCardAsksPushToTalkToWarmItsCapture() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true
    coordinator.beginObservingActivationsIfReady()

    XCTAssertEqual(warmCaptureRequests, 0)
    activateRealApp(on: coordinator)

    XCTAssertEqual(presented.count, 1)
    XCTAssertEqual(warmCaptureRequests, 1)
  }

  /// A card that is never shown must not open the microphone: the warm capture
  /// is tied to the invitation, not to app switching.
  func testACardThatDoesNotFireNeverWarmsTheCapture() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true
    coordinator.beginObservingActivationsIfReady()

    // The user switches to Omi itself — the card is suppressed.
    frontmost = (omiBundleID, "Omi")
    coordinator.handleActivation(bundleIdentifier: omiBundleID, appName: "Omi")
    scheduler.fire(after: FirstRealAppCardPolicy.requiredDwell)

    XCTAssertEqual(presented.count, 0)
    XCTAssertEqual(warmCaptureRequests, 0)
  }

  func testTheCardNeverFiresTwiceInOneSession() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true
    activateRealApp(on: coordinator)
    coordinator.handleCardDismissed()

    activateRealApp(on: coordinator)

    XCTAssertEqual(presented.count, 1)
  }

  /// The marker is durable, not in-memory: a relaunch reconstructs the
  /// coordinator against the same suite and must still refuse.
  func testAConsumedMarkerSurvivesAFreshCoordinator() {
    isOnboardingComplete = false
    let first = makeCoordinator()
    first.start()
    isOnboardingComplete = true
    activateRealApp(on: first)
    XCTAssertEqual(presented.count, 1)
    first.stop()

    let relaunched = makeCoordinator()
    relaunched.start()
    activateRealApp(on: relaunched)

    XCTAssertEqual(presented.count, 1)
  }

  /// Someone who finished onboarding on an older build is retired at the gate:
  /// the marker is written straight to consumed and no card ever fires.
  func testExistingUserIsRetiredByTheInstallGateWithoutFiring() {
    isOnboardingComplete = true
    let coordinator = makeCoordinator()
    coordinator.start()

    activateRealApp(on: coordinator)

    XCTAssertTrue(presented.isEmpty)
    XCTAssertTrue(telemetryPhases.isEmpty)

    // And it stays retired across a relaunch.
    let relaunched = makeCoordinator()
    relaunched.start()
    activateRealApp(on: relaunched)
    XCTAssertTrue(presented.isEmpty)
  }

  /// A fresh user who quits mid-onboarding is still owed the card. This is what
  /// the recorded `pending` verdict buys: the next launch finds onboarding
  /// complete but a marker already written, so the gate does not mistake them
  /// for an existing user.
  func testAFreshUserWhoQuitsDuringOnboardingStillGetsTheCard() {
    isOnboardingComplete = false
    let first = makeCoordinator()
    first.start()
    first.stop()

    isOnboardingComplete = true
    let relaunched = makeCoordinator()
    relaunched.start()
    activateRealApp(on: relaunched)

    XCTAssertEqual(presented.count, 1)
  }

  // MARK: - What is not a real app

  func testOmiFrontmostNeitherFiresNorConsumes() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true

    frontmost = (omiBundleID, "Omi")
    coordinator.handleActivation(bundleIdentifier: omiBundleID, appName: "Omi")
    scheduler.fire(after: FirstRealAppCardPolicy.requiredDwell)
    XCTAssertTrue(presented.isEmpty)

    // The shot is still unspent.
    frontmost = (realApp.bundleIdentifier, realApp.appName)
    activateRealApp(on: coordinator)
    XCTAssertEqual(presented.count, 1)
  }

  func testExcludedSystemUINeitherFiresNorConsumes() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true

    frontmost = ("com.apple.dock", "Dock")
    coordinator.handleActivation(bundleIdentifier: "com.apple.dock", appName: "Dock")
    scheduler.fire(after: FirstRealAppCardPolicy.requiredDwell)
    XCTAssertTrue(presented.isEmpty)

    frontmost = (realApp.bundleIdentifier, realApp.appName)
    activateRealApp(on: coordinator)
    XCTAssertEqual(presented.count, 1)
  }

  /// ⌘-Tab passes through apps. The card names whatever is in front when the
  /// dwell elapses, so an app the user left in the meantime fires nothing.
  func testAnAppLeftBeforeTheDwellElapsesDoesNotFire() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true

    coordinator.handleActivation(bundleIdentifier: "com.tinyspeck.slackmacgap", appName: "Slack")
    frontmost = (realApp.bundleIdentifier, realApp.appName)
    scheduler.fire(after: FirstRealAppCardPolicy.requiredDwell)

    XCTAssertTrue(presented.isEmpty)
  }

  /// A second activation replaces the first's pending dwell rather than
  /// stacking, so a burst of app switches cannot fire two cards.
  func testASecondActivationReplacesThePendingDwell() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true

    coordinator.handleActivation(bundleIdentifier: "com.tinyspeck.slackmacgap", appName: "Slack")
    coordinator.handleActivation(
      bundleIdentifier: realApp.bundleIdentifier, appName: realApp.appName)
    XCTAssertEqual(
      scheduler.pendingDelays, [FirstRealAppCardPolicy.requiredDwell],
      "only the newest activation should still be armed")

    scheduler.fire(after: FirstRealAppCardPolicy.requiredDwell)
    XCTAssertEqual(presented.count, 1)
  }

  // MARK: - Copy

  func testBodyCarriesTheUsersRealChord() {
    pttChordTokens = ["Right ⌘"]
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true
    activateRealApp(on: coordinator)

    XCTAssertEqual(
      presented.first?.body, "Hold Right ⌘ and ask me anything about it — or tap to type.")
  }

  func testBodyFallsBackToTapOnlyWhenTheChordIsEmpty() {
    pttChordTokens = []
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true
    activateRealApp(on: coordinator)

    XCTAssertEqual(presented.first?.body, "Tap to ask me anything about it.")
  }

  // MARK: - Exits

  private func fireCard() -> FirstRealAppCardCoordinator {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true
    activateRealApp(on: coordinator)
    XCTAssertEqual(presented.count, 1)
    return coordinator
  }

  func testTapOpensTheChatWithTheDraftAndReportsTapped() {
    let coordinator = fireCard()

    coordinator.handleCardTapped(prompt: FirstRealAppCardPolicy.prompt)

    XCTAssertEqual(openedChatPrompts, ["Summarize what's on my screen"])
    XCTAssertEqual(telemetryPhases, ["shown", "tapped"])
    // The bar already took the card down on the tap; retiring must not ask for
    // a second dismissal.
    XCTAssertTrue(dismissals.isEmpty)
    XCTAssertTrue(pttObservationStopped)
  }

  func testCloseButtonReportsDismissed() {
    let coordinator = fireCard()

    coordinator.handleCardDismissed()

    XCTAssertEqual(telemetryPhases, ["shown", "dismissed"])
    XCTAssertTrue(openedChatPrompts.isEmpty)
  }

  func testStartingPushToTalkTakesTheCardDown() {
    let coordinator = fireCard()

    XCTAssertNotNil(pttStart, "the card must watch for the action it asks for")
    pttStart?()

    XCTAssertEqual(telemetryPhases, ["shown", "ptt_after_card"])
    XCTAssertEqual(dismissals, [.user])
    XCTAssertTrue(pttObservationStopped)
    withExtendedLifetime(coordinator) {}
  }

  func testTheCardTimesOutAfterItsVisibleWindow() {
    let coordinator = fireCard()

    XCTAssertTrue(scheduler.pendingDelays.contains(FirstRealAppCardPolicy.visibleDuration))
    scheduler.fire(after: FirstRealAppCardPolicy.visibleDuration)

    XCTAssertEqual(telemetryPhases, ["shown", "timed_out"])
    XCTAssertEqual(dismissals, [.timeout])
    withExtendedLifetime(coordinator) {}
  }

  /// Exactly one terminal phase per card, whichever exit wins the race. A tap
  /// that lands as the timeout fires must not report both.
  func testOnlyOneTerminalPhaseIsReported() {
    let coordinator = fireCard()

    coordinator.handleCardTapped(prompt: FirstRealAppCardPolicy.prompt)
    pttStart?()
    coordinator.handleCardDismissed()
    scheduler.fire(after: FirstRealAppCardPolicy.visibleDuration)

    XCTAssertEqual(telemetryPhases, ["shown", "tapped"])
    XCTAssertTrue(dismissals.isEmpty)
  }

  /// The timeout is cancelled when the user acts, so it can never retire a card
  /// that some other surface put up in the meantime.
  func testActingOnTheCardCancelsItsTimeout() {
    let coordinator = fireCard()

    coordinator.handleCardDismissed()

    XCTAssertFalse(scheduler.pendingDelays.contains(FirstRealAppCardPolicy.visibleDuration))
  }

  // MARK: - Prefill contract

  /// The tap prefills and focuses; it does not send. `MainChatNavigationRequestStore`
  /// is the whole seam — it carries a draft and has no send of its own — so the
  /// contract is that the draft is there to be taken exactly once.
  func testThePrefilledDraftIsHandedOverExactlyOnceAndUnsent() {
    let store = MainChatNavigationRequestStore.shared
    _ = store.consumeDraft()

    store.request(draft: FirstRealAppCardPolicy.prompt)

    XCTAssertTrue(store.isPending)
    XCTAssertEqual(store.consumeDraft(), "Summarize what's on my screen")
    XCTAssertNil(store.consumeDraft(), "a second composer must not re-take the draft")
    XCTAssertTrue(store.consume())
  }

  /// Signed out, the card has no owner to fence delivery to — and must not burn
  /// the install's one shot waiting for one.
  func testSignedOutDoesNotFireOrConsume() {
    isOnboardingComplete = false
    let coordinator = makeCoordinator()
    coordinator.start()
    isOnboardingComplete = true
    ownerID = nil

    activateRealApp(on: coordinator)
    XCTAssertTrue(presented.isEmpty)

    ownerID = "owner-1"
    activateRealApp(on: coordinator)
    XCTAssertEqual(presented.count, 1)
  }
}

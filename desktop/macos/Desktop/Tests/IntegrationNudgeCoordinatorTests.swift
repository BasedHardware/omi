import XCTest

@testable import Omi_Computer

/// The coordinator's job is to turn one recognized window into at most one
/// card, and to spend the integration's budget only when a card actually
/// reached the user.
@MainActor
final class IntegrationNudgeCoordinatorTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_700_000_000)

  /// `IntegrationNudgeCatalogTests` proves every import connector has a catalog
  /// entry with at least one trigger, so a nil here is a catalog bug rather than
  /// a test-setup accident — fail loudly instead of silently skipping.
  private func match(
    _ route: IntegrationNudgeRoute = .importConnector("apple-notes")
  ) throws -> IntegrationNudgeMatcher.Match {
    let entry = try XCTUnwrap(IntegrationNudgeCatalog.entry(for: route))
    return IntegrationNudgeMatcher.Match(entry: entry, trigger: try XCTUnwrap(entry.triggers.first))
  }

  private func makeDefaults() -> UserDefaults {
    let suiteName = "IntegrationNudgeCoordinatorTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      preconditionFailure("could not create a private defaults domain for \(suiteName)")
    }
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    return defaults
  }

  private func makeCoordinator(
    defaults: UserDefaults,
    result: OwnerBoundNotificationPresentationResult,
    presentedCount: Box<Int> = Box(0),
    ownerID: String? = "user-a",
    environment: IntegrationNudgeCoordinator.Environment = .init(
      isFeatureEnabled: true,
      notificationsEnabled: true,
      isOnboardingComplete: true
    )
  ) -> IntegrationNudgeCoordinator {
    IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: defaults, ownerID: ownerID),
      now: { self.now },
      presenter: { _, _ in
        presentedCount.value += 1
        return result
      },
      ownerID: { ownerID },
      environment: { environment }
    )
  }

  func testAnEligibleWindowDeliversExactlyOneCardAndSpendsOneBudget() throws {
    let defaults = makeDefaults()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, result: .presented, presentedCount: presented)

    XCTAssertTrue(coordinator.offer(match: try match(), isConnected: false, dwell: 3))
    XCTAssertEqual(presented.value, 1)

    let store = IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
    XCTAssertEqual(store.state(for: try match().entry.telemetryID).shownCount, 1)
    XCTAssertEqual(store.nudgesInCurrentDay(now: now), 1)
  }

  func testAConnectedIntegrationNeitherPresentsNorSpendsBudget() throws {
    let defaults = makeDefaults()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, result: .presented, presentedCount: presented)

    XCTAssertFalse(coordinator.offer(match: try match(), isConnected: true, dwell: 3))
    XCTAssertEqual(presented.value, 0)
    XCTAssertEqual(
      IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
        .state(for: try match().entry.telemetryID).shownCount,
      0
    )
  }

  /// The defect this guards is the one the screen-capture-reset notice shipped:
  /// a one-shot flag set before the surface accepted the delivery permanently
  /// silenced a notice the user never saw.
  func testARejectedPresentationDoesNotSpendTheBudget() throws {
    let defaults = makeDefaults()
    let coordinator = makeCoordinator(defaults: defaults, result: .rejectedOwnerChange)

    XCTAssertFalse(coordinator.offer(match: try match(), isConnected: false, dwell: 3))
    XCTAssertEqual(
      IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
        .state(for: try match().entry.telemetryID).shownCount,
      0
    )
  }

  /// A queued card is still owed to the user, so it counts.
  func testAQueuedPresentationSpendsTheBudget() throws {
    let defaults = makeDefaults()
    let coordinator = makeCoordinator(defaults: defaults, result: .queued)

    XCTAssertTrue(coordinator.offer(match: try match(), isConnected: false, dwell: 3))
    XCTAssertEqual(
      IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
        .state(for: try match().entry.telemetryID).shownCount,
      1
    )
  }

  func testSignedOutNeverPresents() throws {
    let defaults = makeDefaults()
    let presented = Box(0)
    let coordinator = makeCoordinator(
      defaults: defaults,
      result: .presented,
      presentedCount: presented,
      ownerID: nil
    )

    XCTAssertFalse(coordinator.offer(match: try match(), isConnected: false, dwell: 3))
    XCTAssertEqual(presented.value, 0)
  }

  /// Two integrations recognized inside the global cooldown produce one card,
  /// not two — the case where a user opens Gmail and then Notion.
  func testASecondIntegrationInsideTheGlobalCooldownIsSuppressed() throws {
    let defaults = makeDefaults()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, result: .presented, presentedCount: presented)

    XCTAssertTrue(coordinator.offer(match: try match(), isConnected: false, dwell: 3))

    let second = try match(.exportDestination("notion"))
    XCTAssertFalse(coordinator.offer(match: second, isConnected: false, dwell: 3))
    XCTAssertEqual(presented.value, 1)
  }

  /// Turning integration suggestions off in Settings stops them, and so does
  /// turning off Notifications entirely — the feature bypasses the frequency
  /// slider, so the master toggle is the only global mute it still answers to.
  func testTheSettingsTogglesStopEveryNudge() throws {
    for environment in [
      IntegrationNudgeCoordinator.Environment(
        isFeatureEnabled: false, notificationsEnabled: true, isOnboardingComplete: true),
      IntegrationNudgeCoordinator.Environment(
        isFeatureEnabled: true, notificationsEnabled: false, isOnboardingComplete: true),
    ] {
      let presented = Box(0)
      let coordinator = makeCoordinator(
        defaults: makeDefaults(),
        result: .presented,
        presentedCount: presented,
        environment: environment
      )
      XCTAssertFalse(coordinator.offer(match: try match(), isConnected: false, dwell: 3))
      XCTAssertEqual(presented.value, 0)
    }
  }

  /// Onboarding already asks for connectors; nudging over it is duplicative.
  func testNothingIsOfferedDuringOnboarding() throws {
    let presented = Box(0)
    let coordinator = makeCoordinator(
      defaults: makeDefaults(),
      result: .presented,
      presentedCount: presented,
      environment: .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: false)
    )
    XCTAssertFalse(coordinator.offer(match: try match(), isConnected: false, dwell: 3))
    XCTAssertEqual(presented.value, 0)
  }

  func testShortDwellNeverPresents() throws {
    let defaults = makeDefaults()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, result: .presented, presentedCount: presented)

    XCTAssertFalse(
      coordinator.offer(
        match: try match(),
        isConnected: false,
        dwell: IntegrationNudgePolicy.requiredDwell - 0.5
      )
    )
    XCTAssertEqual(presented.value, 0)
  }

  // MARK: - Identity across awaits

  /// Reading the active window title and inspecting a connector are both slow
  /// enough for the user to switch apps mid-flight. A card that says "Connect
  /// Apple Notes" delivered while the user is now in Slack is worse than no
  /// card, and cancelling the task does not help — cancellation never
  /// interrupts an `await` already in progress.
  ///
  /// These drive the real `evaluate` and move the frontmost app *during* each
  /// await, which is the only way to reach the window the bug lives in.
  func testAnAppSwitchDuringTheWindowTitleLookupCancelsTheOffer() async {
    let presented = Box(0)
    let frontmost = Box("com.apple.Notes")
    let coordinator = makeEvaluatingCoordinator(
      presented: presented,
      frontmost: frontmost,
      onWindowTitleLookup: { frontmost.value = "com.tinyspeck.slackmacgap" }
    )

    await coordinator.evaluate(bundleIdentifier: "com.apple.Notes", appName: "Notes", dwell: 3)

    XCTAssertEqual(presented.value, 0)
  }

  func testAnAppSwitchDuringTheConnectionLookupCancelsTheOffer() async {
    let presented = Box(0)
    let frontmost = Box("com.apple.Notes")
    let coordinator = makeEvaluatingCoordinator(
      presented: presented,
      frontmost: frontmost,
      onConnectionLookup: { frontmost.value = "com.tinyspeck.slackmacgap" }
    )

    await coordinator.evaluate(bundleIdentifier: "com.apple.Notes", appName: "Notes", dwell: 3)

    XCTAssertEqual(presented.value, 0)
  }

  /// A sign-out mid-evaluation must not deliver the previous person's nudge.
  func testAnOwnerChangeDuringLookupCancelsTheOffer() async {
    let presented = Box(0)
    let frontmost = Box("com.apple.Notes")
    let owner = Box<String?>("user-a")
    let coordinator = IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: makeDefaults(), ownerID: "user-a"),
      now: { self.now },
      presenter: { _, _ in
        presented.value += 1
        return .presented
      },
      ownerID: { owner.value },
      environment: { .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: true) },
      frontmostBundleID: { frontmost.value },
      windowTitleProvider: { _, _ in
        owner.value = "user-b"
        return nil
      },
      connectionInspector: { _ in false }
    )

    await coordinator.evaluate(bundleIdentifier: "com.apple.Notes", appName: "Notes", dwell: 3)

    XCTAssertEqual(presented.value, 0)
  }

  /// The same path with nothing changing underneath still delivers, so the
  /// guards above cannot pass by suppressing everything.
  func testAStableWindowStillDelivers() async {
    let presented = Box(0)
    let coordinator = makeEvaluatingCoordinator(
      presented: presented,
      frontmost: Box("com.apple.Notes")
    )

    await coordinator.evaluate(bundleIdentifier: "com.apple.Notes", appName: "Notes", dwell: 3)

    XCTAssertEqual(presented.value, 1)
  }

  private func makeEvaluatingCoordinator(
    presented: Box<Int>,
    frontmost: Box<String>,
    onWindowTitleLookup: @escaping @Sendable () -> Void = {},
    onConnectionLookup: @escaping @Sendable () -> Void = {}
  ) -> IntegrationNudgeCoordinator {
    IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: makeDefaults(), ownerID: "user-a"),
      now: { self.now },
      presenter: { _, _ in
        presented.value += 1
        return .presented
      },
      ownerID: { "user-a" },
      environment: { .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: true) },
      frontmostBundleID: { frontmost.value },
      windowTitleProvider: { _, _ in
        onWindowTitleLookup()
        return nil
      },
      connectionInspector: { _ in
        onConnectionLookup()
        return false
      }
    )
  }

  /// A mutable counter usable from the `@Sendable` presenter closure.
  final class Box<T>: @unchecked Sendable {
    var value: T
    init(_ value: T) { self.value = value }
  }
}

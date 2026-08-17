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
      presenter: { _, _, onPresented in
        presentedCount.value += 1
        onPresented()
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

    XCTAssertEqual(coordinator.offer(match: try match(), isConnected: false), .delivered)
    XCTAssertEqual(presented.value, 1)

    let store = IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
    XCTAssertEqual(store.state(for: try match().entry.telemetryID).shownCount, 1)
    XCTAssertEqual(store.nudgesInCurrentDay(now: now), 1)
  }

  func testAConnectedIntegrationNeitherPresentsNorSpendsBudget() throws {
    let defaults = makeDefaults()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, result: .presented, presentedCount: presented)

    XCTAssertEqual(
      coordinator.offer(match: try match(), isConnected: true),
      .settled(.alreadyConnected))
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
    let coordinator = IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: defaults, ownerID: "user-a"),
      now: { self.now },
      presenter: { _, _, _ in .rejectedOwnerChange },
      ownerID: { "user-a" },
      environment: { .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: true) }
    )

    XCTAssertNotEqual(coordinator.offer(match: try match(), isConnected: false), .delivered)
    XCTAssertEqual(
      IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
        .state(for: try match().entry.telemetryID).shownCount,
      0
    )
  }

  /// A queued card has been admitted to a queue, not shown. Spending the budget
  /// on admission would burn one of the integration's three lifetime offers on a
  /// card that may never reach the screen — so the budget is spent from the
  /// bar's presentation callback instead.
  func testAQueuedCardThatIsNeverPresentedDoesNotSpendTheBudget() throws {
    let defaults = makeDefaults()
    let coordinator = IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: defaults, ownerID: "user-a"),
      now: { self.now },
      presenter: { _, _, _ in .queued },
      ownerID: { "user-a" },
      environment: { .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: true) }
    )

    _ = coordinator.offer(match: try match(), isConnected: false)

    XCTAssertEqual(
      IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
        .state(for: try match().entry.telemetryID).shownCount,
      0
    )
  }

  /// The same queued card, once the bar actually presents it, does spend it.
  func testAQueuedCardSpendsTheBudgetWhenItReachesTheScreen() throws {
    let defaults = makeDefaults()
    let present = Box<(@MainActor () -> Void)?>(nil)
    let coordinator = IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: defaults, ownerID: "user-a"),
      now: { self.now },
      presenter: { _, _, onPresented in
        present.value = onPresented
        return .queued
      },
      ownerID: { "user-a" },
      environment: { .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: true) }
    )

    _ = coordinator.offer(match: try match(), isConnected: false)
    present.value?()

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

    XCTAssertNotEqual(coordinator.offer(match: try match(), isConnected: false), .delivered)
    XCTAssertEqual(presented.value, 0)
  }

  /// Two integrations recognized inside the global cooldown produce one card,
  /// not two — the case where a user opens Gmail and then Notion.
  func testASecondIntegrationInsideTheGlobalCooldownIsSuppressed() throws {
    let defaults = makeDefaults()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, result: .presented, presentedCount: presented)

    XCTAssertEqual(coordinator.offer(match: try match(), isConnected: false), .delivered)

    let second = try match(.exportDestination("notion"))
    XCTAssertEqual(
      coordinator.offer(match: second, isConnected: false),
      .settled(.globalCooldown))
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
      XCTAssertNotEqual(coordinator.offer(match: try match(), isConnected: false), .delivered)
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
    XCTAssertNotEqual(coordinator.offer(match: try match(), isConnected: false), .delivered)
    XCTAssertEqual(presented.value, 0)
  }

  // MARK: - Feature off means no work at all

  /// Switched off must mean no Accessibility window-title read, no connector
  /// inspection, and no telemetry — not "do all the work and discard it". The
  /// title read is the privacy-sensitive half, so the assertion is that the
  /// provider is never called at all.
  func testFeatureOffDoesNoWindowInspection() async {
    for environment in [
      IntegrationNudgeCoordinator.Environment(
        isFeatureEnabled: false, notificationsEnabled: true, isOnboardingComplete: true),
      IntegrationNudgeCoordinator.Environment(
        isFeatureEnabled: true, notificationsEnabled: false, isOnboardingComplete: true),
    ] {
      let titleReads = Box(0)
      let connectionChecks = Box(0)
      let presented = Box(0)
      let coordinator = IntegrationNudgeCoordinator(
        store: IntegrationNudgeStore(defaults: makeDefaults(), ownerID: "user-a"),
        now: { self.now },
        presenter: { _, _, _ in
          presented.value += 1
          return .presented
        },
        ownerID: { "user-a" },
        environment: { environment },
        frontmostBundleID: { "com.google.Chrome" },
        windowTitleProvider: { _, _ in
          titleReads.value += 1
          return "Inbox — Gmail"
        },
        connectionInspector: { _ in
          connectionChecks.value += 1
          return false
        }
      )

      coordinator.handleActivation(bundleIdentifier: "com.google.Chrome", appName: "Google Chrome")
      // handleActivation short-circuits before scheduling any work, so there is
      // nothing to await — the counters are already final.
      XCTAssertEqual(titleReads.value, 0)
      XCTAssertEqual(connectionChecks.value, 0)
      XCTAssertEqual(presented.value, 0)
    }
  }

  // MARK: - Re-check loop

  /// Once a window has an answer, re-checking re-reads the title and re-emits
  /// the funnel's denominator for a decision already made.
  func testASettledOutcomeStopsTheReCheckLoop() throws {
    XCTAssertFalse(IntegrationNudgeCoordinator.Outcome.delivered.shouldKeepWatching)
    XCTAssertFalse(IntegrationNudgeCoordinator.Outcome.abandoned.shouldKeepWatching)
    XCTAssertFalse(
      IntegrationNudgeCoordinator.Outcome.settled(.connectorCooldown).shouldKeepWatching)
    XCTAssertTrue(IntegrationNudgeCoordinator.Outcome.noMatchYet.shouldKeepWatching)
  }

  /// A browser tab the user has not opened yet is the one case worth watching.
  func testAnUnrecognizedWindowKeepsTheLoopAlive() async {
    let coordinator = IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: makeDefaults(), ownerID: "user-a"),
      now: { self.now },
      presenter: { _, _, _ in .presented },
      ownerID: { "user-a" },
      environment: { .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: true) },
      frontmostBundleID: { "com.google.Chrome" },
      windowTitleProvider: { _, _ in "Some Unrelated Page" },
      connectionInspector: { _ in false }
    )

    let outcome = await coordinator.evaluate(
      bundleIdentifier: "com.google.Chrome", appName: "Google Chrome")

    XCTAssertEqual(outcome, .noMatchYet)
    XCTAssertTrue(outcome.shouldKeepWatching)
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
      presenter: { _, _, onPresented in
        presented.value += 1
        onPresented()
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

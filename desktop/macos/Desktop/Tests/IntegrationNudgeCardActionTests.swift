import XCTest

@testable import Omi_Computer

/// The card offers exactly three answers, and each is a different promise:
/// Connect takes the user to the connector and credits the nudge for the
/// connect that follows, "Not now" goes quiet for a week, "Never" goes quiet
/// for good. The buttons themselves are one-line SwiftUI closures, so what can
/// actually regress is the handler behind each — these drive the real handlers
/// and assert the effect the user was promised, including the effects the
/// *other* two buttons must not have.
@MainActor
final class IntegrationNudgeCardActionTests: XCTestCase {
  private let clock = Box(Date(timeIntervalSince1970: 1_700_000_000))
  private let capturedBox = Box<[(String, [String: Any])]>([])

  override func tearDown() {
    MainActor.assumeIsolated { IntegrationConnectOrigin.reset() }
    super.tearDown()
  }

  // MARK: - Connect

  /// "Connect" must land the user on the real connector sheet — the same one
  /// the Apps tab opens — and claim the connect that follows. Without the
  /// claim, a nudge-sourced connect is indistinguishable from a user who
  /// browsed to the Apps tab, which is the exact comparison this feature
  /// exists to make.
  func testConnectOpensTheConnectorSheetAndClaimsTheConnectThatFollows() async throws {
    startCapturingTelemetry()
    IntegrationConnectOrigin.reset()
    let defaults = makeDefaults()
    let match = try match()
    let coordinator = makeCoordinator(defaults: defaults)

    let navigatedTo = Box<Int?>(nil)
    let observer = NotificationCenter.default.addObserver(
      forName: .navigateToSidebarItem,
      object: nil,
      queue: nil
    ) { notification in
      navigatedTo.value = notification.userInfo?["rawValue"] as? Int
    }
    defer { NotificationCenter.default.removeObserver(observer) }

    // The presentation command is issued one runloop hop later, so the
    // assertion has to wait for that hop. The main queue is serial, so a block
    // enqueued now runs strictly after it — no sleep and no polling.
    let presentationIssued = expectation(description: "connector sheet command issued")
    coordinator.acceptPresentedNudge(
      telemetryID: match.entry.telemetryID, triggerID: match.trigger.id)
    DispatchQueue.main.async { presentationIssued.fulfill() }
    await fulfillment(of: [presentationIssued], timeout: 2)

    XCTAssertEqual(navigatedTo.value, SidebarNavItem.apps.rawValue)

    let command = try XCTUnwrap(DesktopAutomationPresentationCoordinator.shared.activeCommand)
    XCTAssertEqual(command.target, .importConnector("apple-notes"))
    // Resolve our own command so the shared coordinator is left as we found it.
    DesktopAutomationPresentationCoordinator.shared.acknowledgeVisible(
      generation: command.generation, target: command.target)

    XCTAssertEqual(IntegrationConnectOrigin.consumeSurface(for: match.entry.route), .nudge)

    let event = try XCTUnwrap(capturedBox.value.first)
    XCTAssertEqual(event.0, IntegrationNudgeTelemetry.actionedEventName)
    XCTAssertEqual(event.1["action"] as? String, "connect")
    XCTAssertEqual(event.1["trigger_id"] as? String, match.trigger.id)

    // Accepting is not a refusal: it must not spend a nudge, snooze, or opt out.
    let state = store(defaults).state(for: match.entry.telemetryID, now: clock.value)
    XCTAssertEqual(state, IntegrationNudgePolicy.ConnectorState())
  }

  // MARK: - Not now

  /// "Not now" is a week of silence for this integration, not a permanent
  /// refusal — the week has to actually end, or the button quietly means the
  /// same thing as "Never".
  func testNotNowSilencesThisIntegrationForAWeekAndNoLonger() throws {
    startCapturingTelemetry()
    let defaults = makeDefaults()
    let match = try match()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, presentedCount: presented)

    coordinator.snoozePresentedNudge(
      telemetryID: match.entry.telemetryID, triggerID: match.trigger.id)

    XCTAssertEqual(
      store(defaults).state(for: match.entry.telemetryID, now: clock.value).snoozedUntil,
      clock.value.addingTimeInterval(IntegrationNudgePolicy.snoozeDuration)
    )

    clock.value = clock.value.addingTimeInterval(IntegrationNudgePolicy.snoozeDuration - 1)
    XCTAssertEqual(coordinator.offer(match: match, isConnected: false), .settled(.snoozed))
    XCTAssertEqual(presented.value, 0)

    clock.value = clock.value.addingTimeInterval(1)
    XCTAssertEqual(coordinator.offer(match: match, isConnected: false), .delivered)
    XCTAssertEqual(presented.value, 1)

    let event = try XCTUnwrap(capturedBox.value.first)
    XCTAssertEqual(event.0, IntegrationNudgeTelemetry.actionedEventName)
    XCTAssertEqual(event.1["action"] as? String, "not_now")
    XCTAssertEqual(event.1["trigger_id"] as? String, match.trigger.id)
  }

  // MARK: - Never

  /// "Never" is permanent. The failure that matters is it decaying into a
  /// snooze, so this asserts the refusal still holds long after the snooze
  /// window — and every cooldown in the policy — has passed.
  func testNeverStopsThisIntegrationPermanently() throws {
    startCapturingTelemetry()
    let defaults = makeDefaults()
    let match = try match()
    let presented = Box(0)
    let coordinator = makeCoordinator(defaults: defaults, presentedCount: presented)

    coordinator.dismissPresentedNudgeForever(
      telemetryID: match.entry.telemetryID, triggerID: match.trigger.id)

    XCTAssertTrue(store(defaults).state(for: match.entry.telemetryID, now: clock.value).optedOut)
    XCTAssertEqual(coordinator.offer(match: match, isConnected: false), .settled(.optedOut))

    clock.value = clock.value.addingTimeInterval(365 * 24 * 60 * 60)
    XCTAssertEqual(coordinator.offer(match: match, isConnected: false), .settled(.optedOut))
    XCTAssertEqual(presented.value, 0)

    let event = try XCTUnwrap(capturedBox.value.first)
    XCTAssertEqual(event.0, IntegrationNudgeTelemetry.actionedEventName)
    XCTAssertEqual(event.1["action"] as? String, "dismiss_forever")
    XCTAssertEqual(event.1["trigger_id"] as? String, match.trigger.id)
  }

  // MARK: - Fixtures

  /// `IntegrationNudgeCatalogTests` proves every import connector has a catalog
  /// entry with at least one trigger, so a nil here is a catalog bug rather
  /// than a test-setup accident — fail loudly instead of silently skipping.
  private func match(
    _ route: IntegrationNudgeRoute = .importConnector("apple-notes")
  ) throws -> IntegrationNudgeMatcher.Match {
    let entry = try XCTUnwrap(IntegrationNudgeCatalog.entry(for: route))
    return IntegrationNudgeMatcher.Match(entry: entry, trigger: try XCTUnwrap(entry.triggers.first))
  }

  private func makeDefaults() -> UserDefaults {
    let suiteName = "IntegrationNudgeCardActionTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      preconditionFailure("could not create a private defaults domain for \(suiteName)")
    }
    addTeardownBlock { defaults.removePersistentDomain(forName: suiteName) }
    return defaults
  }

  private func store(_ defaults: UserDefaults) -> IntegrationNudgeStore {
    IntegrationNudgeStore(defaults: defaults, ownerID: "user-a")
  }

  private func makeCoordinator(
    defaults: UserDefaults,
    presentedCount: Box<Int> = Box(0)
  ) -> IntegrationNudgeCoordinator {
    let clock = self.clock
    return IntegrationNudgeCoordinator(
      store: IntegrationNudgeStore(defaults: defaults, ownerID: "user-a"),
      now: { clock.value },
      presenter: { _, _, onPresented, _ in
        presentedCount.value += 1
        onPresented()
        return .presented
      },
      ownerID: { "user-a" },
      environment: {
        .init(isFeatureEnabled: true, notificationsEnabled: true, isOnboardingComplete: true)
      }
    )
  }

  /// Observes the real `AnalyticsManager` emitters through the scoped capture
  /// seam the nudge telemetry tests already use, so "the user answered the
  /// card" is asserted on the event that actually ships rather than on a
  /// payload builder called directly.
  private func startCapturingTelemetry() {
    let box = capturedBox
    box.value = []
    AnalyticsManager.shared.setIntegrationNudgeTelemetryCaptureForTests { event, properties in
      box.value.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run {
        AnalyticsManager.shared.setIntegrationNudgeTelemetryCaptureForTests(nil)
      }
    }
  }

  /// A mutable value usable from the `@Sendable` presenter and observer closures.
  final class Box<T>: @unchecked Sendable {
    var value: T
    init(_ value: T) { self.value = value }
  }
}

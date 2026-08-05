import Combine
import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the background refresh scheduler.
///
/// Every test drives `tick()` directly and never calls `start()`, so no `Timer`
/// is ever installed and no test depends on wall time: the clock, the backoff
/// jitter, the environment probe, and the fallback reporter are all injected.
@MainActor
final class ConnectorRefreshSchedulerTests: XCTestCase {
  private let epoch = Date(timeIntervalSince1970: 1_700_000_000)
  private let hour: TimeInterval = 3600
  private let day: TimeInterval = 24 * 3600

  // MARK: - Doubles

  /// Deterministic, injectable clock. A reference type so the closure handed to
  /// the scheduler observes advances made by the test.
  @MainActor
  private final class TestClock {
    private(set) var current: Date

    init(_ start: Date) { current = start }

    func advance(_ interval: TimeInterval) { current = current.addingTimeInterval(interval) }
  }

  @MainActor
  private final class FallbackRecorder {
    struct Event: Equatable {
      let connectorID: String
      let destination: String
      let reason: String
      let outcome: String
    }

    private(set) var events: [Event] = []

    func reporter() -> ConnectorRefreshFallbackReporter {
      { [self] connectorID, destination, reason, outcome in
        events.append(
          Event(
            connectorID: connectorID,
            destination: destination,
            reason: reason,
            outcome: outcome.rawValue
          )
        )
      }
    }
  }

  @MainActor
  private final class FakeRefreshableConnector: BackgroundRefreshableConnector {
    let connectorID: String
    var declaredUnattendedSupport: Bool
    var refreshInterval: TimeInterval
    var nextResult: ConnectorRefreshResult
    /// When true, `refresh(progress:)` suspends until `release()` is called, so
    /// a test can hold a run in flight without sleeping.
    var blocksUntilReleased = false
    /// When set, the fake reports this title through the sink it was handed.
    /// Proves the scheduler passes the *live* runner sink rather than dropping
    /// it — a sink can only be built by the runner that owns the run.
    var progressTitleToReport: String?

    private(set) var refreshCallCount = 0
    private var gate: CheckedContinuation<Void, Never>?
    private var startWaiter: CheckedContinuation<Void, Never>?
    private var didStart = false

    var supportsUnattendedRefresh: Bool { declaredUnattendedSupport }

    init(
      connectorID: String,
      supportsUnattendedRefresh: Bool = true,
      refreshInterval: TimeInterval = 6 * 3600,
      result: ConnectorRefreshResult = .success(ConnectorRefreshMetrics(sourceCount: 1, memoryCount: 1, newItems: 1))
    ) {
      self.connectorID = connectorID
      self.declaredUnattendedSupport = supportsUnattendedRefresh
      self.refreshInterval = refreshInterval
      self.nextResult = result
    }

    func refresh(progress: ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
      refreshCallCount += 1
      didStart = true
      if let progressTitleToReport {
        progress.update(title: progressTitleToReport, detail: "Checking for new items.")
      }
      startWaiter?.resume()
      startWaiter = nil
      if blocksUntilReleased {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
          gate = continuation
        }
      }
      return nextResult
    }

    /// Suspends until `refresh()` has begun. Signal-driven, not time-driven.
    func waitUntilRefreshStarted() async {
      if didStart { return }
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        startWaiter = continuation
      }
    }

    func release() {
      gate?.resume()
      gate = nil
    }
  }

  // MARK: - Fixtures

  private func makeDefaults() -> (defaults: UserDefaults, suiteName: String) {
    let suiteName = "ConnectorRefreshSchedulerTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("could not create isolated UserDefaults suite")
      return (UserDefaults.standard, suiteName)
    }
    return (defaults, suiteName)
  }

  private func makeScheduler(
    defaults: UserDefaults,
    clock: TestClock,
    connectors: [any BackgroundRefreshableConnector],
    statusStore: ImportConnectorStatusStore,
    fallbacks: FallbackRecorder,
    environment: ConnectorRefreshEnvironment = ConnectorRefreshEnvironment(isSignedIn: true),
    stateStore: ConnectorRefreshStateStore? = nil
  ) -> ConnectorRefreshScheduler {
    let scheduler = ConnectorRefreshScheduler(
      defaults: defaults,
      stateStore: stateStore ?? ConnectorRefreshStateStore(defaults: defaults, sessionUserID: "test-user"),
      now: { clock.current },
      jitter: { 0 },
      environmentProbe: { environment },
      recordFallback: fallbacks.reporter()
    )
    scheduler.configure(statusStoreProvider: { statusStore }, connectors: connectors)
    return scheduler
  }

  private func connectedStatusStore(
    defaults: UserDefaults,
    connectorIDs: [String],
    sourceCount: Int = 5,
    syncedAt: Date
  ) -> ImportConnectorStatusStore {
    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")
    for connectorID in connectorIDs {
      store.markSynced(connectorID: connectorID, sourceCount: sourceCount, syncedAt: syncedAt)
    }
    return store
  }

  private func snapshot(_ store: ImportConnectorStatusStore, _ connectorID: String) -> ImportConnectorStatusStore
    .Snapshot?
  {
    guard let connector = ImportConnector.all.first(where: { $0.id == connectorID }) else { return nil }
    return store.snapshot(for: connector)
  }

  // MARK: - Dispatch

  func testTickRefreshesOnlyEligibleConnectors() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    // Ineligible connectors can raise a consent dialog; 34 days stale must not
    // change that.
    let ineligible = FakeRefreshableConnector(connectorID: "calendar", supportsUnattendedRefresh: false)
    let eligible = FakeRefreshableConnector(connectorID: "apple-notes", supportsUnattendedRefresh: true)
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar", "apple-notes"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [ineligible, eligible],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    let decisions = await scheduler.tick()

    XCTAssertEqual(decisions["calendar"], .skip(.notEligibleForUnattendedRefresh))
    XCTAssertEqual(decisions["apple-notes"], .refresh)
    XCTAssertEqual(ineligible.refreshCallCount, 0, "an ineligible connector must never run in the background")
    XCTAssertEqual(eligible.refreshCallCount, 1)
  }

  func testTickRefreshesAtMostOneConnectorPerTick() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    let connectors = ["calendar", "apple-notes", "local-files"].map {
      FakeRefreshableConnector(connectorID: $0, supportsUnattendedRefresh: true)
    }
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar", "apple-notes", "local-files"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: connectors,
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    _ = await scheduler.tick()

    XCTAssertEqual(
      connectors.reduce(0) { $0 + $1.refreshCallCount },
      1,
      "at most one connector may import per tick — this is the anti-thundering-herd rule"
    )
  }

  func testSecondTickDoesNotOverlapAnInFlightRefresh() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(connectorID: "apple-notes", supportsUnattendedRefresh: true)
    connector.blocksUntilReleased = true
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["apple-notes"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    let firstTick = Task { await scheduler.tick() }
    await connector.waitUntilRefreshStarted()

    let secondTick = await scheduler.tick()
    XCTAssertTrue(secondTick.isEmpty, "a tick that lands during an in-flight tick must be a no-op")
    XCTAssertEqual(connector.refreshCallCount, 1)

    connector.release()
    _ = await firstTick.value
    XCTAssertEqual(connector.refreshCallCount, 1)
  }

  // MARK: - Runner integration

  func testRefreshReceivesTheLiveRunnerProgressSink() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(connectorID: "apple-notes", supportsUnattendedRefresh: true)
    connector.progressTitleToReport = "Importing Apple Notes"
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["apple-notes"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    _ = await scheduler.tick()

    // The sink can only be built by the runner that owns the run, so a title
    // landing on that run's state is proof the scheduler threaded the real sink
    // through instead of discarding it — the whole reason the import operations
    // were unreachable from an adapter.
    XCTAssertEqual(
      ConnectorImportRunner.shared.runs["apple-notes"]?.progressTitle,
      "Importing Apple Notes"
    )
  }

  func testBackgroundRunsReportTheBackgroundSurfaceNotTheConnectFunnel() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    var captured: [(name: String, properties: [String: Any])] = []
    AnalyticsManager.shared.setIntegrationConnectTelemetryCaptureForTests { name, properties in
      captured.append((name, properties))
    }
    defer { AnalyticsManager.shared.setIntegrationConnectTelemetryCaptureForTests(nil) }

    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()
    let connector = FakeRefreshableConnector(connectorID: "apple-notes", supportsUnattendedRefresh: true)
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["apple-notes"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    _ = await scheduler.tick()

    // Unattended ticks must not land in the user-initiated connect funnel: every
    // existing `surface == "apps"` query would silently change meaning.
    XCTAssertEqual(captured.map(\.name), ["Integration Connect Attempted", "Integration Connect Succeeded"])
    XCTAssertEqual(captured.compactMap { $0.properties["surface"] as? String }, ["background", "background"])
  }

  // MARK: - Truthful status

  func testSuccessWritesTruthfulLastSyncedToStatusStore() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    // The status store renders relative timestamps against the real clock, so
    // this test anchors its injected clock to the present instead of an epoch.
    let clock = TestClock(Date())
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(
      connectorID: "calendar",
      supportsUnattendedRefresh: true,
      refreshInterval: hour,
      result: .success(ConnectorRefreshMetrics(sourceCount: 42, memoryCount: 7, newItems: 3))
    )
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar"],
      syncedAt: clock.current.addingTimeInterval(-40 * day)
    )
    let staleSecondary = snapshot(statusStore, "calendar")?.secondaryText
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    _ = await scheduler.tick()

    let refreshed = snapshot(statusStore, "calendar")
    XCTAssertEqual(refreshed?.isConnected, true)
    XCTAssertEqual(refreshed?.primaryText, "42 events • 7 memories")
    XCTAssertNotNil(staleSecondary)
    XCTAssertNotEqual(
      refreshed?.secondaryText,
      staleSecondary,
      "a successful background refresh must advance the visible synced timestamp"
    )
  }

  func testFailureDoesNotAdvanceLastSynced() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(Date())
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(
      connectorID: "calendar",
      supportsUnattendedRefresh: true,
      refreshInterval: hour,
      result: .transientFailure(reason: .network)
    )
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar"],
      syncedAt: clock.current.addingTimeInterval(-40 * day)
    )
    let before = snapshot(statusStore, "calendar")
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    _ = await scheduler.tick()

    let after = snapshot(statusStore, "calendar")
    XCTAssertEqual(connector.refreshCallCount, 1)
    XCTAssertEqual(after?.primaryText, before?.primaryText)
    XCTAssertEqual(
      after?.secondaryText,
      before?.secondaryText,
      "a failed refresh must never move the synced timestamp — that latch is the bug being fixed"
    )
  }

  // MARK: - Attention and re-arm

  func testNeedsUserActionSurfacesAttentionToUI() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(
      connectorID: "calendar",
      supportsUnattendedRefresh: true,
      result: .needsUserAction(reason: .sessionExpired)
    )
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    _ = await scheduler.tick()

    XCTAssertEqual(scheduler.attention["calendar"]?.reason, .sessionExpired)
    XCTAssertEqual(scheduler.attention["calendar"]?.since, epoch)
    XCTAssertEqual(scheduler.attention["calendar"]?.message, "Google Calendar needs to be reconnected.")
    XCTAssertEqual(
      fallbacks.events,
      [.init(connectorID: "calendar", destination: "manual_only", reason: "auth", outcome: "exhausted")])
  }

  func testUserReconnectClearsNeedsAttentionAndReArms() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(
      connectorID: "calendar",
      supportsUnattendedRefresh: true,
      result: .needsUserAction(reason: .sessionExpired)
    )
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    _ = await scheduler.tick()
    XCTAssertNotNil(scheduler.attention["calendar"])

    clock.advance(7 * day)
    let parkedDecisions = await scheduler.tick()
    XCTAssertEqual(parkedDecisions["calendar"], .skip(.needsUserAction))
    XCTAssertEqual(connector.refreshCallCount, 1, "a parked connector must not retry on its own")

    // The user reconnects from the Apps tab: no app restart may be required.
    scheduler.handleUserInitiatedSync(connectorID: "calendar")
    XCTAssertNil(scheduler.attention["calendar"])

    connector.nextResult = .success(ConnectorRefreshMetrics(sourceCount: 3, memoryCount: 1, newItems: 1))
    clock.advance(7 * hour)
    let reArmedDecisions = await scheduler.tick()
    XCTAssertEqual(reArmedDecisions["calendar"], .refresh)
    XCTAssertEqual(connector.refreshCallCount, 2)
    XCTAssertNil(scheduler.attention["calendar"])
  }

  // MARK: - Persistence

  func testStatePersistsAcrossSchedulerRecreation() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["apple-notes"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )

    let firstConnector = FakeRefreshableConnector(connectorID: "apple-notes", supportsUnattendedRefresh: true)
    let firstScheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [firstConnector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )
    _ = await firstScheduler.tick()
    XCTAssertEqual(firstConnector.refreshCallCount, 1)

    // Simulates a relaunch: a brand new scheduler and state store over the same
    // persisted defaults must honor the interval that was just satisfied.
    let secondConnector = FakeRefreshableConnector(connectorID: "apple-notes", supportsUnattendedRefresh: true)
    let secondScheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [secondConnector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    let relaunchDecisions = await secondScheduler.tick()
    XCTAssertEqual(relaunchDecisions["apple-notes"], .skip(.intervalNotElapsed))
    XCTAssertEqual(secondConnector.refreshCallCount, 0)
  }

  // MARK: - Fallback telemetry

  func testFallbackTelemetryEmittedOnceOnExhaustion() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(
      connectorID: "calendar",
      supportsUnattendedRefresh: true,
      refreshInterval: 60,
      result: .transientFailure(reason: .network)
    )
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    // Five transient failures, each after the previous backoff has elapsed.
    for _ in 0..<ConnectorRefreshPolicy.maxConsecutiveFailures {
      _ = await scheduler.tick()
      clock.advance(3 * hour)
    }

    XCTAssertEqual(connector.refreshCallCount, ConnectorRefreshPolicy.maxConsecutiveFailures)
    XCTAssertEqual(
      fallbacks.events,
      [.init(connectorID: "calendar", destination: "manual_only", reason: "other", outcome: "exhausted")],
      "exhaustion reports exactly once — a single transient failure must report nothing"
    )
    XCTAssertNotNil(scheduler.attention["calendar"])
  }

  func testFallbackTelemetryDedupedWithin24Hours() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    let clock = TestClock(epoch)
    let fallbacks = FallbackRecorder()

    let connector = FakeRefreshableConnector(
      connectorID: "calendar",
      supportsUnattendedRefresh: true,
      refreshInterval: 60,
      result: .transientFailure(reason: .network)
    )
    let statusStore = connectedStatusStore(
      defaults: defaults,
      connectorIDs: ["calendar"],
      syncedAt: epoch.addingTimeInterval(-34 * day)
    )
    let scheduler = makeScheduler(
      defaults: defaults,
      clock: clock,
      connectors: [connector],
      statusStore: statusStore,
      fallbacks: fallbacks
    )

    for _ in 0..<ConnectorRefreshPolicy.maxConsecutiveFailures {
      _ = await scheduler.tick()
      clock.advance(3 * hour)
    }
    XCTAssertEqual(fallbacks.events.count, 1)

    // Re-arm and exhaust again, still inside the 24h reporting window.
    scheduler.handleUserInitiatedSync(connectorID: "calendar")
    for _ in 0..<ConnectorRefreshPolicy.maxConsecutiveFailures {
      clock.advance(3 * hour)
      _ = await scheduler.tick()
    }

    XCTAssertEqual(connector.refreshCallCount, 2 * ConnectorRefreshPolicy.maxConsecutiveFailures)
    XCTAssertEqual(
      fallbacks.events.count,
      1,
      "a second exhaustion inside the 24h cooldown must not emit a second fallback"
    )
  }
}

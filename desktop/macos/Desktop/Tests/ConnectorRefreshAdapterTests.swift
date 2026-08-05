import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the three background refresh adapters.
///
/// The adapters are thin by design, so what these tests pin is the wiring that
/// was actually broken: each adapter forwards the runner's progress sink into
/// its import operation, and eligibility is decided by declared/recorded facts
/// rather than by a connector id.
///
/// No test calls a real `ConnectorImportOperations` entry point — those read
/// Apple Events, browser cookies, and user folders. The operation is injected,
/// and the sink is obtained from a real `ConnectorImportRunner`, whose
/// `ProgressSink` storage is `fileprivate` and therefore impossible to forge
/// anywhere else. That constraint is exactly why the sink is threaded through
/// `BackgroundRefreshableConnector.refresh(progress:)`.
@MainActor
final class ConnectorRefreshAdapterTests: XCTestCase {
  private let successMetrics = ConnectorRefreshMetrics(sourceCount: 4, memoryCount: 2, newItems: 1)

  // MARK: - Doubles

  /// Stands in for the connector's real import operation and records that it
  /// ran, plus reports progress through whatever sink it was handed.
  @MainActor
  private final class ImportOperationSpy {
    private(set) var invocationCount = 0
    var stubbedResult: ConnectorRefreshResult = .success(ConnectorRefreshMetrics())
    /// Reported through the injected sink so a test can prove the sink belongs
    /// to the live run rather than being an inert value.
    var progressTitle = "Importing"

    func operation() -> @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorRefreshResult {
      { [self] progress in
        invocationCount += 1
        progress.update(title: progressTitle, detail: "Checking for new items.")
        return stubbedResult
      }
    }
  }

  // MARK: - Fixtures

  /// Runs `body` inside a real runner-owned run so it receives a genuine
  /// `ProgressSink`, then returns the runner for assertions on the run state
  /// that sink was supposed to drive.
  private func withRunnerSink(
    connectorID: String,
    _ body: @escaping @MainActor (ConnectorImportRunner.ProgressSink) async -> Void
  ) async -> ConnectorImportRunner {
    let runner = ConnectorImportRunner()
    let task = runner.start(
      connectorID: connectorID,
      progressTitle: "Syncing",
      progressDetail: "Checking for new items."
    ) { sink in
      await body(sink)
      return .success(message: "done")
    }
    await task?.value
    return runner
  }

  private func isolatedDefaults() -> (defaults: UserDefaults, suiteName: String)? {
    let suiteName = "ConnectorRefreshAdapterTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("could not create isolated UserDefaults suite")
      return nil
    }
    return (defaults, suiteName)
  }

  // MARK: - Sink threading

  func testAppleNotesAdapterForwardsTheRunnerSinkAndItsResult() async {
    let spy = ImportOperationSpy()
    spy.stubbedResult = .success(successMetrics)
    spy.progressTitle = "Importing Apple Notes"
    let adapter = AppleNotesBackgroundRefreshAdapter(performRefresh: spy.operation())

    var result: ConnectorRefreshResult?
    let runner = await withRunnerSink(connectorID: "apple-notes") { sink in
      result = await adapter.refresh(progress: sink)
    }

    XCTAssertEqual(spy.invocationCount, 1, "the adapter must call its import operation, not a stub")
    XCTAssertEqual(result, .success(successMetrics))
    XCTAssertEqual(
      runner.runs["apple-notes"]?.progressTitle,
      "Importing Apple Notes",
      "progress must reach the run that owns the sink — a discarded sink is the bug this wiring fixes"
    )
  }

  func testCalendarAdapterForwardsTheRunnerSinkAndItsResult() async {
    let spy = ImportOperationSpy()
    spy.stubbedResult = .needsUserAction(reason: .decryptFailed)
    spy.progressTitle = "Importing calendar events"
    let adapter = CalendarBackgroundRefreshAdapter(performRefresh: spy.operation())

    var result: ConnectorRefreshResult?
    let runner = await withRunnerSink(connectorID: "calendar") { sink in
      result = await adapter.refresh(progress: sink)
    }

    XCTAssertEqual(spy.invocationCount, 1)
    XCTAssertEqual(result, .needsUserAction(reason: .decryptFailed))
    XCTAssertEqual(runner.runs["calendar"]?.progressTitle, "Importing calendar events")
  }

  func testLocalFilesAdapterForwardsTheRunnerSinkAndItsResult() async {
    let spy = ImportOperationSpy()
    spy.stubbedResult = .success(successMetrics)
    spy.progressTitle = "Reindexing local files"
    let adapter = LocalFilesBackgroundRefreshAdapter(performRefresh: spy.operation())

    var result: ConnectorRefreshResult?
    let runner = await withRunnerSink(connectorID: "local-files") { sink in
      result = await adapter.refresh(progress: sink)
    }

    XCTAssertEqual(spy.invocationCount, 1)
    XCTAssertEqual(result, .success(successMetrics))
    XCTAssertEqual(runner.runs["local-files"]?.progressTitle, "Reindexing local files")
  }

  // MARK: - Eligibility

  func testCalendarIsIneligibleForUnattendedRefreshByDefault() {
    // Calendar still reaches Google by decrypting the browser's Safe Storage
    // Keychain item. The unattended path suppresses the consent sheet rather
    // than answering it, so an eligible Calendar would park itself on a
    // decrypt failure the user cannot see coming. Flips with server-side OAuth
    // (https://github.com/BasedHardware/omi/issues/10459).
    XCTAssertFalse(CalendarBackgroundRefreshAdapter().supportsUnattendedRefresh)
  }

  func testAppleNotesIsEligibleForUnattendedRefreshByDefault() {
    XCTAssertTrue(AppleNotesBackgroundRefreshAdapter().supportsUnattendedRefresh)
  }

  func testLocalFilesBecomesEligibleOnlyWhileAProvenGrantIsRecorded() {
    guard let testDefaults = isolatedDefaults() else { return }
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    let stateStore = ConnectorRefreshStateStore(defaults: defaults, sessionUserID: "test-user")
    let adapter = LocalFilesBackgroundRefreshAdapter(stateStore: stateStore)

    XCTAssertFalse(
      adapter.supportsUnattendedRefresh,
      "the first scan of ~/Downloads, ~/Documents, and ~/Desktop raises TCC dialogs — never unattended"
    )

    // What a user-initiated scan reporting no denied user folders records.
    stateStore.recordUnattendedGrant(proven: true, for: LocalFilesBackgroundRefreshAdapter.connectorIdentifier)
    XCTAssertTrue(adapter.supportsUnattendedRefresh)

    // A folder revoked in System Settings must take it back out of rotation on
    // the very next evaluation, with no relaunch.
    stateStore.recordUnattendedGrant(proven: false, for: LocalFilesBackgroundRefreshAdapter.connectorIdentifier)
    XCTAssertFalse(adapter.supportsUnattendedRefresh)
  }
}

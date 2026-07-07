import XCTest

@testable import Omi_Computer

@MainActor
final class ConnectorImportRunnerTests: XCTestCase {
  /// Deterministic gate so tests control when an operation completes —
  /// no sleeps, no wall-clock dependence.
  private actor Gate {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
      if isOpen { return }
      await withCheckedContinuation { waiters.append($0) }
    }

    func open() {
      isOpen = true
      for waiter in waiters {
        waiter.resume()
      }
      waiters.removeAll()
    }
  }

  func testStartPublishesRunningStateAndAppliesProgressUpdates() async {
    let runner = ConnectorImportRunner()
    let sinkReady = Gate()
    let release = Gate()
    var sink: ConnectorImportRunner.ProgressSink?

    let task = runner.start(
      connectorID: "email",
      progressTitle: "Connecting",
      progressDetail: "Starting"
    ) { progress in
      sink = progress
      await sinkReady.open()
      await release.wait()
      return .success(message: "done")
    }

    XCTAssertNotNil(task)
    XCTAssertTrue(runner.isRunning("email"))
    XCTAssertEqual(runner.runs["email"]?.phase, .running)
    XCTAssertEqual(runner.runs["email"]?.progressTitle, "Connecting")
    XCTAssertEqual(runner.runs["email"]?.progressDetail, "Starting")

    await sinkReady.wait()
    sink?.update(title: "Importing", detail: "Halfway")
    XCTAssertEqual(runner.runs["email"]?.progressTitle, "Importing")
    XCTAssertEqual(runner.runs["email"]?.progressDetail, "Halfway")

    await release.open()
    await task?.value
    XCTAssertFalse(runner.isRunning("email"))
    XCTAssertEqual(runner.runs["email"]?.phase, .succeeded)
    XCTAssertEqual(runner.runs["email"]?.statusMessage, "done")
    XCTAssertNil(runner.runs["email"]?.errorMessage)
  }

  func testFailureOutcomePublishesFailedState() async {
    let runner = ConnectorImportRunner()

    let task = runner.start(
      connectorID: "calendar",
      progressTitle: "t",
      progressDetail: "d"
    ) { _ in
      .failure(message: "boom")
    }

    await task?.value
    XCTAssertFalse(runner.isRunning("calendar"))
    XCTAssertEqual(runner.runs["calendar"]?.phase, .failed)
    XCTAssertEqual(runner.runs["calendar"]?.errorMessage, "boom")
    XCTAssertNil(runner.runs["calendar"]?.statusMessage)
  }

  func testDuplicateStartIsIgnoredWhileRunning() async {
    let runner = ConnectorImportRunner()
    let release = Gate()
    var secondOperationRan = false

    let first = runner.start(
      connectorID: "email",
      progressTitle: "first",
      progressDetail: "d"
    ) { _ in
      await release.wait()
      return .success(message: "first done")
    }
    let second = runner.start(
      connectorID: "email",
      progressTitle: "second",
      progressDetail: "d"
    ) { _ in
      secondOperationRan = true
      return .success(message: "second done")
    }

    XCTAssertNotNil(first)
    XCTAssertNil(second)
    XCTAssertEqual(runner.runs["email"]?.progressTitle, "first")

    await release.open()
    await first?.value
    XCTAssertFalse(secondOperationRan)
    XCTAssertEqual(runner.runs["email"]?.statusMessage, "first done")
  }

  func testRunsForDifferentConnectorsAreIndependent() async {
    let runner = ConnectorImportRunner()
    let release = Gate()

    let email = runner.start(
      connectorID: "email",
      progressTitle: "e",
      progressDetail: "d"
    ) { _ in
      await release.wait()
      return .success(message: "email done")
    }
    let calendar = runner.start(
      connectorID: "calendar",
      progressTitle: "c",
      progressDetail: "d"
    ) { _ in
      .success(message: "calendar done")
    }

    XCTAssertNotNil(email)
    XCTAssertNotNil(calendar)

    await calendar?.value
    XCTAssertTrue(runner.isRunning("email"))
    XCTAssertEqual(runner.runs["calendar"]?.phase, .succeeded)

    await release.open()
    await email?.value
    XCTAssertEqual(runner.runs["email"]?.statusMessage, "email done")
  }

  func testTerminalStateRetainedUntilNextStartReplacesIt() async {
    let runner = ConnectorImportRunner()

    let first = runner.start(
      connectorID: "email",
      progressTitle: "t1",
      progressDetail: "d1"
    ) { _ in
      .failure(message: "first failed")
    }
    await first?.value
    XCTAssertEqual(runner.runs["email"]?.phase, .failed)
    XCTAssertEqual(runner.runs["email"]?.errorMessage, "first failed")

    let release = Gate()
    let second = runner.start(
      connectorID: "email",
      progressTitle: "t2",
      progressDetail: "d2"
    ) { _ in
      await release.wait()
      return .success(message: "second done")
    }

    XCTAssertNotNil(second)
    XCTAssertEqual(runner.runs["email"]?.phase, .running)
    XCTAssertNil(runner.runs["email"]?.errorMessage)
    XCTAssertEqual(runner.runs["email"]?.progressTitle, "t2")

    await release.open()
    await second?.value
    XCTAssertEqual(runner.runs["email"]?.phase, .succeeded)
    XCTAssertEqual(runner.runs["email"]?.statusMessage, "second done")
  }

  func testAcknowledgeSuccessClearsSucceededRun() async {
    let runner = ConnectorImportRunner()

    let task = runner.start(
      connectorID: "local-files",
      progressTitle: "t",
      progressDetail: "d"
    ) { _ in
      .success(message: "done")
    }
    await task?.value
    XCTAssertEqual(runner.runs["local-files"]?.phase, .succeeded)

    runner.acknowledgeSuccess(connectorID: "local-files")
    XCTAssertNil(runner.runs["local-files"])
  }

  func testAcknowledgeSuccessKeepsFailedRun() async {
    let runner = ConnectorImportRunner()

    let task = runner.start(
      connectorID: "email",
      progressTitle: "t",
      progressDetail: "d"
    ) { _ in
      .failure(message: "boom")
    }
    await task?.value

    runner.acknowledgeSuccess(connectorID: "email")
    XCTAssertEqual(runner.runs["email"]?.phase, .failed)
    XCTAssertEqual(runner.runs["email"]?.errorMessage, "boom")
  }

  func testAcknowledgeSuccessIgnoresRunningRun() async {
    let runner = ConnectorImportRunner()
    let release = Gate()

    let task = runner.start(
      connectorID: "email",
      progressTitle: "t",
      progressDetail: "d"
    ) { _ in
      await release.wait()
      return .success(message: "done")
    }

    runner.acknowledgeSuccess(connectorID: "email")
    XCTAssertEqual(runner.runs["email"]?.phase, .running)
    XCTAssertTrue(runner.isRunning("email"))

    await release.open()
    await task?.value
    XCTAssertEqual(runner.runs["email"]?.phase, .succeeded)
  }

  func testProgressUpdateAfterCompletionIsDropped() async {
    let runner = ConnectorImportRunner()
    var sink: ConnectorImportRunner.ProgressSink?

    let task = runner.start(
      connectorID: "email",
      progressTitle: "t",
      progressDetail: "d"
    ) { progress in
      sink = progress
      return .success(message: "done")
    }
    await task?.value

    sink?.update(title: "late", detail: "late")
    XCTAssertEqual(runner.runs["email"]?.phase, .succeeded)
    XCTAssertEqual(runner.runs["email"]?.progressTitle, "t")
    XCTAssertEqual(runner.runs["email"]?.progressDetail, "d")
  }

  func testStaleSinkFromFinishedRunCannotMutateNewerRun() async {
    let runner = ConnectorImportRunner()
    var staleSink: ConnectorImportRunner.ProgressSink?

    let first = runner.start(
      connectorID: "email",
      progressTitle: "t1",
      progressDetail: "d1"
    ) { progress in
      staleSink = progress
      return .success(message: "first done")
    }
    await first?.value

    let release = Gate()
    let second = runner.start(
      connectorID: "email",
      progressTitle: "t2",
      progressDetail: "d2"
    ) { _ in
      await release.wait()
      return .success(message: "second done")
    }
    XCTAssertNotNil(second)

    staleSink?.update(title: "stale", detail: "stale")
    XCTAssertEqual(runner.runs["email"]?.progressTitle, "t2")
    XCTAssertEqual(runner.runs["email"]?.progressDetail, "d2")

    await release.open()
    await second?.value
    XCTAssertEqual(runner.runs["email"]?.phase, .succeeded)
  }
}

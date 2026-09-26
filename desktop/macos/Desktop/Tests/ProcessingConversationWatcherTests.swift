import XCTest

@testable import Omi_Computer

/// The watcher follows a processing row to a terminal state with injected
/// clock and sleeper, publishes the resolved row, and emits telemetry.
@MainActor
final class ProcessingConversationWatcherTests: XCTestCase {
  nonisolated private static let base = Date(timeIntervalSince1970: 1_700_000_000)

  nonisolated private static func conversation(
    id: String = "c1",
    status: ConversationStatus,
    deferred: Bool = false,
    title: String = ""
  ) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: base,
      updatedAt: nil,
      startedAt: nil,
      finishedAt: base,
      structured: Structured(title: title, overview: "", emoji: "", category: "", actionItems: [], events: []),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: nil,
      status: status,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil,
      deferred: deferred
    )
  }

  /// Serialises the watcher's sleeps so a test can step it deterministically.
  private actor StepClock {
    private var waiters: [CheckedContinuation<Void, Error>] = []
    private(set) var requestedDelays: [UInt64] = []

    func sleep(_ nanoseconds: UInt64) async throws {
      try await withCheckedThrowingContinuation { continuation in
        requestedDelays.append(nanoseconds)
        waiters.append(continuation)
      }
    }

    /// Release one pending sleep. Yields until a sleeper is actually waiting.
    func step() async {
      while waiters.isEmpty {
        await Task.yield()
      }
      waiters.removeFirst().resume()
    }
  }

  /// Scripted detail responses; the last entry repeats.
  private actor FetchScript {
    private var responses: [Result<ServerConversation, Error>]
    private(set) var calls = 0

    init(_ responses: [Result<ServerConversation, Error>]) {
      self.responses = responses
    }

    func next() throws -> ServerConversation {
      calls += 1
      let result = responses.count > 1 ? responses.removeFirst() : responses[0]
      return try result.get()
    }
  }

  private struct Boom: Error {}

  private func settle() async {
    for _ in 0..<40 { await Task.yield() }
  }

  func test_pollDelays_backOffThenRepeatLast() {
    XCTAssertEqual(ProcessingConversationWatcher.pollDelay(attempt: 0), 3)
    XCTAssertEqual(ProcessingConversationWatcher.pollDelay(attempt: 5), 60)
    XCTAssertEqual(ProcessingConversationWatcher.pollDelay(attempt: 50), 60)
  }

  func test_shouldWatch_onlyLivePipelineRows() {
    XCTAssertTrue(ProcessingConversationWatcher.shouldWatch(Self.conversation(status: .processing)))
    XCTAssertTrue(ProcessingConversationWatcher.shouldWatch(Self.conversation(status: .inProgress)))
    XCTAssertFalse(ProcessingConversationWatcher.shouldWatch(Self.conversation(status: .completed, title: "T")))
    XCTAssertFalse(ProcessingConversationWatcher.shouldWatch(Self.conversation(status: .failed)))
    XCTAssertFalse(
      ProcessingConversationWatcher.shouldWatch(Self.conversation(status: .processing, deferred: true)),
      "Nothing is running for a deferred row; polling it would only burn requests")
  }

  func test_resolvesProcessingRow_publishesAndEmitsElapsed() async {
    let clock = StepClock()
    let script = FetchScript([
      .success(Self.conversation(status: .processing)),
      .success(Self.conversation(status: .completed, title: "Done")),
    ])
    var now = Self.base.addingTimeInterval(10)
    var resolved: [ServerConversation] = []
    var completedEvents: [(String, Int, String)] = []
    var stalledEvents: [(String, Int)] = []

    let watcher = ProcessingConversationWatcher(
      fetch: { _ in try await script.next() },
      sleeper: { try await clock.sleep($0) },
      now: { now },
      onResolved: { resolved.append($0) },
      onCompleted: { completedEvents.append(($0, $1, $2)) },
      onStalled: { stalledEvents.append(($0, $1)) }
    )

    watcher.sync(with: [Self.conversation(status: .processing)])
    XCTAssertEqual(watcher.watchedIDs, ["c1"])

    await clock.step()  // first poll → still processing
    await settle()
    XCTAssertEqual(resolved.map(\.status), [.processing], "Interim detail is published for the provisional title")
    XCTAssertEqual(completedEvents.count, 0)

    now = Self.base.addingTimeInterval(42)
    await clock.step()  // second poll → completed
    await settle()

    XCTAssertEqual(resolved.last?.structured.title, "Done")
    XCTAssertEqual(completedEvents.count, 1)
    XCTAssertEqual(completedEvents.first?.1, 42)
    XCTAssertEqual(completedEvents.first?.2, "completed")
    XCTAssertTrue(stalledEvents.isEmpty)
    XCTAssertTrue(watcher.watchedIDs.isEmpty)
    XCTAssertTrue(watcher.isSettlingDerived("c1"), "Derived effects are still landing after status flips")
    let delays = await clock.requestedDelays
    XCTAssertEqual(Array(delays.prefix(2)), [3_000_000_000, 5_000_000_000])

    await clock.step()  // grace sleep → refetch → settled
    await settle()
    XCTAssertFalse(watcher.isSettlingDerived("c1"))
    XCTAssertEqual(resolved.count, 3, "Grace refetch republishes the row with its derived fields")
  }

  func test_failedOutcome_doesNotEnterSettling() async {
    let clock = StepClock()
    let script = FetchScript([.success(Self.conversation(status: .failed))])
    var completedEvents: [String] = []
    let watcher = ProcessingConversationWatcher(
      fetch: { _ in try await script.next() },
      sleeper: { try await clock.sleep($0) },
      now: { Self.base.addingTimeInterval(5) },
      onResolved: { _ in },
      onCompleted: { completedEvents.append($2) },
      onStalled: { _, _ in }
    )
    watcher.sync(with: [Self.conversation(status: .processing)])
    await clock.step()
    await settle()
    XCTAssertEqual(completedEvents, ["failed"])
    XCTAssertFalse(watcher.isSettlingDerived("c1"))
  }

  func test_stalledReportedOnce_evenWhileFetchesFail() async {
    let clock = StepClock()
    let script = FetchScript([.failure(Boom())])
    var stalledEvents: [(String, Int)] = []
    var resolvedCount = 0
    var completedCount = 0
    let watcher = ProcessingConversationWatcher(
      fetch: { _ in try await script.next() },
      sleeper: { try await clock.sleep($0) },
      now: { Self.base.addingTimeInterval(ConversationProcessingProgress.stalledAfter + 5) },
      onResolved: { _ in resolvedCount += 1 },
      onCompleted: { _, _, _ in completedCount += 1 },
      onStalled: { stalledEvents.append(($0, $1)) }
    )
    watcher.sync(with: [Self.conversation(status: .processing)])
    await settle()
    XCTAssertEqual(stalledEvents.count, 1, "Stalled is reported from the first observation")
    XCTAssertEqual(stalledEvents.first?.1, Int(ConversationProcessingProgress.stalledAfter + 5))
    await clock.step()
    await settle()
    await clock.step()
    await settle()
    XCTAssertEqual(stalledEvents.count, 1, "Later polls must not re-report")
    XCTAssertEqual(resolvedCount, 0, "Nothing to publish while fetches fail")
    XCTAssertEqual(completedCount, 0)
    XCTAssertEqual(watcher.watchedIDs, ["c1"], "The watcher never gives up while the row is visible")
    watcher.stopAll()
  }

  func test_syncStopsFollowingRowsThatLeftTheList() async {
    let clock = StepClock()
    let script = FetchScript([.success(Self.conversation(status: .processing))])
    let watcher = ProcessingConversationWatcher(
      fetch: { _ in try await script.next() },
      sleeper: { try await clock.sleep($0) },
      now: { Self.base },
      onResolved: { _ in },
      onCompleted: { _, _, _ in },
      onStalled: { _, _ in }
    )
    watcher.sync(with: [
      Self.conversation(id: "a", status: .processing), Self.conversation(id: "b", status: .processing),
    ])
    XCTAssertEqual(watcher.watchedIDs, ["a", "b"])
    watcher.sync(with: [Self.conversation(id: "b", status: .processing)])
    XCTAssertEqual(watcher.watchedIDs, ["b"])
    watcher.sync(with: [Self.conversation(id: "b", status: .completed, title: "T")])
    XCTAssertTrue(watcher.watchedIDs.isEmpty, "A row resolved by another path is dropped")
  }
}

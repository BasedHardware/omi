import XCTest

@testable import Omi_Computer

@MainActor
final class TranscriptionRestartCoordinatorTests: XCTestCase {
  func testRestartWaitsForPhysicalStopBeforeStartingReplacement() async {
    var events: [String] = []
    let (stream, continuation) = AsyncStream<Void>.makeStream()

    let task = TranscriptionRestartCoordinator.restart(
      stop: { events.append("stop") },
      waitForPhysicalStop: {
        for await _ in stream { break }
      },
      start: { events.append("start") }
    )

    XCTAssertEqual(events, ["stop"])
    continuation.yield(())
    await task.value
    XCTAssertEqual(events, ["stop", "start"])
  }
}

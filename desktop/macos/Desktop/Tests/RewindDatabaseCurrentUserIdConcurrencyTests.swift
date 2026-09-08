import XCTest

@testable import Omi_Computer

/// Regression coverage for SCA-8: `RewindDatabase.currentUserId` was a
/// `nonisolated(unsafe) static var String?`, racy across the `RewindDatabase`
/// actor, `MainActor` (`AgentVMService`), and the `nonisolated`
/// `markCleanShutdown()` termination path. It is now lock-gated. These tests
/// pin the race-free contract: every read returns a coherent value written by
/// some writer (never a torn/garbage pointer), and round-trip get/set works
/// from any executor.
final class RewindDatabaseCurrentUserIdConcurrencyTests: XCTestCase {

  override func tearDown() async throws {
    // Restore the default unconfigured state regardless of what a test wrote.
    RewindDatabase.currentUserId = nil
    try await super.tearDown()
  }

  func testCurrentUserIdRoundTripsThroughLock() {
    // Sanity: the computed property preserves the exact value written, including
    // nil. If the lock-backed accessor were wired incorrectly this would fail.
    RewindDatabase.currentUserId = nil
    XCTAssertNil(RewindDatabase.currentUserId)

    let id = "sca8-roundtrip-\(UUID().uuidString)"
    RewindDatabase.currentUserId = id
    XCTAssertEqual(RewindDatabase.currentUserId, id)

    RewindDatabase.currentUserId = nil
    XCTAssertNil(RewindDatabase.currentUserId)
  }

  func testConcurrentReadWriteIsRaceFree() async throws {
    // Concurrent writers each own a distinct ID; readers sample continuously.
    // Under the prior `nonisolated(unsafe)` storage a concurrent write+read of
    // a refcounted `String?` could return a torn value or trap on use-after-free
    // in the string's heap storage. With the lock, every read must return either
    // nil or one of the writer-owned strings — never anything else.
    let writerCount = 8
    let readersPerWriter = 4
    let writerIDs = (0..<writerCount).map { _ in "sca8-writer-\(UUID().uuidString)" }

    // Seed with nil so readers can also observe the unconfigured state.
    RewindDatabase.currentUserId = nil

    let validValues = Set(writerIDs + [nil as String?])

    await withTaskGroup(of: Void.self) { group in
      for id in writerIDs {
        group.addTask {
          // Hammer writes from this task's executor.
          for _ in 0..<5_000 {
            RewindDatabase.currentUserId = id
          }
        }
        for _ in 0..<readersPerWriter {
          group.addTask {
            // Hammer reads from independent concurrent tasks.
            for _ in 0..<5_000 {
              let snapshot = RewindDatabase.currentUserId
              XCTAssertTrue(
                validValues.contains(snapshot),
                "currentUserId returned a torn/invalid value: \(String(describing: snapshot))"
              )
            }
          }
        }
      }
      // All child tasks must complete without trapping.
      for await _ in group {}
    }
  }
}

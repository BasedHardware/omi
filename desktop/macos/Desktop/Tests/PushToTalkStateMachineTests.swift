import XCTest

@testable import Omi_Computer

final class PushToTalkStateMachineTests: XCTestCase {
  func testStartListeningIsIdempotentOutsideIdleOrPendingLock() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("guard state == .idle || state == .pendingLockDecision else"))
    XCTAssertTrue(source.contains("PushToTalkManager: startListening ignored — state="))
  }

  func testMicCaptureStartCannotDoubleAdvanceState() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("private var micCaptureStartInFlight = false"))
    XCTAssertTrue(source.contains("private var micCaptureActive = false"))
    XCTAssertTrue(source.contains("guard !micCaptureStartInFlight && !micCaptureActive else"))
    XCTAssertTrue(source.contains("PushToTalkManager: mic capture start ignored — already active"))
    XCTAssertTrue(source.contains("self.micCaptureActive = true"))
  }

  private func pushToTalkManagerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}

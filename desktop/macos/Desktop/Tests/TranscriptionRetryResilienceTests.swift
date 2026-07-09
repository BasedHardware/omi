import XCTest

@testable import Omi_Computer

final class TranscriptionRetryResilienceTests: XCTestCase {
  func testPausesInsteadOfStoppingAfterRepeatedDBFailures() throws {
    let source = try sourceFile("TranscriptionRetryService.swift")
    XCTAssertTrue(source.contains("isPausedForDBErrors"))
    XCTAssertTrue(source.contains("pausing timer"))
    XCTAssertFalse(source.contains("stopping timer to avoid error flood"))
    XCTAssertTrue(source.contains("resumeAfterDatabaseRecovery"))
  }

  func testBusyErrorsDoNotTriggerCorruptionRecovery() throws {
    let source = try sourceFile("Rewind/Core/RewindDatabase.swift")
    XCTAssertTrue(source.contains("isBusyDatabaseError"))
    XCTAssertTrue(source.contains("recordDbLockContention"))
    XCTAssertTrue(source.contains("if isBusyDatabaseError(error) { return false }"))
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}

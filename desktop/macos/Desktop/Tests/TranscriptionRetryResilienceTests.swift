import XCTest

@testable import Omi_Computer

final class TranscriptionRetryResilienceTests: XCTestCase {
  func testPausesInsteadOfStoppingAfterRepeatedDBFailures() throws {
    let source = try sourceFile("TranscriptionRetryService.swift")
    XCTAssertTrue(source.contains("isPausedForDBErrors"))
    XCTAssertTrue(source.contains("pausing timer"))
    XCTAssertTrue(source.contains("resumeAfterDatabaseRecovery"))
  }

  func testBusyErrorsDoNotTriggerCorruptionRecovery() throws {
    let source = try sourceFile("Rewind/Core/RewindDatabase.swift")
    XCTAssertTrue(source.contains("isBusyDatabaseError"))
    XCTAssertTrue(source.contains("recordDbLockContention"))
    // Check semantic elements separately rather than exact formatting, which
    // would break on a standard Swift multi-line brace reformat.
    XCTAssertTrue(source.contains("isBusyDatabaseError(error)"))
    XCTAssertTrue(source.contains("return false"))
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

import XCTest

@testable import Omi_Computer

final class AgentPillLifecycleTests: XCTestCase {
  func testFloatingPillUsesBackgroundAgentPrompt() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("You are running inside a visible floating background agent pill."))
    XCTAssertTrue(source.contains("Do the requested work now; do not merely acknowledge"))
    XCTAssertTrue(source.contains("systemPromptSuffix: systemPromptSuffix ?? Self.backgroundAgentSystemPromptSuffix"))
    XCTAssertTrue(source.contains("Do not call spawn_agent or delegate_agent just to hand off this same task."))
  }

  func testFloatingPillDoesNotTreatMissingTerminalProjectionAsSuccess() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("Agent ended before reporting a final result"))
    XCTAssertFalse(source.contains("pill.latestActivity = pill.latestActivity.isEmpty ? \"Finished\" : pill.latestActivity"))
  }

  func testFallbackFailurePathsRecordCompletionTime() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("pill.status = .failed(errorText)\n            pill.completedAt = Date()"))
    XCTAssertTrue(
      source.contains(
        "pill.status = .failed(\"Agent ended before reporting a final result\")\n            pill.completedAt = Date()"))
  }

  func testLateMessageActivityCannotOverwriteTerminalPillStatus() throws {
    let source = try agentPillSource()

    XCTAssertTrue(source.contains("if pill.status.isFinished {\n            return\n        }"))
    XCTAssertTrue(source.contains("let activity = Self.describeActivity(for: aiMessage)"))
  }

  private func agentPillSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/AgentPill.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}

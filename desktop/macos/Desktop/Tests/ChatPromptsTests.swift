import XCTest

@testable import Omi_Computer

final class ChatPromptsTests: XCTestCase {
  func testCurrentTimePromptUsesOneExplicitInstantAndTimeZone() throws {
    let date = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-31T02:30:45Z"))
    let timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))

    XCTAssertEqual(
      ChatPromptBuilder.currentTimePrompt(for: "What day is it?", at: date, timeZone: timeZone),
      "# Current Time\n2026-07-30T22:30:45-04:00 (America/New_York)\n\nWhat day is it?"
    )
  }

  func testExplicitScreenShareRequestUsesCanonicalScreenRecordingPermissionTool() {
    let desktopPrompt = ChatPromptBuilder.buildDesktopChat(userName: "Taylor")

    XCTAssertTrue(
      desktopPrompt.contains("screen share, screen sharing, and screen-share as the screen_recording permission"))
    XCTAssertTrue(desktopPrompt.contains("use request_permission immediately"))
    XCTAssertTrue(DesktopCapabilityRegistry.realtimeSelfModelPrompt.contains("screen share"))
    XCTAssertTrue(DesktopCapabilityRegistry.realtimeSelfModelPrompt.contains("screen_recording"))
    XCTAssertTrue(
      DesktopCapabilityRegistry.realtimeSelfModelPrompt.contains(
        "explicitly say that Omi needs Screen Recording permission"
      )
    )
    XCTAssertTrue(
      DesktopCapabilityRegistry.realtimeSelfModelPrompt.contains(
        "next-turn request such as \"request it\""
      )
    )
  }

  func testOnboardingDefersWebResearchUntilAfterFileScanAndEmailAttempt() throws {
    let prompt = ChatPromptBuilder.buildOnboardingChat(
      userName: "Taylor Swift",
      givenName: "Taylor",
      email: "taylor@example.com"
    )

    let step2Range = try XCTUnwrap(prompt.range(of: "STEP 2 — FILE SCAN + EMAIL READING"))
    let step3Range = try XCTUnwrap(prompt.range(of: "STEP 3 — NON-RESTART PERMISSIONS"))
    let step4Range = try XCTUnwrap(prompt.range(of: "STEP 4 — WEB RESEARCH"))
    let step5Range = try XCTUnwrap(prompt.range(of: "STEP 5 — SCREEN RECORDING"))
    let step6Range = try XCTUnwrap(prompt.range(of: "STEP 6 — EMAIL INSIGHTS + MONTHLY GOAL"))
    let gateRange = try XCTUnwrap(
      prompt.range(
        of: "Use what you learned from the file scan to make the searches more targeted."
      )
    )

    XCTAssertLessThan(step2Range.lowerBound, step3Range.lowerBound)
    XCTAssertLessThan(step3Range.lowerBound, step4Range.lowerBound)
    XCTAssertLessThan(step4Range.lowerBound, step5Range.lowerBound)
    XCTAssertLessThan(step5Range.lowerBound, step6Range.lowerBound)
    XCTAssertGreaterThan(gateRange.lowerBound, step4Range.lowerBound)
    XCTAssertLessThan(gateRange.lowerBound, step5Range.lowerBound)
  }

  @MainActor
  func testPreferredResponseLanguageCreatesAnExplicitKernelDirective() {
    XCTAssertEqual(
      ChatProvider.responseLanguageInstruction(languageCodes: ["es-MX"]),
      "Reply in Spanish (es-MX) unless the user asks for another language."
    )
    XCTAssertNil(ChatProvider.responseLanguageInstruction(languageCodes: []))
  }

  /// The adapter registers every advertised tool with its own description,
  /// promptGuidelines, and input schema. Restating those in the system prompt
  /// shipped the same content twice per turn and let the two copies drift, so
  /// the prompt must carry only cross-tool guidance.
  func testDesktopToolPromptDoesNotRestatePerToolDocs() {
    let prompt = DesktopCapabilityRegistry.desktopToolPrompt
    for capability in DesktopCapabilityRegistry.capabilities(for: .desktopChat) {
      XCTAssertFalse(
        prompt.contains(capability.summary),
        "\(capability.toolName) summary is duplicated in the system prompt; the tool definition already carries it"
      )
    }
  }

  /// Cross-tool guidance has nowhere else to live, so it must survive.
  func testDesktopToolPromptKeepsCrossToolGuidance() {
    let prompt = DesktopCapabilityRegistry.desktopToolPrompt
    XCTAssertTrue(prompt.contains("When to use which tool:"))
    XCTAssertFalse(prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
  }
}

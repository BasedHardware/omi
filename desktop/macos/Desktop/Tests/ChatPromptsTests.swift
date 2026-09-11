import XCTest

@testable import Omi_Computer

final class ChatPromptsTests: XCTestCase {
  func testCurrentDatetimeStringIncludesIANAZoneAndConvertsUTCInstant() throws {
    let date = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-08-27T19:59:51Z"))
    let timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))

    let rendered = ChatPromptBuilder.currentDatetimeString(date, timeZone: timeZone)
    XCTAssertTrue(
      rendered.contains("3:59:51 PM") || rendered.contains("15:59:51"),
      "expected local 3:59:51 PM, got \(rendered)")
    XCTAssertTrue(
      rendered.contains("America/New_York") || rendered.contains("EDT"),
      "expected a zone token, got \(rendered)")
    XCTAssertFalse(rendered.contains("7:59:51 PM"), "must not present UTC-as-local \(rendered)")
  }

  func testDesktopChatPromptDoesNotBakeALiveClockIntoTheCachedPrefix() {
    XCTAssertFalse(ChatPrompts.desktopChat.contains("{current_datetime_str}"))
    XCTAssertTrue(ChatPrompts.desktopChat.contains("# Current Time"))
    XCTAssertTrue(ChatPrompts.desktopChat.contains("{tz}"))
  }

  func testDesktopChatSQLFiltersCompareUTCColumnsToUTCBounds() {
    let prompt = ChatPrompts.desktopChat
    XCTAssertTrue(prompt.contains("MIN(timestamp) AS firstSeenAt, MAX(timestamp) AS lastSeenAt"))
    XCTAssertTrue(prompt.contains("Select raw timestamp and camelCase *At columns"))
    XCTAssertTrue(prompt.contains("execute_sql converts those result cells once"))
    XCTAssertFalse(prompt.contains("MIN(time(timestamp, 'localtime'))"))
    XCTAssertTrue(prompt.contains("datetime('now', 'localtime', 'start of day', '-1 day', 'utc')"))
    XCTAssertTrue(prompt.contains("datetime('now', 'localtime', 'start of day', 'utc')"))
    XCTAssertFalse(
      prompt.contains("timestamp >= datetime('now', 'start of day', '-1 day', 'localtime')"))
    XCTAssertFalse(prompt.contains("timestamp >= datetime('now', '-1 day', 'localtime')"))
    XCTAssertFalse(prompt.contains("startedAt >= datetime('now', 'start of day', '-1 day', 'localtime')"))
    XCTAssertFalse(prompt.contains("createdAt >= datetime('now', 'start of day', '-1 day', 'localtime')"))
    XCTAssertFalse(prompt.contains("which SQLite handles automatically"))
  }

  func testSQLDayBoundsStayUTCVersusUTC() {
    XCTAssertEqual(
      DesktopChatTimestampFormat.SQLDayBounds.startAsUTC(daysAgo: 1),
      "datetime('now', 'localtime', 'start of day', '-1 day', 'utc')")
    XCTAssertEqual(
      DesktopChatTimestampFormat.SQLDayBounds.exclusiveEndAsUTC(daysAgo: 1),
      "datetime('now', 'localtime', 'start of day', 'utc')")
    XCTAssertEqual(
      DesktopChatTimestampFormat.SQLDayBounds.exclusiveEndAsUTC(daysAgo: 0),
      "datetime('now')")
    XCTAssertTrue(DesktopChatTimestampFormat.SQLDayBounds.startAsUTC(daysAgo: 0).hasSuffix("'utc')"))
    XCTAssertEqual(
      DesktopChatTimestampFormat.SQLDayBounds.startAsUTC(daysAgo: -1),
      DesktopChatTimestampFormat.SQLDayBounds.startAsUTC(daysAgo: 0))
    XCTAssertEqual(
      DesktopChatTimestampFormat.SQLDayBounds.exclusiveEndAsUTC(daysAgo: -1),
      DesktopChatTimestampFormat.SQLDayBounds.exclusiveEndAsUTC(daysAgo: 0))
  }

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

  func testScreenReadRecallRoutesToScreenHistoryNotConversations() {
    // Regression: a voice turn asking about a riddle the user had only *read* on screen
    // called search_conversations, found nothing, and answered "no riddles mentioned".
    let voice = DesktopCapabilityRegistry.realtimeSelfModelPrompt
    XCTAssertTrue(voice.contains("lives in screen history, not conversations: use search_screen_history"))
    XCTAssertTrue(voice.contains("search screen history before saying it was never mentioned"))

    let desktopPrompt = ChatPromptBuilder.buildDesktopChat(userName: "Taylor")
    XCTAssertTrue(desktopPrompt.contains("-> semantic_search over screen history, not conversation tools"))
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
}

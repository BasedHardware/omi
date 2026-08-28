import XCTest

@testable import Omi_Computer

/// SCA-358 regression pins. The shipped Insight/Focus cards telling users their clock
/// was "stuck in 2026" came from two defects in the same lanes: a prompt example that
/// taught the model 2026 dates are mistakes, and analysis requests that never stated
/// the year (Insight sent time-of-day + weekday only; Suggestion sent no date at all).
/// These tests pin the fix contract: the teaching example is retired, every analysis
/// user prompt carries today's date from an injectable clock, and the static system
/// prompts stay free of live timestamps so their cached prefixes remain byte-stable.
final class ProactiveDateGroundingTests: XCTestCase {
  // A fixed IANA zone cannot fail to resolve on a supported system; the fallbacks below
  // exist only because SwiftLint bans force-unwrapping — if either ever engaged, the
  // exact-string assertions in these tests fail loudly rather than pass vacuously.
  private let tz = TimeZone(identifier: "America/New_York") ?? .current

  /// 2026-08-25 15:45 America/New_York (EDT, UTC-4).
  private func instant(hour: Int, minute: Int) -> Date {
    var components = DateComponents()
    components.year = 2026
    components.month = 8
    components.day = 25
    components.hour = hour
    components.minute = minute
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = tz
    return calendar.date(from: components) ?? Date(timeIntervalSince1970: 0)
  }

  @MainActor
  func testInsightDefaultPromptRetiresTheWrongYearExample() {
    let prompt = InsightAssistantSettings.defaultAnalysisPrompt

    XCTAssertFalse(prompt.contains("double-check the year"))
    // The replacement keeps the calendar-mistake class without year suspicion.
    XCTAssertTrue(prompt.contains("double-check the date"))
    XCTAssertTrue(prompt.contains("DATE GROUNDING"))
    XCTAssertTrue(prompt.contains("never say the clock, calendar, or year"))
  }
  @MainActor
  func testSuggestionDefaultPromptRetiresTheWrongYearExample() {
    let prompt = SuggestionAssistantSettings.defaultAnalysisPrompt

    XCTAssertFalse(prompt.contains("double-check the year"))
    XCTAssertTrue(prompt.contains("double-check the date"))
    XCTAssertTrue(prompt.contains("DATE GROUNDING"))
    XCTAssertTrue(prompt.contains("never say the clock, calendar, or year"))
  }

  /// Cached-prefix contract: the shipped system prompts are the stable prefix these
  /// lanes cache implicitly — a per-second timestamp in them would bust the prefix
  /// on every call. (The "due 2026-08-10" bad-example is date-only and unaffected.)
  @MainActor
  func testDefaultSystemPromptsCarryNoLiveTimestamp() {
    let timestampLike = #"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"#
    for prompt in [InsightAssistantSettings.defaultAnalysisPrompt, SuggestionAssistantSettings.defaultAnalysisPrompt] {
      XCTAssertNil(
        prompt.range(of: timestampLike, options: .regularExpression),
        "system prompt must not embed a live timestamp")
    }
  }

  // MARK: - User-prompt grounding (controllable clock seam)

  func testInsightClockLineCarriesFullYearAndTimezone() {
    let line = InsightAssistant.analysisClockLine(at: instant(hour: 15, minute: 45), timeZone: tz)

    XCTAssertEqual(line, "Date/Time: Tuesday, August 25, 2026 at 3:45 PM (America/New_York)")
  }

  func testSuggestionUserPromptCarriesTodaysDateFromTheClockSeam() {
    let prompt = SuggestionAssistant.userPrompt(
      appName: "Calendar",
      windowTitle: "October",
      groundingText: "== OPEN COMMITMENTS ==\nShip the cache change",
      recentSuggestions: ["Mask the credentials visible in terminal"],
      now: instant(hour: 9, minute: 0),
      timeZone: tz
    )

    XCTAssertTrue(prompt.contains("Today is 2026-08-25 (Tuesday)."))
    XCTAssertTrue(prompt.contains("App: Calendar"))
    XCTAssertTrue(prompt.contains("Window: October"))
    XCTAssertTrue(prompt.contains("== OPEN COMMITMENTS =="))
    XCTAssertTrue(prompt.contains("== RECENT SUGGESTIONS (do not repeat these) =="))
  }

  func testSuggestionUserPromptOmitsEmptySectionsButKeepsTheDate() {
    let prompt = SuggestionAssistant.userPrompt(
      appName: "Safari",
      windowTitle: nil,
      groundingText: "",
      recentSuggestions: [],
      now: instant(hour: 22, minute: 30),
      timeZone: tz
    )

    XCTAssertTrue(prompt.contains("Today is 2026-08-25 (Tuesday)."))
    XCTAssertTrue(prompt.contains("Window: (no title)"))
    XCTAssertFalse(prompt.contains("== RECENT SUGGESTIONS"))
  }

  /// The seam the other proactive lanes already use (TaskAssistant's "Today is
  /// yyyy-MM-dd (EEEE)") is the one shared helper — day-stable within a timezone, so
  /// a same-day re-evaluation renders byte-identical prompt heads.
  func testCalendarDayIsStableWithinTheDay() {
    let morning = ChatPromptBuilder.currentCalendarDay(at: instant(hour: 0, minute: 1), timeZone: tz)
    let night = ChatPromptBuilder.currentCalendarDay(at: instant(hour: 23, minute: 59), timeZone: tz)

    XCTAssertEqual(morning, "2026-08-25 (Tuesday)")
    XCTAssertEqual(morning, night)
  }

  /// The re-ranking lane weighs "Time urgency (due date proximity)" against UTC ISO
  /// dues with no anchor — the model judged proximity from its training-cutoff date.
  /// The prompt now states today and labels the dues as UTC (SCA-358).
  func testTaskRerankPromptCarriesTodaysDateAndLabelsUTCDues() {
    let prompt = TaskPrioritizationService.rerankPrompt(
      totalCount: 12,
      windowFirst: 1,
      windowLast: 8,
      contextSection: "",
      taskLines: "1. [id:t1] Ship the cache change [due: 2026-08-26T04:00:00Z]",
      maxMoves: 5,
      today: "2026-08-25 (Tuesday)"
    )

    XCTAssertTrue(prompt.contains("Today is 2026-08-25 (Tuesday)."))
    XCTAssertTrue(prompt.contains("UTC ISO timestamps"))
    XCTAssertTrue(prompt.contains("[due: 2026-08-26T04:00:00Z]"))
    XCTAssertTrue(prompt.contains("Time urgency (due date proximity)"))
  }
}

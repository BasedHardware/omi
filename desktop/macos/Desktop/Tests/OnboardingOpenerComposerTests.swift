import XCTest

@testable import Omi_Computer

final class OnboardingOpenerComposerTests: XCTestCase {
  private var utcCalendar: Calendar {
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = .gmt
    return cal
  }

  private func date(hour: Int) -> Date {
    // 2026-01-15 at the given UTC hour.
    let components = DateComponents(year: 2026, month: 1, day: 15, hour: hour)
    guard let date = utcCalendar.date(from: components) else {
      fatalError("Failed to build fixed test date for hour \(hour)")
    }
    return date
  }

  private func meeting(_ title: String, _ time: String) -> OnboardingMeetingBrief {
    OnboardingMeetingBrief(title: title, time: time)
  }

  // MARK: timeOfDay

  func testTimeOfDayBuckets() {
    XCTAssertEqual(OnboardingOpenerComposer.timeOfDay(date(hour: 8), calendar: utcCalendar), "Morning")
    XCTAssertEqual(OnboardingOpenerComposer.timeOfDay(date(hour: 14), calendar: utcCalendar), "Afternoon")
    XCTAssertEqual(OnboardingOpenerComposer.timeOfDay(date(hour: 21), calendar: utcCalendar), "Evening")
    // Boundary + pre-dawn fall into Evening.
    XCTAssertEqual(OnboardingOpenerComposer.timeOfDay(date(hour: 3), calendar: utcCalendar), "Evening")
  }

  // MARK: greeting (short headline)

  func testGreetingIsTimeOfDayPlusName() {
    let g = OnboardingOpenerComposer.greeting(name: "Archit", now: date(hour: 8), calendar: utcCalendar)
    XCTAssertEqual(g, "Morning, Archit")
  }

  func testGreetingEmptyNameDropsComma() {
    let g = OnboardingOpenerComposer.greeting(name: "   ", now: date(hour: 8), calendar: utcCalendar)
    XCTAssertEqual(g, "Morning")
  }

  // MARK: subline — no meetings

  func testSublineNoMeetingsAlways() {
    let s = OnboardingOpenerComposer.subline(mode: .always, meetings: [])
    XCTAssertEqual(s, "I'm set up and listening. Ask me anything to start.")
  }

  func testSublineNoMeetingsMeetingsOnly() {
    let s = OnboardingOpenerComposer.subline(mode: .meetingsOnly, meetings: [])
    XCTAssertEqual(s, "I'm set up and I'll listen during your meetings. Ask me anything to start.")
  }

  // MARK: subline — with meetings

  func testSublineSingleMeeting() {
    let s = OnboardingOpenerComposer.subline(mode: .always, meetings: [meeting("Design sync", "2:00 PM")])
    XCTAssertEqual(s, "'Design sync' at 2:00 PM today. I'll be listening.")
  }

  func testSublineMultipleMeetingsUsesCountAndFirst() {
    let s = OnboardingOpenerComposer.subline(
      mode: .meetingsOnly,
      meetings: [meeting("Design sync", "2:00 PM"), meeting("1:1", "4:00 PM"), meeting("Standup", "5:00 PM")])
    XCTAssertEqual(
      s,
      "3 meetings today — first is 'Design sync' at 2:00 PM. I'll listen during your meetings.")
  }

  // MARK: starters

  func testStartersWithMeetingPrependsPrepAndCapsAtThree() {
    let starters = OnboardingOpenerComposer.starters(
      meetings: [meeting("Design sync", "2:00 PM")],
      baseStarters: ["What should I do today?", "How is Atlas going?", "What did I miss?"])
    XCTAssertEqual(starters, ["Prep me for 'Design sync'", "What should I do today?", "How is Atlas going?"])
  }

  func testStartersWithoutMeetingUsesBaseCappedAtThree() {
    let starters = OnboardingOpenerComposer.starters(
      meetings: [],
      baseStarters: ["What should I do today?", "How is Atlas going?", "What did I miss?", "Extra?"])
    XCTAssertEqual(starters, ["What should I do today?", "How is Atlas going?", "What did I miss?"])
  }

  func testStartersDedupIsCaseInsensitiveAndDropsEmpties() {
    let starters = OnboardingOpenerComposer.starters(
      meetings: [],
      baseStarters: ["What should I do today?", "  ", "what should i do today?", "Next step?"])
    XCTAssertEqual(starters, ["What should I do today?", "Next step?"])
  }

  func testComposeBundlesGreetingSublineAndStarters() {
    let content = OnboardingOpenerComposer.compose(
      name: "Archit", mode: .always, meetings: [meeting("Design sync", "2:00 PM")],
      now: date(hour: 8), baseStarters: ["What should I do today?"], calendar: utcCalendar)
    XCTAssertEqual(content.greeting, "Morning, Archit")
    XCTAssertTrue(content.subline.hasPrefix("'Design sync' at 2:00 PM today"))
    XCTAssertEqual(content.starters, ["Prep me for 'Design sync'", "What should I do today?"])
  }
}

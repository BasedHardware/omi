import XCTest

@testable import Omi_Computer

final class SecondBrainHomeTests: XCTestCase {
  func testReturningHomeMakesTheUsersRealContextTheProductProof() {
    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 12,
      memories: 34,
      tasks: 5,
      screenCount: 1_200,
      personalizedPrompts: ["What did Priya need from me after our launch review?"],
      onboardingPrompts: [],
      opener: nil)

    XCTAssertEqual(snapshot.headline, "Your life, ready to answer.")
    XCTAssertEqual(snapshot.total, 1_251)
    XCTAssertEqual(snapshot.sources.map(\.title), ["Heard", "Seen", "Remembered", "Decided"])
    XCTAssertEqual(
      snapshot.sources.map(\.detail),
      ["12 conversations", "1,200 screen moments", "34 memories", "5 open tasks"])
    XCTAssertEqual(snapshot.prompts.first, HomeSuggestionComposer.universalFirstQuestion)
    XCTAssertTrue(snapshot.prompts.contains("What did Priya need from me after our launch review?"))
  }

  func testPostOnboardingHomeKeepsTheGreetingAndRealStarterQuestions() {
    let opener = OnboardingOpenerContent(
      greeting: "Morning, Sam",
      subline: "Two meetings today. I'll be listening.",
      starters: [
        "Prep me for product review",
        "What should I do today?",
        "Prep me for product review",
      ])

    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 0,
      memories: 0,
      tasks: 0,
      screenCount: 0,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: opener)

    XCTAssertEqual(snapshot.greeting, "Morning, Sam")
    XCTAssertEqual(snapshot.headline, "Your second brain starts here.")
    XCTAssertEqual(snapshot.supportingCopy, opener.subline)
    XCTAssertEqual(
      snapshot.prompts,
      [
        "Prep me for product review",
        "What should I do today?",
        "What did I spend my time on this week?",
      ])
  }

  func testUnavailableScreenCountIsShownAsCountingRatherThanAFalseZero() {
    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: 2,
      memories: 3,
      tasks: 1,
      screenCount: nil,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: nil)

    XCTAssertNil(snapshot.total)
    XCTAssertEqual(snapshot.sources.first(where: { $0.kind == .screen })?.detail, "Counting moments…")
  }

  func testBadCountsCannotProduceNegativeProof() {
    let snapshot = SecondBrainHomeSnapshot.compose(
      conversations: -4,
      memories: -3,
      tasks: -2,
      screenCount: -1,
      personalizedPrompts: [],
      onboardingPrompts: [],
      opener: nil)

    XCTAssertEqual(snapshot.total, 0)
    XCTAssertEqual(snapshot.headline, "Your second brain starts here.")
    XCTAssertFalse(snapshot.sources.map(\.detail).joined().contains("-"))
  }
}

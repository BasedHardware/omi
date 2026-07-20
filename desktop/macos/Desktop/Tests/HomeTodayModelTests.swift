import XCTest

@testable import Omi_Computer

final class HomeTodayModelTests: XCTestCase {

  // MARK: - Greeting

  func testGreetingDaypartsAndName() {
    XCTAssertEqual(HomeGreetingComposer.greeting(name: "Nik", hour: 9), "Good morning, Nik.")
    XCTAssertEqual(HomeGreetingComposer.greeting(name: "Nik", hour: 14), "Good afternoon, Nik.")
    XCTAssertEqual(HomeGreetingComposer.greeting(name: "Nik", hour: 22), "Good evening, Nik.")
    XCTAssertEqual(HomeGreetingComposer.greeting(name: "Nik", hour: 2), "Good evening, Nik.")
  }

  func testGreetingNeverRendersPlaceholderName() {
    // Legacy signed-in-without-a-name placeholder must read as a bare greeting.
    XCTAssertEqual(HomeGreetingComposer.greeting(name: "there", hour: 14), "Good afternoon.")
    XCTAssertEqual(HomeGreetingComposer.greeting(name: "  ", hour: 14), "Good afternoon.")
    XCTAssertEqual(HomeGreetingComposer.greeting(name: nil, hour: 14), "Good afternoon.")
  }

  // MARK: - Proof line

  func testProofLineShowsOnlyNonZeroTodayCounts() {
    let segments = HomeGreetingComposer.proofSegments(
      today: .init(conversations: 3, memories: 0, tasks: 5, screens: 214),
      lifetimeConversations: 2401
    )
    XCTAssertEqual(
      segments.map(\.text),
      ["3 conversations", "5 tasks", "214 screens", "today"]
    )
    XCTAssertEqual(segments[0].destination, .conversations)
    XCTAssertEqual(segments[1].destination, .tasks)
    XCTAssertEqual(segments[2].destination, .rewind)
    XCTAssertNil(segments[3].destination)
  }

  func testProofLineMorningCaseLeadsWithLifetime() {
    // The common morning launch: nothing today yet, real history — must not
    // render a row of zeros.
    let segments = HomeGreetingComposer.proofSegments(
      today: .init(conversations: 0, memories: 0, tasks: 0, screens: 0),
      lifetimeConversations: 2401
    )
    XCTAssertEqual(segments.map(\.text), ["Quiet so far today —", "2,401 conversations remembered"])
    XCTAssertEqual(segments[1].destination, .conversations)
  }

  func testProofLineTrueEmptyExplainsInsteadOfZeros() {
    let segments = HomeGreetingComposer.proofSegments(
      today: .init(conversations: 0, memories: 0, tasks: 0, screens: 0),
      lifetimeConversations: 0
    )
    XCTAssertEqual(segments.count, 1)
    XCTAssertNil(segments[0].destination)
    XCTAssertFalse(segments[0].text.contains("0"))
  }

  func testProofLineTreatsUnknownCountsAsAbsent() {
    let segments = HomeGreetingComposer.proofSegments(
      today: .init(conversations: nil, memories: nil, tasks: nil, screens: nil),
      lifetimeConversations: nil
    )
    XCTAssertEqual(segments.count, 1)
    XCTAssertNil(segments[0].destination)
  }

  func testSingularPluralForms() {
    let segments = HomeGreetingComposer.proofSegments(
      today: .init(conversations: 1, memories: 1, tasks: 1, screens: 0),
      lifetimeConversations: nil
    )
    XCTAssertEqual(segments.map(\.text), ["1 conversation", "1 memory", "1 task", "today"])
  }

  // MARK: - First-win memory quality gate

  func testFilePathShapedMemoriesAreFiltered() {
    XCTAssertFalse(FirstWinMemoryFilter.isDisplayable("~/Projects/omi/backend/main.py"))
    XCTAssertFalse(FirstWinMemoryFilter.isDisplayable("/Users/nik/Documents/taxes-2026.pdf"))
    XCTAssertFalse(FirstWinMemoryFilter.isDisplayable("src/utils/helpers/format_date.ts"))
    XCTAssertFalse(FirstWinMemoryFilter.isDisplayable("report_final_v2.docx"))
    XCTAssertFalse(FirstWinMemoryFilter.isDisplayable("   "))
    XCTAssertFalse(FirstWinMemoryFilter.isDisplayable("short"))
  }

  func testHumanSentencesPassTheGate() {
    XCTAssertTrue(
      FirstWinMemoryFilter.isDisplayable("Nik is building Omi, an AI wearable company."))
    XCTAssertTrue(
      FirstWinMemoryFilter.isDisplayable("Your goal this quarter: close the seed round."))
  }

  func testDisplayableDedupesAndCaps() {
    let texts = [
      "Nik is building Omi, an AI wearable company.",
      "nik is building omi, an ai wearable company.",
      "~/Projects/omi/backend/main.py",
      "Your goal this quarter: close the seed round.",
      "Investor pitch Thursday with Meridian Ventures.",
      "One more human sentence about the user here.",
    ]
    let result = FirstWinMemoryFilter.displayable(texts, limit: 3)
    XCTAssertEqual(result.count, 3)
    XCTAssertEqual(result[0], "Nik is building Omi, an AI wearable company.")
    XCTAssertFalse(result.contains { $0.contains("main.py") })
  }
}

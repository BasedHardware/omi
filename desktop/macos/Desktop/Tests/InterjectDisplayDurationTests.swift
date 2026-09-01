import XCTest

@testable import Omi_Computer

final class InterjectDisplayDurationTests: XCTestCase {
  func testFlagOffIsExactlyTheLegacySixSecondPath() {
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(
        title: "A long title with many words in it",
        message: "And an even longer message that would otherwise stretch past six seconds",
        kind: .task,
        enabled: false
      ),
      6
    )
    XCTAssertEqual(InterjectDisplayDuration.legacyTimeout, 6)
  }

  func testWordCountSplitsOnWhitespace() {
    XCTAssertEqual(InterjectDisplayDuration.wordCount(in: ""), 0)
    XCTAssertEqual(InterjectDisplayDuration.wordCount(in: "  hello   world\nagain "), 3)
  }

  func testDurationIsBasePlusQuarterSecondPerWordAndClamped() {
    // task_candidate base 6s + 4 words * 0.25s = 7s
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(title: "two words", message: "two more", kind: .task),
      7
    )
    // resurface base 4s + 0 words = 4s (floor)
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(title: "", message: "", kind: .resurface),
      4
    )
    // empty insight uses base 5s
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(title: "", message: "", kind: .insight),
      5
    )
  }

  func testTaskCandidateBaseIsLongerThanResurface() {
    XCTAssertGreaterThan(
      InterjectDisplayDuration.baseTimeout(for: .task),
      InterjectDisplayDuration.baseTimeout(for: .resurface)
    )
  }

  func testDurationClampsToFourteenSeconds() {
    let many = Array(repeating: "word", count: 80).joined(separator: " ")
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(title: many, message: many, kind: .task),
      14
    )
  }

  func testDurationClampsToFourSecondsEvenWhenMathIsLower() {
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(title: "", message: "", kind: .resurface),
      4
    )
  }

  func testInsightDurationUsesTheTeaserNotTheUnexpandedBody() {
    let longBody = Array(repeating: "word", count: 40).joined(separator: " ")
    let teaser = InterjectDisplayDuration.teaserText(of: longBody)
    XCTAssertEqual(InterjectDisplayDuration.wordCount(in: teaser), 12)

    // insight base 5s + (title 1 + teaser 12) * 0.25s = 8.25s
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(title: "Title", message: longBody, kind: .insight),
      8.25
    )
    // A task still counts the full body and hits the 14s clamp.
    XCTAssertEqual(
      InterjectDisplayDuration.timeout(title: "Title", message: longBody, kind: .task),
      14
    )
  }
}

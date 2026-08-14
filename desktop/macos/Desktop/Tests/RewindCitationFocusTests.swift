import XCTest

@testable import Omi_Computer

final class RewindCitationFocusTests: XCTestCase {
  @MainActor
  func testScreenshotIDParserRejectsMalformedAndNonPositiveValues() {
    XCTAssertEqual(RewindCitationFocusState.parseScreenshotID(" 42 "), 42)
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID(""))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("42x"))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("0"))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("-1"))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("9223372036854775808"))
  }

  @MainActor
  func testCitationTargetIsInsertedIntoSampledTimelineInTimestampOrder() {
    let older = Screenshot(id: 1, timestamp: Date(timeIntervalSince1970: 10), appName: "Editor")
    let newer = Screenshot(id: 3, timestamp: Date(timeIntervalSince1970: 30), appName: "Editor")
    let target = Screenshot(id: 2, timestamp: Date(timeIntervalSince1970: 20), appName: "Editor")

    let result = RewindViewModel.insertingCitationTarget(target, into: [older, newer])

    XCTAssertEqual(result.map(\.id), [1, 2, 3])
    XCTAssertEqual(
      RewindViewModel.insertingCitationTarget(target, into: result).map(\.id),
      [1, 2, 3],
      "a repeated focus request must not duplicate the exact row"
    )
  }
}

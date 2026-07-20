import XCTest

@testable import Omi_Computer

final class HomeValueSnapshotTests: XCTestCase {
  func testUnknownCountsUseHonestLoadingCopy() {
    let snapshot = HomeValueSnapshot.make(
      conversationCount: nil,
      memoryCount: nil,
      screenshotCount: nil
    )

    XCTAssertEqual(snapshot.experience, .loading)
    XCTAssertEqual(snapshot.availableContextSourceCount, 0)
    XCTAssertFalse(snapshot.title.contains("already"))
    XCTAssertEqual(snapshot.askPlaceholder, "Ask about your work or life")
  }

  func testNewAccountGetsImmediateActionWithoutFabricatedHistory() {
    let snapshot = HomeValueSnapshot.make(
      conversationCount: 0,
      memoryCount: 0,
      screenshotCount: 0
    )

    XCTAssertEqual(snapshot.experience, .gettingStarted)
    XCTAssertEqual(snapshot.availableContextSourceCount, 0)
    XCTAssertEqual(snapshot.title, "Ask one question only your Omi could answer.")
    XCTAssertEqual(snapshot.askPlaceholder, "What on my screen matters most right now?")
  }

  func testSmallAmountOfContextUsesBuildingExperience() {
    let snapshot = HomeValueSnapshot.make(
      conversationCount: 1,
      memoryCount: 0,
      screenshotCount: 0
    )

    XCTAssertEqual(snapshot.experience, .building)
    XCTAssertEqual(snapshot.availableContextSourceCount, 1)
    XCTAssertEqual(snapshot.title, "Your second brain is taking shape.")
  }

  func testEstablishedAccountShowsContextFirstValue() {
    let snapshot = HomeValueSnapshot.make(
      conversationCount: 124,
      memoryCount: 842,
      screenshotCount: 12_000
    )

    XCTAssertEqual(snapshot.experience, .established)
    XCTAssertEqual(snapshot.availableContextSourceCount, 3)
    XCTAssertEqual(snapshot.title, "Omi already knows the backstory.")
    XCTAssertTrue(snapshot.subtitle.contains("computer, conversations, and memories"))
    XCTAssertEqual(snapshot.askHeading, "Ask with your context")
  }
}

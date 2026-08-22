import XCTest

@testable import Omi_Computer

@MainActor
final class MeetingNoteTakingNoticeTests: XCTestCase {
  override func tearDown() {
    MeetingNoteTakingNotice.present = MeetingNoteTakingNoticeTests.originalPresenter
    super.tearDown()
  }

  private static let originalPresenter = MeetingNoteTakingNotice.present

  /// The card states what already happened rather than asking permission, so
  /// its copy must stay a statement — a question here would re-introduce the
  /// prompt the notice deliberately replaces.
  func testNoticeCopyIsAStatementNotAPrompt() {
    XCTAssertEqual(MeetingNoteTakingNotice.title, "Meeting detected")
    XCTAssertEqual(MeetingNoteTakingNotice.message, "Omi is taking notes")
    XCTAssertFalse(MeetingNoteTakingNotice.message.contains("?"))
  }

  /// The boundary presents through this seam, so a test can prove the call
  /// happens without a notification centre or a signed-in owner.
  func testPresenterSeamIsInvokable() {
    var presented = 0
    MeetingNoteTakingNotice.present = { presented += 1 }
    MeetingNoteTakingNotice.present()
    XCTAssertEqual(presented, 1)
  }
}

import XCTest

@testable import Omi_Computer

final class RatingPromptPolicyTests: XCTestCase {
  func testPromptIsDueExactlyFromTheThirdQuestion() {
    XCTAssertFalse(RatingPromptPolicy.shouldShow(questionCount: 0, submittedRating: 0, dismissed: false))
    XCTAssertFalse(RatingPromptPolicy.shouldShow(questionCount: 2, submittedRating: 0, dismissed: false))
    XCTAssertTrue(RatingPromptPolicy.shouldShow(questionCount: 3, submittedRating: 0, dismissed: false))
    XCTAssertTrue(RatingPromptPolicy.shouldShow(questionCount: 30, submittedRating: 0, dismissed: false))
  }

  func testSubmittedRatingSilencesThePromptForever() {
    for rating in 1...5 {
      XCTAssertFalse(
        RatingPromptPolicy.shouldShow(questionCount: 10, submittedRating: rating, dismissed: false))
    }
  }

  func testDismissalSilencesThePromptForever() {
    XCTAssertFalse(RatingPromptPolicy.shouldShow(questionCount: 10, submittedRating: 0, dismissed: true))
  }

  func testRemoteKillSwitchOverridesADuePrompt() {
    XCTAssertTrue(
      RatingPromptPolicy.shouldShow(
        questionCount: 3, submittedRating: 0, dismissed: false, remotelyDisabled: false))
    XCTAssertFalse(
      RatingPromptPolicy.shouldShow(
        questionCount: 3, submittedRating: 0, dismissed: false, remotelyDisabled: true))
  }
}

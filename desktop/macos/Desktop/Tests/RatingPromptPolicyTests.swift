import OmiTheme
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

  func testReferralButtonUsesReadableSharedPrimaryStyle() {
    XCTAssertEqual(RatingPromptButtonStyle.referralKind, .primary)
    XCTAssertEqual(RatingPromptButtonStyle.referralSize, .compact)
    XCTAssertEqual(OmiButtonStyle.fill(.primary, pressed: false), Ink.primary)
    XCTAssertEqual(OmiButtonStyle.label(.primary), Ink.surface)
  }

  func testRemoteQuestionThresholdDefersUntilTheConfiguredQuestion() {
    // Threshold 5: three questions are not due anymore…
    XCTAssertFalse(
      RatingPromptPolicy.shouldShow(
        questionCount: 3, submittedRating: 0, dismissed: false, questionThreshold: 5))
    // …and the fifth is.
    XCTAssertTrue(
      RatingPromptPolicy.shouldShow(
        questionCount: 5, submittedRating: 0, dismissed: false, questionThreshold: 5))
  }

  func testRemoteDisableConfigHidesADuePrompt() {
    XCTAssertFalse(
      RatingPromptPolicy.shouldShow(
        questionCount: 3, submittedRating: 0, dismissed: false, enabled: false))
  }

  func testCommentGateIsThePureLowScoreRule() {
    XCTAssertTrue(RatingPromptPolicy.shouldAskForComment(score: 1, commentMaxScore: 3))
    XCTAssertTrue(RatingPromptPolicy.shouldAskForComment(score: 3, commentMaxScore: 3))
    XCTAssertFalse(RatingPromptPolicy.shouldAskForComment(score: 4, commentMaxScore: 3))
    XCTAssertFalse(RatingPromptPolicy.shouldAskForComment(score: 5, commentMaxScore: 3))
  }
}

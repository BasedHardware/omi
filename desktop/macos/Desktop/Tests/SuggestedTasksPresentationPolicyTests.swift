import XCTest

@testable import Omi_Computer

final class SuggestedTasksPresentationPolicyTests: XCTestCase {
  func testInitialSuggestedLoadUsesFloatingIndicatorInsteadOfAnInFlowSection() {
    XCTAssertFalse(SuggestedTasksPresentationPolicy.showsSection(candidateCount: 0))
    XCTAssertTrue(
      SuggestedTasksPresentationPolicy.showsFloatingLoadingIndicator(
        isLoading: true,
        candidateCount: 0
      ))
  }

  func testLoadedSuggestionsReplaceTheFloatingIndicatorWithTheSection() {
    XCTAssertTrue(SuggestedTasksPresentationPolicy.showsSection(candidateCount: 1))
    XCTAssertFalse(
      SuggestedTasksPresentationPolicy.showsCandidates(candidateCount: 1, isExpanded: false))
    XCTAssertTrue(
      SuggestedTasksPresentationPolicy.showsCandidates(candidateCount: 1, isExpanded: true))
    XCTAssertFalse(
      SuggestedTasksPresentationPolicy.showsFloatingLoadingIndicator(
        isLoading: false,
        candidateCount: 1
      ))
  }

  func testRefreshingExistingSuggestionsKeepsTheSectionInPlaceWithoutAnotherIndicator() {
    XCTAssertTrue(SuggestedTasksPresentationPolicy.showsSection(candidateCount: 2))
    XCTAssertFalse(
      SuggestedTasksPresentationPolicy.showsFloatingLoadingIndicator(
        isLoading: true,
        candidateCount: 2
      ))
  }

  func testCollapsedDeepLinkRequiresExpandBeforeCandidateScrollTargetExists() {
    XCTAssertTrue(
      SuggestedTasksPresentationPolicy.shouldExpandBeforeScrollingToCandidate(isExpanded: false))
    XCTAssertFalse(
      SuggestedTasksPresentationPolicy.shouldExpandBeforeScrollingToCandidate(isExpanded: true))
    XCTAssertFalse(
      SuggestedTasksPresentationPolicy.showsCandidates(candidateCount: 1, isExpanded: false),
      "collapsed section must not mount suggested-<id> scroll targets")
    XCTAssertTrue(
      SuggestedTasksPresentationPolicy.showsCandidates(candidateCount: 1, isExpanded: true))
  }

  func testDismissReasonChoicesPreserveAttributionContract() {
    XCTAssertEqual(
      SuggestedCandidateDismissReasons.choices.map(\.reason),
      [.already_handled, .not_mine, .not_useful])
  }
}

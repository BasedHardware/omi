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
}

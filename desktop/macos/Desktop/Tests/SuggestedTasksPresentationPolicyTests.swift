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

  func testSuggestedRowsReserveTheSameLeadingHandleWidthAsCategorizedTaskRows() {
    XCTAssertEqual(TaskRowChrome.leadingHandleWidth, 16)
  }

  func testCreatedTaskIdentifierMatchesCanonicalTaskIdFromAcceptReceipt() {
    let task = TaskActionItem(
      id: "backend-action-item",
      description: "Follow up with Codemagic",
      completed: false,
      createdAt: Date(),
      taskId: "canonical-task"
    )
    XCTAssertTrue(task.matchesTaskIdentifier("backend-action-item"))
    XCTAssertTrue(task.matchesTaskIdentifier("canonical-task"))
    XCTAssertFalse(task.matchesTaskIdentifier("other"))
  }

  func testAcceptAndCompleteSlideWithTheTaskWhileRejectSlidesAway() {
    XCTAssertEqual(SuggestedRowDismissal.Kind.complete.offset, 50)
    XCTAssertEqual(SuggestedRowDismissal.Kind.accept.offset, 50)
    XCTAssertEqual(SuggestedRowDismissal.Kind.reject.offset, -50)
  }

  func testSuggestedRowExitUsesTheSameHoldThenFadeBudgetAsCheckingATask() {
    XCTAssertEqual(SuggestedRowDismissal.exitStartNanos, 400_000_000)
    XCTAssertEqual(SuggestedRowDismissal.exitDurationNanos, 300_000_000)
    XCTAssertEqual(
      SuggestedRowDismissal.checkmarkBounceNanos + SuggestedRowDismissal.checkmarkSettleNanos,
      SuggestedRowDismissal.exitStartNanos
    )
  }
}

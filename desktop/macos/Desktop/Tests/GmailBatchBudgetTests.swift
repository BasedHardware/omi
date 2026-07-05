import XCTest

@testable import Omi_Computer

final class GmailBatchBudgetTests: XCTestCase {

  func testSingleRequestKeepsOriginalSixtySecondBudget() {
    XCTAssertEqual(
      GmailReaderService.batchBudgetSeconds(requestCount: 1, maxConcurrentRequests: 1), 60)
    XCTAssertEqual(
      GmailReaderService.batchBudgetSeconds(requestCount: 1, maxConcurrentRequests: 4), 60)
  }

  func testCombinedFetchBudgetIsWaveBasedNotPerRequest() {
    // 1 probe wave + ceil(13/4) = 4 parallel waves → 300s, not 14 × 60 = 840s.
    XCTAssertEqual(
      GmailReaderService.batchBudgetSeconds(requestCount: 14, maxConcurrentRequests: 4), 300)
  }

  func testSequentialWidthDegradesToPerRequestBudget() {
    // Width 1 means every request is its own wave — matches the old serial cap.
    XCTAssertEqual(
      GmailReaderService.batchBudgetSeconds(requestCount: 3, maxConcurrentRequests: 1), 180)
  }

  func testDefensiveInputsClampToMinimumBudget() {
    XCTAssertEqual(
      GmailReaderService.batchBudgetSeconds(requestCount: 0, maxConcurrentRequests: 4), 60)
    XCTAssertEqual(
      GmailReaderService.batchBudgetSeconds(requestCount: 2, maxConcurrentRequests: 0), 120)
  }
}

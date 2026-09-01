import XCTest

@testable import Omi_Computer

@MainActor
final class GoalGenerationServiceTests: XCTestCase {
  func testCanonicalAISuggestedSourceIsEligibleForCleanup() {
    XCTAssertTrue(GoalGenerationService.isAIGeneratedSource("ai_suggested"))
  }

  func testReleasedAISourceRemainsEligibleForCleanup() {
    XCTAssertTrue(GoalGenerationService.isAIGeneratedSource("ai"))
  }

  func testUserAndMissingSourcesAreNotEligibleForCleanup() {
    XCTAssertFalse(GoalGenerationService.isAIGeneratedSource("user"))
    XCTAssertFalse(GoalGenerationService.isAIGeneratedSource(nil))
  }
}

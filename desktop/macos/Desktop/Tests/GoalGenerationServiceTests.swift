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

  func testOnboardingGoalCallersUseCanonicalUserSource() throws {
    let sources = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
    let paged = try String(
      contentsOf: sources.appendingPathComponent("Onboarding/OnboardingPagedIntroCoordinator.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(paged.contains("source: \"user\""))
    XCTAssertFalse(paged.contains("source: \"onboarding_step_flow\""))
  }
}

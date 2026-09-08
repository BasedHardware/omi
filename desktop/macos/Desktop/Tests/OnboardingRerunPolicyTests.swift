import XCTest

@testable import Omi_Computer

final class OnboardingRerunPolicyTests: XCTestCase {
  private let payload: [String: Any] = [
    "generation": 1, "min_account_age_days": 7, "active_questions_30d": 8,
  ]
  private func profile(
    age: Int? = 30, questions: Int = 0, screen: Bool = true, mic: Bool = true
  ) -> OnboardingRerunPolicy.Profile {
    .init(
      accountAgeDays: age, questionsLast30Days: questions, screenRecordingGranted: screen,
      microphoneGranted: mic)
  }

  func testLowUsageOldAccountReruns() {
    XCTAssertEqual(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: payload, appliedGeneration: 0, profile: profile(questions: 3)), 1)
  }

  func testActiveUserWithBothPermissionsIsLeftAlone() {
    XCTAssertNil(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: payload, appliedGeneration: 0, profile: profile(questions: 8)))
  }

  func testHeavyUserMissingAPermissionStillReruns() {
    XCTAssertEqual(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: payload, appliedGeneration: 0,
        profile: profile(questions: 40, screen: false)), 1)
  }

  func testAccountsYoungerThanAWeekOrUnknownAgeAreSkipped() {
    // Unknown age counts as brand new, so only a rule with no minimum age fires on it.
    XCTAssertEqual(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: ["generation": 1, "min_account_age_days": 0],
        appliedGeneration: 0, profile: profile(age: nil)), 1)
    XCTAssertNil(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: payload, appliedGeneration: 0, profile: profile(age: 3)))
    XCTAssertNil(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: payload, appliedGeneration: 0, profile: profile(age: nil)))
  }

  func testAppliesAtMostOncePerGenerationAndNeverWhenOff() {
    XCTAssertNil(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: payload, appliedGeneration: 1, profile: profile()))
    XCTAssertNil(
      OnboardingRerunPolicy.generationToApply(
        enabled: false, payload: payload, appliedGeneration: 0, profile: profile()))
    XCTAssertEqual(
      OnboardingRerunPolicy.generationToApply(
        enabled: true, payload: ["generation": 2], appliedGeneration: 1, profile: profile()), 2)
  }

  func testPayloadParsingAcceptsJSONStringObjectAndBareNumber() {
    XCTAssertEqual(
      OnboardingRerunPolicy.Rule.parse(#"{"generation": 3, "active_questions_30d": 4}"#),
      .init(generation: 3, minAccountAgeDays: 7, activeQuestions30d: 4))
    XCTAssertEqual(OnboardingRerunPolicy.Rule.parse(5), .init(generation: 5))
    XCTAssertNil(OnboardingRerunPolicy.Rule.parse("nope"))
    XCTAssertNil(OnboardingRerunPolicy.Rule.parse(nil))
  }
}

import XCTest

@testable import Omi_Computer

final class JITProactivityBudgetTests: XCTestCase {
  func testTemporalPromptLabelsCaptureAndEvaluationSeparately() {
    let capturedAt = Date(timeIntervalSince1970: 1_775_000_000)
    let evaluatedAt = capturedAt.addingTimeInterval(12)
    let temporal = JITProactivityTemporalContext(
      capturedAt: capturedAt,
      evaluatedAt: evaluatedAt,
      timezoneIdentifier: "America/New_York")

    let prompt = temporal.promptSection()

    XCTAssertTrue(prompt.contains("Evidence captured at (UTC):"))
    XCTAssertTrue(prompt.contains("Evaluated at (UTC):"))
    XCTAssertTrue(prompt.contains("Authoritative user timezone: America/New_York"))
    XCTAssertTrue(prompt.contains("Do not make a time-specific claim"))
    XCTAssertNotEqual(capturedAt, evaluatedAt)
  }

  func testMissingTemporalContextDoesNotInventAClock() {
    let temporal = JITProactivityTemporalContext(
      capturedAt: nil, evaluatedAt: nil, timezoneIdentifier: nil)

    let prompt = temporal.promptSection()

    XCTAssertTrue(prompt.contains("Evidence capture time: unavailable"))
    XCTAssertTrue(prompt.contains("Evaluation time: unavailable"))
    XCTAssertTrue(prompt.contains("Authoritative user timezone: unavailable"))
    XCTAssertTrue(prompt.contains("Do not make a time-specific claim"))
  }

  func testSharedFullTurnPromptRetainsAuthoritativeTemporalContext() {
    let temporal = JITProactivityTemporalContext(
      capturedAt: Date(timeIntervalSince1970: 1_775_000_000),
      evaluatedAt: Date(timeIntervalSince1970: 1_775_000_012),
      timezoneIdentifier: "America/New_York")
    let prompt = JITProactivityPromptBuilder.fullTurnPrompt(
      lane: .planned,
      executionPrompt: "Review the deadline",
      currentEvidence: "fact:deadline-1 The deadline is tomorrow.",
      derivedIntent: JITDerivedIntentMatch(entries: []),
      ambientEvidence: "",
      temporalContext: temporal)
    XCTAssertTrue(prompt.contains(temporal.promptSection()))
    XCTAssertTrue(prompt.contains("fact:deadline-1"))
    XCTAssertTrue(prompt.contains("write tools and external actions"))

    let unavailable = JITProactivityPromptBuilder.fullTurnPrompt(
      lane: .ambient,
      executionPrompt: "Review the screen",
      currentEvidence: "fact:screen-1 A draft is open.",
      derivedIntent: JITDerivedIntentMatch(entries: []),
      ambientEvidence: "")
    XCTAssertTrue(unavailable.contains("Trusted temporal context: unavailable"))
    XCTAssertFalse(unavailable.contains("America/New_York"))
  }

  func testBudgetOnlyAttachesForAdvertisedQualificationContract() {
    let executionID = String(repeating: "a", count: 64)
    let budget = JITProactivityAgentBudget(
      contractVersion: JITProactivityAgentBudget.cloudQAContractVersion,
      executionID: executionID)

    XCTAssertNotNil(budget)
    XCTAssertEqual(budget?.maxProviderAttempts, 3)
    XCTAssertEqual(budget?.maxOutputTokensPerAttempt, 2_048)
    XCTAssertEqual(budget?.maxNormalizedInputTokensPerAttempt, 32_768)
    XCTAssertEqual(budget?.maxEstimatedSpendMicroUSD, 50_000)
    XCTAssertNil(JITProactivityAgentBudget(contractVersion: nil, executionID: executionID))
    XCTAssertNil(JITProactivityAgentBudget(contractVersion: "old", executionID: executionID))
  }
}

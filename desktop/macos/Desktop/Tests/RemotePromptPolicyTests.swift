import XCTest

@testable import Omi_Computer

final class RemotePromptPolicyTests: XCTestCase {
  private func spec(
    _ id: String, kind: String = "app_launch", count: Int = 0, type: String = "banner"
  ) -> RemotePromptSpec {
    RemotePromptSpec(
      id: id, type: type, question: "Q?", options: [], ctaLabel: nil, ctaURL: nil,
      triggerKind: kind, triggerCount: count)
  }

  func testAppLaunchPromptIsDueImmediatelyAndOnlyOnce() {
    let s = spec("a")
    XCTAssertEqual(RemotePromptPolicy.duePrompt(specs: [s], resolvedIds: [], questionCount: 0)?.id, "a")
    XCTAssertNil(RemotePromptPolicy.duePrompt(specs: [s], resolvedIds: ["a"], questionCount: 0))
  }

  func testQuestionCountPromptWaitsForItsThreshold() {
    let s = spec("q", kind: "question_count", count: 3)
    XCTAssertNil(RemotePromptPolicy.duePrompt(specs: [s], resolvedIds: [], questionCount: 2))
    XCTAssertEqual(RemotePromptPolicy.duePrompt(specs: [s], resolvedIds: [], questionCount: 3)?.id, "q")
  }

  func testZeroCountQuestionTriggerStillRequiresOneQuestion() {
    let s = spec("q", kind: "question_count", count: 0)
    XCTAssertNil(RemotePromptPolicy.duePrompt(specs: [s], resolvedIds: [], questionCount: 0))
    XCTAssertNotNil(RemotePromptPolicy.duePrompt(specs: [s], resolvedIds: [], questionCount: 1))
  }

  func testUnknownTriggerKindsAreIgnoredNotShownAtLaunch() {
    let s = spec("x", kind: "on_full_moon")
    XCTAssertNil(RemotePromptPolicy.duePrompt(specs: [s], resolvedIds: [], questionCount: 99))
  }

  func testOnePromptAtATimeDeterministicById() {
    let due = RemotePromptPolicy.duePrompt(
      specs: [spec("b"), spec("a")], resolvedIds: [], questionCount: 0)
    XCTAssertEqual(due?.id, "a")
  }
}

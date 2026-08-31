import XCTest

@testable import Omi_Computer

final class InterjectCopyBudgetTests: XCTestCase {
  func testTaskCandidateBudgetIsLongerThanResurface() {
    let task = InterjectCopyBudget.limits(for: "task_candidate")
    let resurface = InterjectCopyBudget.limits(for: "resurface")
    XCTAssertGreaterThan(task.messageLimit, resurface.messageLimit)
    XCTAssertGreaterThan(task.titleLimit, resurface.titleLimit)
  }

  func testBudgetsNeverExceedTheSafetyCeiling() {
    for decision in ["task_candidate", "resurface", "insight", "suggest", "silence", "unknown"] {
      let limits = InterjectCopyBudget.limits(for: decision)
      XCTAssertLessThanOrEqual(limits.titleLimit, InterjectCopyBudget.safetyTitleLimit)
      XCTAssertLessThanOrEqual(limits.messageLimit, InterjectCopyBudget.safetyMessageLimit)
    }
  }

  func testClampedRespectsPerTypeBudgetsWhenProvided() {
    let decision = ContextDirectorDecision(
      decision: "resurface",
      title: String(repeating: "t", count: 120),
      message: String(repeating: "m", count: 600),
      reasoning: "r",
      bucketEntryRefs: [],
      factIDs: [])
    let tightened = decision.clamped(copyBudget: InterjectCopyBudget.limits(for: "resurface"))
    XCTAssertEqual(tightened.title.count, 60)
    XCTAssertEqual(tightened.message.count, 160)
  }

  func testDirectorPromptGainsBudgetsOnlyWhenAsked() {
    let snapshot = ContextBucketSnapshot(
      bucketID: "bucket-interject",
      versionID: 1,
      version: 1,
      header: "header",
      frozenRankedSegment: Data(),
      tail: [],
      validatedFacts: ["fact:1 a fact"],
      notifyWorthiness: 1,
      visitCount: 1)
    let off = ContextProactivityPromptBuilder.directorStablePrompt(snapshot: snapshot)
    let on = ContextProactivityPromptBuilder.directorStablePrompt(
      snapshot: snapshot, includeInterjectCopyBudgets: true)
    XCTAssertFalse(off.contains(InterjectCopyBudget.directorPromptSection))
    XCTAssertTrue(on.contains(InterjectCopyBudget.directorPromptSection))
    XCTAssertTrue(
      off.contains("never convert to or mention UTC."),
      "flag-off prefix must keep today's last contract line")
  }

  func testClampedWithoutBudgetStaysAtTheLegacyCeiling() {
    let decision = ContextDirectorDecision(
      decision: "resurface",
      title: String(repeating: "t", count: 120),
      message: String(repeating: "m", count: 600),
      reasoning: "r",
      bucketEntryRefs: [],
      factIDs: [])
    let legacy = decision.clamped()
    XCTAssertEqual(legacy.title.count, 120)
    XCTAssertEqual(legacy.message.count, 600)
  }
}

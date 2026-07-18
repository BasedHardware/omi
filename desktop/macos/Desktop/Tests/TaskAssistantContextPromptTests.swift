import XCTest

@testable import Omi_Computer

/// Regression coverage for `TaskAssistant.contextEvidencePrompt`.
///
/// Staged (local-only) tasks used to be merged into the id'd ACTIVE TASKS list
/// with a hard-coded `id:0`. The model could echo that back as
/// `duplicate_of:0` / `refines_task:0`, driving a task update against a
/// non-existent backend task. Staged tasks must instead render as id-less
/// "already captured" evidence, so only real backend tasks carry an id the
/// model can target.
final class TaskAssistantContextPromptTests: XCTestCase {
  func testStagedTasksRenderWithoutAnUpdatableId() {
    let context = TaskExtractionContext(
      activeTasks: [(id: Int64(42), description: "Review the PR", priority: "high", relevanceScore: 10)],
      completedTasks: [],
      deletedTasks: [],
      stagedTaskDescriptions: ["Draft the Q3 report"],
      goals: []
    )

    let prompt = TaskAssistant.contextEvidencePrompt(context)

    // Real backend tasks keep their updatable id.
    XCTAssertTrue(prompt.contains("[id:42] Review the PR"))
    // Staged tasks appear as id-less evidence.
    XCTAssertTrue(prompt.contains("ALREADY CAPTURED — STAGED"))
    let stagedLine = prompt.split(separator: "\n").first { $0.contains("Draft the Q3 report") }
    XCTAssertNotNil(stagedLine, "Staged description should be present in the prompt")
    XCTAssertFalse(
      stagedLine?.contains("[id:") ?? true,
      "A staged task must never be rendered with an updatable id")
    // The specific bug signature must be gone entirely.
    XCTAssertFalse(prompt.contains("[id:0]"), "No task may be rendered with the sentinel id 0")
  }

  func testEmptyContextRendersNothing() {
    let context = TaskExtractionContext(
      activeTasks: [], completedTasks: [], deletedTasks: [], stagedTaskDescriptions: [], goals: [])
    XCTAssertEqual(TaskAssistant.contextEvidencePrompt(context), "")
  }
}

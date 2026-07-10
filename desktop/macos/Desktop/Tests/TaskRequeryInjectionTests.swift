import XCTest

@testable import Omi_Computer

/// TASK-06: a server push arriving during an active drag must not clobber the
/// in-flight order — `suppressDatabaseRequery` blocks the SQLite requery. The
/// bridge action `inject_requery_during_drag` runs the real recompute path under
/// a simulated drag and reports the outcome.
final class TaskRequeryInjectionTests: XCTestCase {
  // Note: the end-to-end suppress-during-drag behavior touches the shared
  // TasksStore + SQLite + auth, which is not hermetic for the CI unit lane, so it
  // is exercised at runtime via the `inject_requery_during_drag` bridge action
  // (e2e/SKILL.md §2f). This suite guards the wiring hermetically.
  func testHookIsRegisteredAndInstrumented() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/TasksPage.swift")
    let src = try String(contentsOf: sourceURL, encoding: .utf8)
    for needle in [
      "name: \"inject_requery_during_drag\"",
      "func automationInjectRequeryDuringDrag() async",
      "automationRequeryCount += 1",
      // Non-vacuity: the probe forces the requery branch so a suppressed count is
      // meaningful even with no user filter active.
      "automationForceFilteredRequery = true",
      // Determinism: poll the counter instead of a fixed sleep.
      "waitForRequeryCount(above:",
    ] {
      XCTAssertTrue(src.contains(needle), "TASK-06 hook missing invariant: \(needle)")
    }
    // The recompute guard that the hook exercises must still gate on the flag —
    // this is the actual TASK-06 mechanism; removing it is the regression.
    XCTAssertTrue(src.contains("&& !suppressDatabaseRequery"),
      "recompute requery must remain gated on suppressDatabaseRequery")
    // The counter must live PAST the empty-filter early return (count real DB reads).
    let requeryFn = src.range(of: "private func loadFilteredTasksFromDatabase() async {")!.upperBound
    let guardIdx = src.range(of: "else {\n            filteredFromDatabase = []", range: requeryFn..<src.endIndex)!.lowerBound
    let counterIdx = src.range(of: "automationRequeryCount += 1", range: requeryFn..<src.endIndex)!.lowerBound
    XCTAssertGreaterThan(counterIdx, guardIdx,
      "the requery counter must increment only past the empty-filter early return")
  }
}

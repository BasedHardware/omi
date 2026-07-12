import XCTest

@testable import Omi_Computer

/// Harness seams for the last runtime-blocked hardening rows:
///
/// - TASK-05: `reorder_task flush=false` leaves the production 500ms sortOrder
///   debounce running so rapid reorders provably coalesce into ONE sync (the
///   bridge's unconditional flush was hiding exactly the behavior under test).
/// - CHAT-07: `simulate_system_wake` posts the real `.systemDidWake` signal so the
///   post-wake restart paths run without physically sleeping the machine.
///
/// Both are registry-bound `@MainActor` paths that can't be behaviorally unit-run
/// in the test host, so these pin the wiring; the behavior is the runtime lane
/// (SKILL §2k/§2l).
final class HardeningSeamActionTests: XCTestCase {

  func testReorderTaskExposesFlushParamAndGatesTheFlush() throws {
    let source = try tasksPageSource()
    guard let start = source.range(of: "name: \"reorder_task\"") else {
      return XCTFail("reorder_task registration not found")
    }
    let block = String(source[start.lowerBound...].prefix(2200))
    XCTAssertTrue(
      block.contains("\"flush\""),
      "reorder_task must expose the flush param (TASK-05 debounce-coalescing seam)")
    XCTAssertTrue(
      block.contains("if flush {"),
      "the sortOrder flush must be conditional so flush=false leaves the 500ms debounce live")
    XCTAssertTrue(
      block.contains("flushSortOrderSyncForAutomation()"),
      "the default path must still flush so existing recipes keep deterministic SQLite reads")
    XCTAssertTrue(
      block.contains("(params[\"flush\"] ?? \"true\")"),
      "flush must default to true — only an explicit flush=false opts into the debounce path")
  }

  func testSimulateSystemWakeIsRegisteredNonProdGatedAndPostsTheRealSignal() throws {
    let source = try bridgeSource()
    guard let start = source.range(of: "name: \"simulate_system_wake\"") else {
      return XCTFail("simulate_system_wake registration not found")
    }
    let block = String(source[start.lowerBound...].prefix(1400))
    XCTAssertTrue(
      block.contains("guard AppBuild.isNonProduction"),
      "simulate_system_wake must refuse to run on production bundles")
    // The wake chain's top is NSWorkspace.didWakeNotification on the WORKSPACE
    // center. RealtimeHubController observes that center directly — a default-center
    // .systemDidWake post would silently miss it (verifier finding, Wave 19).
    XCTAssertTrue(
      block.contains("NSWorkspace.shared.notificationCenter.post"),
      "the action must post on the workspace notification center (RealtimeHub observes it directly)")
    XCTAssertTrue(
      block.contains("NSWorkspace.didWakeNotification"),
      "the action must post the real top-of-chain wake signal, not the .systemDidWake re-broadcast")
    XCTAssertTrue(
      block.contains("MainActor.run"),
      "the notification must post on the main actor like the real observers expect")
  }

  // MARK: - Helpers

  private func tasksPageSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/TasksPage.swift")
    // omi-test-quality: source-inspection -- static contract: the reorder_task flush seam must stay param-gated with a flush=true default; the action runs through the registry against the @MainActor store and cannot be behaviorally unit-run in the test host. Coalescing behavior is proven on the runtime lane (SKILL §2k).
    return try String(contentsOf: url, encoding: .utf8)
  }

  private func bridgeSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/DesktopAutomationBridge.swift")
    // omi-test-quality: source-inspection -- static contract: simulate_system_wake must stay registered, non-prod gated, and posting the real .systemDidWake signal; the action can't be behaviorally unit-run (registry + MainActor notification). Post-wake behavior is proven on the runtime lane (SKILL §2l).
    return try String(contentsOf: url, encoding: .utf8)
  }
}

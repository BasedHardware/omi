import XCTest
@testable import Omi_Computer

final class AgentContinuityGauntletTests: XCTestCase {
  func testGauntletRunnerFilesExist() throws {
    let desktopDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let script = desktopDir.appendingPathComponent("scripts/agent-continuity-gauntlet.sh")
    let driver = desktopDir.appendingPathComponent("scripts/agent-continuity-gauntlet-lib.py")
    XCTAssertTrue(FileManager.default.isExecutableFile(atPath: script.path), script.path)
    XCTAssertTrue(FileManager.default.fileExists(atPath: driver.path), driver.path)
  }

  func testGauntletAutomationHooksRegistered() throws {
    let desktopDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let bridgeSource = try String(
      contentsOf: desktopDir
        .appendingPathComponent("Desktop/Sources/DesktopAutomationBridge.swift"),
      encoding: .utf8
    )
    let required = [
      "ask",
      "main_chat_snapshot",
      "wait_main_chat_idle",
      "agent_runtime_evidence",
      "ask_main_chat",
      "ask_main_chat_no_wait",
      "main_chat_busy_state",
      "coordinator_awareness_snapshot",
      "swap_test_owner",
      "restore_test_owner",
      "clear_owner_surface_state",
      "kernel_turn_tail",
    ]
    for name in required {
      XCTAssertTrue(
        bridgeSource.contains("name: \"\(name)\""),
        "missing automation action \(name)"
      )
    }
    let hubSource = try String(
      contentsOf: desktopDir
        .appendingPathComponent("Desktop/Sources/FloatingControlBar/RealtimeHubController.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(hubSource.contains("name: \"ptt_test_turn\""))
    let providerSource = try String(
      contentsOf: desktopDir
        .appendingPathComponent("Desktop/Sources/Providers/ChatProvider.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(providerSource.contains("automationMainChatSnapshot"))
    XCTAssertTrue(providerSource.contains("automationSwapTestOwner"))
    XCTAssertTrue(providerSource.contains("automationKernelTurnTail"))
    XCTAssertTrue(providerSource.contains("automationClearOwnerSurfaceState"))
    XCTAssertTrue(providerSource.contains("RuntimeOwnerIdentity.applyAutomationOwnerOverride"))
    XCTAssertTrue(providerSource.contains("RuntimeOwnerIdentity.clearAutomationOwnerOverride"))
  }

  func testResilienceSuiteIsWiredIntoCanonicalGauntlet() throws {
    let desktopDir = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let scriptSource = try String(
      contentsOf: desktopDir.appendingPathComponent("scripts/agent-continuity-gauntlet.sh"),
      encoding: .utf8
    )
    let driverSource = try String(
      contentsOf: desktopDir.appendingPathComponent("scripts/agent-continuity-gauntlet-lib.py"),
      encoding: .utf8
    )
    let bridgeSource = try String(
      contentsOf: desktopDir
        .appendingPathComponent("Desktop/Sources/DesktopAutomationBridge.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(driverSource.contains("\"resilience\""))
    XCTAssertTrue(driverSource.contains("\"all\": {\"continuity\", \"agents\", \"owner\", \"prompts\", \"resilience\"}"))
    XCTAssertTrue(driverSource.contains("SUITE_NAMES = {\"continuity\", \"agents\", \"owner\", \"prompts\", \"resilience\"}"))
    XCTAssertTrue(driverSource.contains("def run_resilience_suite(self) -> None"))
    XCTAssertTrue(driverSource.contains("if \"resilience\" in self.suites"))
    XCTAssertTrue(driverSource.contains("self.run_resilience_suite()"))
    XCTAssertTrue(driverSource.contains("resilience-diagnostics.jsonl"))
    XCTAssertTrue(driverSource.contains("schema_version"))
    XCTAssertTrue(driverSource.contains("terminal_reason"))
    XCTAssertTrue(driverSource.contains("resilience_terminal_reason_counts"))
    XCTAssertTrue(driverSource.contains("resilience_forbidden_terminal_reasons"))
    XCTAssertTrue(driverSource.contains("skipped_missing_action"))
    XCTAssertTrue(driverSource.contains("\"skipped_missing_action\""))
    // Forbidden taxonomy still lists skipped_unimplemented_action; R3 no longer emits it.
    XCTAssertTrue(driverSource.contains("\"skipped_unimplemented_action\""))
    XCTAssertTrue(driverSource.contains("hold_completed_early"))
    XCTAssertTrue(driverSource.contains("hold_busy_ms"))
    XCTAssertTrue(driverSource.contains("ask_main_chat_no_wait"))
    XCTAssertTrue(driverSource.contains("main_chat_busy_state"))
    XCTAssertTrue(driverSource.contains("run_resilience_r3_race_policy"))
    XCTAssertTrue(driverSource.contains("Objective: track marker"))
    XCTAssertTrue(bridgeSource.contains("hold_busy_ms"))
    XCTAssertTrue(bridgeSource.contains("harnessBusyUntil"))
    XCTAssertTrue(driverSource.contains("continuity_contract_self_check_failures"))
    XCTAssertTrue(driverSource.contains("testStageOptimisticThenApplyPromotesInPlaceWithoutDuplicate"))
    XCTAssertTrue(driverSource.contains("testMainAndFloatingAutomationSnapshotsAliasSameTimeline"))
    XCTAssertTrue(driverSource.contains("testHydratePreferencePrefersRunThenSessionThenPill"))
    XCTAssertTrue(driverSource.contains("--suite resilience"))

    XCTAssertTrue(scriptSource.contains("--suite resilience"))
    XCTAssertTrue(scriptSource.contains("--suite all"))
    XCTAssertTrue(scriptSource.contains("Release-candidate manual QA"))

    let harnessSource = try String(
      contentsOf: desktopDir.appendingPathComponent("scripts/agent-logic-harness.sh"),
      encoding: .utf8
    )
    XCTAssertTrue(harnessSource.contains("KernelTurnRecordedProjectionTests"))
    XCTAssertTrue(harnessSource.contains("ChatTimelineContinuityTests"))
    XCTAssertTrue(harnessSource.contains("FloatingControlBarStateTests"))
  }

  @MainActor
  func testAutomationActionDescriptorsExposeDiscoveryMetadata() throws {
    let registry = DesktopAutomationActionRegistry.shared
    registry.register(
      name: "__metadata_contract_test__",
      summary: "Read test-only metadata",
      params: ["limit"],
      category: "read",
      surfaces: ["test_surface"],
      safety: "read_only",
      sideEffects: [],
      examples: ["./scripts/omi-ctl action __metadata_contract_test__ limit=1"]
    ) { _ in
      ["ok": "true"]
    }
    defer { registry.unregister("__metadata_contract_test__") }

    let descriptor = try XCTUnwrap(
      registry.descriptors().first { $0.name == "__metadata_contract_test__" }
    )
    XCTAssertEqual(descriptor.summary, "Read test-only metadata")
    XCTAssertEqual(descriptor.params, ["limit"])
    XCTAssertEqual(descriptor.category, "read")
    XCTAssertEqual(descriptor.surfaces, ["test_surface"])
    XCTAssertEqual(descriptor.safety, "read_only")
    XCTAssertEqual(descriptor.examples, ["./scripts/omi-ctl action __metadata_contract_test__ limit=1"])
    XCTAssertTrue(descriptor.preferSemantic)
  }

  func testAutomationActionDescriptorInfersUsefulMetadataForBuiltins() throws {
    let snapshot = DesktopAutomationActionDescriptor(
      name: "main_chat_snapshot",
      summary: "Export main-chat state",
      params: ["limit"]
    )
    XCTAssertEqual(snapshot.category, "read")
    XCTAssertEqual(snapshot.surfaces, ["main_chat"])
    XCTAssertEqual(snapshot.safety, "read_only")
    XCTAssertEqual(snapshot.examples, ["./scripts/omi-ctl action main_chat_snapshot limit=<value>"])

    let capture = DesktopAutomationActionDescriptor(
      name: "capture_floating_bar_png",
      summary: "Capture the floating bar",
      params: ["path"]
    )
    XCTAssertEqual(capture.category, "capture")
    XCTAssertEqual(capture.surfaces, ["floating_bar"])
    XCTAssertEqual(capture.safety, "local_artifact")
    XCTAssertEqual(capture.sideEffects, ["writes local artifact file"])
  }
}

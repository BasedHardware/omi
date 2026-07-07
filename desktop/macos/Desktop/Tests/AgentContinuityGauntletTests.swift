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
      "main_chat_snapshot",
      "wait_main_chat_idle",
      "agent_runtime_evidence",
      "ask_main_chat",
      "coordinator_awareness_snapshot",
      "swap_test_owner",
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

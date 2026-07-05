import XCTest

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
}

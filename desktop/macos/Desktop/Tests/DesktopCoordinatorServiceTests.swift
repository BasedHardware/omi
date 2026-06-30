import XCTest

final class DesktopCoordinatorServiceTests: XCTestCase {
  func testCoordinatorServiceUsesRuntimeControlToolsOnly() throws {
    let source = try sourceFile("Chat/DesktopCoordinatorService.swift")

    XCTAssertTrue(source.contains("build_desktop_awareness_snapshot"))
    XCTAssertTrue(source.contains("list_desktop_action_queue"))
    XCTAssertTrue(source.contains("get_desktop_open_loops"))
    XCTAssertTrue(source.contains("route_desktop_intent"))
    XCTAssertTrue(source.contains("create_desktop_dispatch"))
    XCTAssertTrue(source.contains("resolve_desktop_dispatch"))
    XCTAssertTrue(source.contains("runtime.directControlTool"))
  }

  func testCoordinatorServiceDoesNotOwnDispatchOrLifecycleAuthority() throws {
    let source = try sourceFile("Chat/DesktopCoordinatorService.swift")

    XCTAssertFalse(source.contains("createDebugDispatch"))
    XCTAssertFalse(source.contains("resolveDebugDispatch"))
    XCTAssertFalse(source.contains("debug_dispatch_"))
    XCTAssertFalse(source.contains("recordLocalSuccess"))
    XCTAssertFalse(source.contains("recordPresentationCompletion"))
  }

  func testMainChatUsesContextPacketInsteadOfRawPromptOnly() throws {
    let source = try sourceFile("Providers/ChatProvider.swift")

    XCTAssertTrue(source.contains("buildMainChatContextPacketPrompt("))
    XCTAssertTrue(source.contains("build_desktop_context_packet"))
    XCTAssertTrue(source.contains("DesktopContextPacket"))
    XCTAssertTrue(source.contains("\"sourceKind\": \"chat_surface\""))
    XCTAssertTrue(source.contains("prompt: promptForBridge"))
    XCTAssertTrue(source.contains("\"screenshotImages\": \"dispatch_required\""))
  }

  func testRealtimeStatusReadsCoordinatorOpenLoops() throws {
    let source = try sourceFile("FloatingControlBar/RealtimeHubController.swift")

    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.openLoopsJSON()"))
    XCTAssertTrue(source.contains("coordinator_open_loops"))
    XCTAssertTrue(source.contains("TaskAgentStatusRegistry.shared.combinedSummary()"))
  }

  func testTaskRoutingUsesExactExternalTaskReference() throws {
    let source = try sourceFile("Chat/DesktopCoordinatorService.swift")

    XCTAssertTrue(source.contains("externalRefKind: stringValue(session[\"externalRefKind\"])"))
    XCTAssertTrue(source.contains("externalRefId: stringValue(session[\"externalRefId\"])"))
    XCTAssertTrue(source.contains("$0.externalRefKind == \"task\" && $0.externalRefId == taskId"))
    XCTAssertFalse(source.contains("sessionId?.contains(taskId)"))
  }

  func testLocalAgentAPIRejectsUnexpectedHostAndOrigin() throws {
    let source = try sourceFile("LocalAgentAPIServer.swift")

    XCTAssertTrue(source.contains("acceptsLoopbackHostAndOrigin"))
    XCTAssertTrue(source.contains("invalid_host_or_origin"))
    XCTAssertTrue(source.contains("\"127.0.0.1:\\(LocalAgentAPISettings.port)\""))
    XCTAssertTrue(source.contains("\"localhost:\\(LocalAgentAPISettings.port)\""))
    XCTAssertTrue(source.contains("\"[::1]:\\(LocalAgentAPISettings.port)\""))
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let url = root.appendingPathComponent("Sources").appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }
}

import XCTest

@testable import Omi_Computer

@MainActor
final class ChatToolExecutorSpawnAgentTests: XCTestCase {
  private let permissionTypes = [
    ("screen_recording", "Screen Recording"),
    ("microphone", "microphone"),
    ("notifications", "notification permission"),
    ("accessibility", "Accessibility permission"),
    ("automation", "Automation permission"),
    ("full_disk_access", "Full Disk Access"),
  ]

  func testChatPermissionDelegationsRouteToCanonicalNativeExecutor() {
    for (type, phrase) in permissionTypes {
      XCTAssertEqual(
        ChatToolExecutor.permissionExecutionRoute(
          toolName: "spawn_agent",
          arguments: ["brief": "Request \(phrase) for Omi."]
        ),
        .directNative(toolName: "request_permission", type: type, recoveredFromDelegation: true)
      )
      XCTAssertEqual(
        ChatToolExecutor.permissionExecutionRoute(
          toolName: "spawn_agent",
          arguments: ["brief": "Check whether Omi has \(phrase) granted."]
        ),
        .directNative(toolName: "check_permission_status", type: type, recoveredFromDelegation: true)
      )
    }

    for brief in [
      "Request Omi Screen Recording permission.",
      "Request Omi microphone permission.",
    ] {
      let type = brief.contains("Screen Recording") ? "screen_recording" : "microphone"
      XCTAssertEqual(
        ChatToolExecutor.permissionExecutionRoute(
          toolName: "spawn_agent",
          arguments: ["brief": brief],
          originatingUserText: brief
        ),
        .directNative(
          toolName: "request_permission", type: type, recoveredFromDelegation: true)
      )
    }
  }

  func testChatDirectPermissionToolsUseNativeRoute() {
    for (type, _) in permissionTypes {
      for toolName in ["check_permission_status", "request_permission"] {
        XCTAssertEqual(
          ChatToolExecutor.permissionExecutionRoute(
            toolName: toolName,
            arguments: ["type": type]
          ),
          .directNative(toolName: toolName, type: type, recoveredFromDelegation: false)
        )
      }
    }

    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "check_permission_status"),
      .checkPermissionStatus)
    XCTAssertEqual(
      GeneratedToolExecutors.chatDispatch(for: "request_permission"),
      .requestPermission)
  }

  func testPermissionDelegationWithoutLocalTargetStaysDelegated() {
    for brief in [
      "Request Screen Recording permission.",
      "Check microphone permission status.",
      "Research how permission prompts work.",
    ] {
      XCTAssertEqual(
        ChatToolExecutor.permissionExecutionRoute(
          toolName: "spawn_agent", arguments: ["brief": brief]),
        .delegate
      )
    }
  }

  func testExplicitOtherAppPermissionTargetCannotUseOmiNativeTools() async {
    for toolName in ["check_permission_status", "request_permission"] {
      for (type, userText) in [
        ("screen_recording", "Request Screen Recording permission for Chrome."),
        ("microphone", "Check whether Zoom has microphone permission."),
        ("notifications", "Request notification permission for Slack."),
        ("screen_recording", "Does Chromium have Screen Recording access?"),
        ("screen_recording", "Check Google Chrome Screen Recording permission."),
        ("microphone", "Allow Microsoft Teams to use microphone access."),
        ("screen_recording", "Could Omi check Chromium's Screen Recording permission?"),
        (
          "screen_recording",
          "Omi, can you tell me whether Screen Recording permission is enabled for Google Chrome?"
        ),
        ("microphone", "Omi, tell me if Google Chrome is allowed microphone access."),
      ] {
        let arguments: [String: Any] = ["type": type]
        XCTAssertEqual(
          ChatToolExecutor.permissionExecutionRoute(
            toolName: toolName,
            arguments: arguments,
            originatingUserText: userText),
          .rejectExternalTarget
        )
        let result = await ChatToolExecutor.execute(
          ToolCall(name: toolName, arguments: arguments, thoughtSignature: nil),
          originatingUserText: userText)
        XCTAssertTrue(result.contains("permission_target_not_omi"), result)
      }
    }
  }

  func testSchemaRealisticDirectPermissionCallsAllowOmiOrUnspecifiedTarget() {
    let userTexts: [String?] = [
      nil,
      "Request Omi Screen Recording permission.",
      "Allow this app to use the microphone.",
      "Tell me if Screen Recording permission is enabled.",
    ]
    for userText in userTexts {
      XCTAssertEqual(
        ChatToolExecutor.permissionExecutionRoute(
          toolName: "request_permission",
          arguments: ["type": "screen_recording"],
          originatingUserText: userText),
        .directNative(
          toolName: "request_permission", type: "screen_recording", recoveredFromDelegation: false),
        "Unexpected route for originating text: \(userText ?? "<none>")"
      )
    }
  }

  func testExplicitOtherAppPermissionDelegationDoesNotRedirectToOmi() {
    for brief in [
      "Request Screen Recording permission for Chrome.",
      "Check whether Zoom has microphone permission granted.",
      "Does Slack have notification permission?",
      "Request Screen Recording permission for Chromium.",
      "Check whether Google Chrome has microphone permission granted.",
      "Allow Microsoft Teams to use microphone access.",
    ] {
      XCTAssertEqual(
        ChatToolExecutor.permissionExecutionRoute(
          toolName: "spawn_agent", arguments: ["brief": brief]),
        .delegate
      )
    }
  }

  func testTrustedOtherAppUserTurnOverridesMalformedLocalDelegationBrief() {
    let route = ChatToolExecutor.permissionExecutionRoute(
      toolName: "spawn_agent",
      arguments: ["brief": "Request Screen Recording permission for Omi."],
      originatingUserText: "Request Screen Recording permission for Chromium.")

    XCTAssertEqual(route, .delegate)
    XCTAssertFalse(route.recoversMalformedDelegation)
  }

  func testExecutionContextSuppliesOriginatingUserTextForPermissionRouting() async {
    let route = await ChatToolExecutor.withOriginatingUserText(
      "Request Omi Screen Recording permission."
    ) {
      ChatToolExecutor.permissionExecutionRoute(
        toolName: "spawn_agent",
        arguments: ["brief": "Request Screen Recording permission."],
        originatingUserText: ChatToolExecutor.effectiveOriginatingUserText(nil))
    }

    XCTAssertEqual(
      route,
      .directNative(toolName: "request_permission", type: "screen_recording", recoveredFromDelegation: true))
  }

  func testFloatingPillCannotSpawnNestedFloatingPill() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "spawn_agent",
      arguments: ["brief": "Sleep for 10 seconds", "title": "Sleep Agent"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingClientScope: "floating-pill")

    XCTAssertTrue(result.contains("unavailable from an existing floating background agent"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testChatSpawnAgentRejectsEmptyObjectiveBeforeSpawning() async {
    let before = AgentPillsManager.shared.pills.count
    let toolCall = ToolCall(
      name: "spawn_agent",
      arguments: ["title": "New Search"],
      thoughtSignature: nil)

    let result = await ChatToolExecutor.execute(
      toolCall,
      originatingChatMode: .act,
      originatingClientScope: nil)

    XCTAssertTrue(result.contains("Missing objective"))
    XCTAssertEqual(AgentPillsManager.shared.pills.count, before)
  }

  func testChatSpawnAgentRoutesThroughCoordinatorSpawn() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent("Providers/ChatToolExecutor.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("DesktopCoordinatorService.shared.spawnAgent("))
    XCTAssertTrue(source.contains("AgentPillsManager.shared.upsertSpawnedPill("))
    XCTAssertTrue(source.contains("refreshProjectedPillsFromKernel"))
    XCTAssertFalse(source.contains("AgentPillsManager.shared.spawnFromUserQuery("))
  }
}

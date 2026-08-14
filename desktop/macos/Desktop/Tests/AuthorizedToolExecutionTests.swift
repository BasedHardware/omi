import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class AuthorizedToolExecutionTests: XCTestCase {
  func testParsesKernelAuthorizedBackgroundExecutionWithoutRequestIdentity() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(toolName: "get_memories"),
      currentOwnerID: "owner-1")

    XCTAssertEqual(command.invocationID, "invoke-1")
    XCTAssertEqual(command.runID, "run-1")
    XCTAssertEqual(command.attemptID, "attempt-1")
    XCTAssertEqual(command.canonicalToolName, "get_memories")
  }

  func testAliasResolvesThroughGeneratedManifest() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(toolName: "search_screen_history"),
      currentOwnerID: "owner-1")

    XCTAssertEqual(command.canonicalToolName, "semantic_search")
  }

  func testChatFirstToolRequiresMainChatCapabilityAndDynamicManifest() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(
        toolName: "render_chat_blocks",
        overrides: [
          "manifestDigest": GeneratedToolExecutors.chatFirstManifestDigest,
          "surfaceKind": "main_chat",
          "chatFirstControlGeneration": 7,
        ]),
      currentOwnerID: "owner-1")

    XCTAssertEqual(command.canonicalToolName, "render_chat_blocks")
    XCTAssertEqual(command.chatFirstControlGeneration, 7)

    let ordinaryChatFirstTool = try AuthorizedToolExecution.parse(
      payload(
        toolName: "get_memories",
        overrides: [
          "manifestDigest": GeneratedToolExecutors.chatFirstManifestDigest,
          "surfaceKind": "main_chat",
          "chatFirstControlGeneration": 7,
        ]),
      currentOwnerID: "owner-1")
    XCTAssertEqual(ordinaryChatFirstTool.canonicalToolName, "get_memories")
    XCTAssertEqual(ordinaryChatFirstTool.chatFirstControlGeneration, 7)

    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(
          toolName: "render_chat_blocks",
          overrides: [
            "manifestDigest": GeneratedToolExecutors.chatFirstManifestDigest,
            "surfaceKind": "main_chat",
          ]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .invalidChatFirstCapability)
    }
    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(
          overrides: [
            "manifestDigest": GeneratedToolExecutors.chatFirstManifestDigest,
            "surfaceKind": "floating_chat",
            "chatFirstControlGeneration": 7,
          ]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .invalidChatFirstCapability)
    }
  }

  func testWrongOwnerAndManifestFailClosed() {
    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(payload(), currentOwnerID: "owner-other")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .wrongOwner)
    }
    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(overrides: ["manifestVersion": GeneratedToolExecutors.manifestVersion + 1]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .staleManifest)
    }
    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(overrides: ["manifestDigest": "sha256:stale"]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .staleManifest)
    }
  }

  func testOwnerFenceRequiresBothRuntimeAndAuthenticatedOwner() {
    let suiteName = "AuthorizedToolExecutionTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer {
      defaults.removePersistentDomain(forName: suiteName)
    }

    defaults.set("owner-a", forKey: DefaultsKey.authUserId.rawValue)
    defaults.removeObject(forKey: DefaultsKey.automationOwnerOverride.rawValue)
    XCTAssertTrue(
      AuthorizedToolExecution.isOwnerCurrent(
        "owner-a",
        defaults: defaults,
        allowAutomationOverride: true))

    defaults.set("owner-b", forKey: DefaultsKey.automationOwnerOverride.rawValue)
    XCTAssertFalse(
      AuthorizedToolExecution.isOwnerCurrent(
        "owner-a",
        defaults: defaults,
        allowAutomationOverride: true))

    defaults.set("owner-b", forKey: DefaultsKey.authUserId.rawValue)
    defaults.set("owner-a", forKey: DefaultsKey.automationOwnerOverride.rawValue)
    XCTAssertFalse(
      AuthorizedToolExecution.isOwnerCurrent(
        "owner-a",
        defaults: defaults,
        allowAutomationOverride: true))
  }

  func testRealtimeHubExecutorParsesForScopedAuthorizedHandler() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(
        toolName: "get_tasks",
        overrides: ["surfaceKind": "realtime_voice"]),
      currentOwnerID: "owner-1")

    XCTAssertEqual(command.canonicalToolName, "get_tasks")
    XCTAssertEqual(command.executor, .realtimeHub)
  }

  func testRealtimeHandlerRejectionUsesExactFailedLedgerWireTuple() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(
        toolName: "get_tasks",
        overrides: ["surfaceKind": "realtime_voice"]),
      currentOwnerID: "owner-1")
    let rejection = #"{"ok":false,"error":{"code":"stale_realtime_tool_authorization"}}"#

    let failed = AgentRuntimeProcess.authorizedToolExecutionResultWireMessage(
      command: command,
      executionResult: .failed(rejection))

    XCTAssertEqual(
      Set(failed.keys),
      Set([
        "type", "protocolVersion", "invocationId", "ownerId", "sessionId", "runId",
        "attemptId", "profileGeneration", "manifestVersion", "manifestDigest",
        "daemonBootEpoch", "executionGeneration", "inputHash", "outcome", "result",
      ]))
    XCTAssertEqual(failed["type"] as? String, "authorized_tool_execution_result")
    XCTAssertEqual(failed["invocationId"] as? String, command.invocationID)
    XCTAssertEqual(failed["ownerId"] as? String, command.ownerID)
    XCTAssertEqual(failed["sessionId"] as? String, command.sessionID)
    XCTAssertEqual(failed["runId"] as? String, command.runID)
    XCTAssertEqual(failed["attemptId"] as? String, command.attemptID)
    XCTAssertEqual(failed["profileGeneration"] as? Int, command.profileGeneration)
    XCTAssertEqual(failed["manifestVersion"] as? Int, command.manifestVersion)
    XCTAssertEqual(failed["manifestDigest"] as? String, command.manifestDigest)
    XCTAssertEqual(failed["daemonBootEpoch"] as? String, command.daemonBootEpoch)
    XCTAssertEqual(failed["executionGeneration"] as? Int, command.executionGeneration)
    XCTAssertEqual(failed["inputHash"] as? String, command.inputHash)
    XCTAssertEqual(failed["outcome"] as? String, "failed")
    XCTAssertEqual(failed["result"] as? String, rejection)
  }

  func testRealtimeHandlerSuccessUsesSucceededLedgerOutcome() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(
        toolName: "get_tasks",
        overrides: ["surfaceKind": "realtime_voice"]),
      currentOwnerID: "owner-1")

    let succeeded = AgentRuntimeProcess.authorizedToolExecutionResultWireMessage(
      command: command,
      executionResult: .succeeded("No tasks due today."))

    XCTAssertEqual(succeeded["outcome"] as? String, "succeeded")
    XCTAssertEqual(succeeded["result"] as? String, "No tasks due today.")
  }

  func testRealtimeHandlerOwnershipRejectsStaleTurnAndInvocation() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(
        toolName: "get_tasks",
        overrides: ["surfaceKind": "realtime_voice"]),
      currentOwnerID: "owner-1")
    let turnID = VoiceTurnID()
    let effectIdentity = VoiceEffectIdentity(turnID: turnID, effectID: 7)
    let source = NSObject()
    let binding = ExternalSurfaceRunBinding(
      ownerID: "owner-1",
      sessionID: "session-1",
      turnID: turnID.rawValue.uuidString.lowercased(),
      runID: "run-1",
      attemptID: "attempt-1",
      duplicate: false)
    let invocation = RealtimeAuthorizedToolInvocation(
      invocationID: "invoke-1",
      binding: binding,
      turnID: turnID,
      callID: VoiceToolCallID("call-1"),
      effectIdentity: effectIdentity,
      canonicalToolName: "get_tasks",
      inputHash: command.inputHash,
      sourceObjectID: ObjectIdentifier(source),
      turnEpoch: 3)

    XCTAssertTrue(
      RealtimeAuthorizedToolOwnership.accepts(
        command: command,
        invocation: invocation,
        activeTurnID: turnID,
        activeToolIdentity: effectIdentity,
        activeSourceObjectID: ObjectIdentifier(source),
        currentTurnEpoch: 3))
    XCTAssertFalse(
      RealtimeAuthorizedToolOwnership.accepts(
        command: command,
        invocation: invocation,
        activeTurnID: VoiceTurnID(),
        activeToolIdentity: effectIdentity,
        activeSourceObjectID: ObjectIdentifier(source),
        currentTurnEpoch: 3))

    let staleInvocationCommand = try AuthorizedToolExecution.parse(
      payload(
        toolName: "get_tasks",
        overrides: [
          "surfaceKind": "realtime_voice",
          "invocationId": "invoke-stale",
        ]),
      currentOwnerID: "owner-1")
    XCTAssertFalse(
      RealtimeAuthorizedToolOwnership.accepts(
        command: staleInvocationCommand,
        invocation: invocation,
        activeTurnID: turnID,
        activeToolIdentity: effectIdentity,
        activeSourceObjectID: ObjectIdentifier(source),
        currentTurnEpoch: 3))
  }

  func testNonIdempotentWriteCanNeverAdvertiseSafeRetry() {
    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(overrides: [
          "effectClass": "non_idempotent_write",
          "retryPolicy": "safe_retry",
        ]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .invalidRetryPolicy)
    }
  }

  func testInputHashMismatchFailsClosed() {
    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(overrides: ["inputHash": "sha256:wrong"]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .inputHashMismatch)
    }
  }

  func testPermissionDelegationRecoveryIsBoundedToNativePermissionTools() throws {
    let command = try AuthorizedToolExecution.parse(
      payload(
        toolName: "request_permission",
        overrides: ["policyRecovery": "permission_delegation_to_native"]),
      currentOwnerID: "owner-1")
    XCTAssertEqual(command.policyRecovery, .permissionDelegationToNative)

    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(overrides: ["policyRecovery": "permission_delegation_to_native"]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .invalidPolicyRecovery)
    }
    XCTAssertThrowsError(
      try AuthorizedToolExecution.parse(
        payload(
          toolName: "request_permission",
          overrides: ["policyRecovery": "unbounded_recovery"]),
        currentOwnerID: "owner-1")
    ) { error in
      XCTAssertEqual(error as? AuthorizedToolExecution.Rejection, .invalidPolicyRecovery)
    }
  }

  func testCanonicalInputHashMatchesKernelNestedJSONFixture() throws {
    let input: [String: Any] = [
      "z": [3, ["é": "<tag>", "a": true], NSNull()],
      "a": ["two": 2, "one": "line\nbreak"],
    ]

    XCTAssertEqual(
      try AuthorizedToolExecution.inputHash(for: input),
      "sha256:6f6a5fc2f37f5512e07808cd81aafc5b868c5573cff37ac67205713dd079f870"
    )
  }

  private func payload(
    toolName: String = "get_memories",
    overrides: [String: Any] = [:]
  ) -> [String: Any] {
    let input: [String: Any] = ["query": "memory"]
    var value: [String: Any] = [
      "type": "authorized_tool_execution",
      "protocolVersion": 2,
      "invocationId": "invoke-1",
      "ownerId": "owner-1",
      "sessionId": "session-1",
      "runId": "run-1",
      "attemptId": "attempt-1",
      "profileGeneration": 2,
      "manifestVersion": GeneratedToolExecutors.manifestVersion,
      "manifestDigest": GeneratedToolExecutors.manifestDigest,
      "daemonBootEpoch": "boot-1",
      "executionGeneration": 3,
      "capabilityRef": "capability-1",
      "toolName": toolName,
      "input": input,
      "inputHash": try! AuthorizedToolExecution.inputHash(for: input),
      "effectClass": "read_only",
      "retryPolicy": "safe_retry",
      "surfaceKind": "background_agent",
      "externalRefKind": NSNull(),
      "externalRefId": NSNull(),
      "originatingUserText": "Find a memory",
      "precedingAssistantText": NSNull(),
      "runMode": "act",
      "chatMode": NSNull(),
    ]
    for (key, replacement) in overrides {
      value[key] = replacement
    }
    return value
  }
}

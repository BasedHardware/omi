import XCTest

@testable import Omi_Computer

private struct TokenRefreshAuthorization: Equatable, Sendable {
  let ownerID: String
  let generation: UInt64
}

private actor DelayedOwnerBoundTokenRefreshHarness {
  private var ownerId: String? = "owner-a"
  private var generation: UInt64 = 0
  private var fetchStarted = false
  private var fetchStartedWaiter: CheckedContinuation<Void, Never>?
  private var pendingFetch: CheckedContinuation<String, Error>?
  private(set) var fetchedOwnerIds: [String] = []
  private(set) var sentToken: String?
  private(set) var sentOwnerId: String?

  func captureAuthorization() -> TokenRefreshAuthorization? {
    guard let ownerId else { return nil }
    return TokenRefreshAuthorization(ownerID: ownerId, generation: generation)
  }

  func isAuthorizationCurrent(_ authorization: TokenRefreshAuthorization) -> Bool {
    ownerId == authorization.ownerID && generation == authorization.generation
  }

  func fetchAuthHeader(expectedOwnerId: String) async throws -> String {
    fetchedOwnerIds.append(expectedOwnerId)
    return try await withCheckedThrowingContinuation { continuation in
      pendingFetch = continuation
      fetchStarted = true
      fetchStartedWaiter?.resume()
      fetchStartedWaiter = nil
    }
  }

  func waitUntilFetchStarted() async {
    if fetchStarted { return }
    await withCheckedContinuation { continuation in
      fetchStartedWaiter = continuation
    }
  }

  func replaceOwnerASessionAndCompleteFetch(header: String) -> Bool {
    ownerId = nil
    generation &+= 1
    ownerId = "owner-a"
    generation &+= 1
    guard let pendingFetch else { return false }
    self.pendingFetch = nil
    pendingFetch.resume(returning: header)
    return true
  }

  func recordSend(token: String, ownerId: String) -> Bool {
    sentToken = token
    sentOwnerId = ownerId
    return true
  }

  func snapshot() -> (fetchedOwnerIds: [String], sentToken: String?, sentOwnerId: String?) {
    (fetchedOwnerIds, sentToken, sentOwnerId)
  }
}

private actor GatedRuntimeStartupHarness {
  private var launchCount = 0
  private var launchStarted = false
  private var launchStartedWaiter: CheckedContinuation<Void, Never>?
  private var releaseContinuation: CheckedContinuation<Void, Never>?

  func launch(receipt: UInt64) async -> UInt64 {
    launchCount += 1
    launchStarted = true
    launchStartedWaiter?.resume()
    launchStartedWaiter = nil
    await withCheckedContinuation { continuation in
      releaseContinuation = continuation
    }
    return receipt
  }

  func waitUntilLaunchStarted() async {
    if launchStarted { return }
    await withCheckedContinuation { continuation in
      launchStartedWaiter = continuation
    }
  }

  func release() -> Bool {
    guard let releaseContinuation else { return false }
    self.releaseContinuation = nil
    releaseContinuation.resume()
    return true
  }

  func launches() -> Int { launchCount }
}

final class AgentRuntimeProcessTests: XCTestCase {
  func testJournalDeadlineAcceptsResultAfterSQLiteBusyWindowWithoutWallClockDelay() {
    let simulatedArrivalNanoseconds: UInt64 = 6_170_000_000
    XCTAssertEqual(
      AgentRuntimeJournalTimeoutPolicy.sqliteBusyWindowNanoseconds,
      5_000_000_000
    )
    XCTAssertEqual(AgentRuntimeJournalTimeoutPolicy.ipcSlackNanoseconds, 5_000_000_000)
    XCTAssertGreaterThan(
      AgentRuntimeJournalTimeoutPolicy.deadlineNanoseconds,
      AgentRuntimeJournalTimeoutPolicy.sqliteBusyWindowNanoseconds
    )
    XCTAssertLessThan(
      simulatedArrivalNanoseconds,
      AgentRuntimeJournalTimeoutPolicy.deadlineNanoseconds
    )
    XCTAssertTrue(
      AgentRuntimeJournalTimeoutPolicy.allowsCorrelatedResult(
        elapsedNanoseconds: simulatedArrivalNanoseconds
      )
    )
  }

  func testJournalDeadlineClassifiesExactAndLaterArrivalsAsTimedOut() {
    let deadline = AgentRuntimeJournalTimeoutPolicy.deadlineNanoseconds
    XCTAssertEqual(deadline, 10_000_000_000)
    XCTAssertFalse(
      AgentRuntimeJournalTimeoutPolicy.allowsCorrelatedResult(
        elapsedNanoseconds: deadline
      ),
      "the actor removes the request at the exact deadline before late results can route"
    )
    XCTAssertFalse(
      AgentRuntimeJournalTimeoutPolicy.allowsCorrelatedResult(
        elapsedNanoseconds: deadline + 1_170_000_000
      ),
      "post-deadline results remain unroutable"
    )
  }

  // MARK: - CHAT-02 agent stall hook

  func testSuspendStreamNoOpsWithoutRunningProcess() async {
    // External contract: the debug suspend never reports success without a real
    // suspend — it returns an error (prod-gated in the test host, or no running
    // process on a dev bundle), never suspended:true, and never SIGSTOPs a bogus pid.
    let result = await AgentRuntimeProcess.shared.debugSuspendStream(durationMs: 190_000)
    XCTAssertNotEqual(result["suspended"], "true")
    XCTAssertNotNil(result["error"])
  }

  func testResumeStreamNoOpsWithoutProcess() {
    // debugResumeStream is nonisolated now (off-actor SIGCONT) — no await needed.
    let result = AgentRuntimeProcess.shared.debugResumeStream()
    XCTAssertNotEqual(result["resumed"], "true")
    XCTAssertNotNil(result["error"])
  }

  func testAgentStallHookIsNonProdGatedAndSafe() throws {
    let processSource = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift"),
      encoding: .utf8)
    // Production gate, live-process guard, real signals, bounded window, and a
    // generation-guarded auto-resume so a forgotten resume can't wedge the agent.
    for needle in [
      "func debugSuspendStream(durationMs: Int)",
      "guard AppBuild.isNonProduction else",
      "process.isRunning, process.processIdentifier > 0",
      "kill(pid, SIGSTOP)",
      "kill($0, SIGCONT)",
      "min(durationMs, 300_000)",
      "generation == self.generation",
    ] {
      XCTAssertTrue(processSource.contains(needle), "AgentRuntimeProcess missing stall-hook invariant: \(needle)")
    }

    let bridgeSource = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("Sources/DesktopAutomationBridge.swift"),
      encoding: .utf8)
    for needle in ["name: \"suspend_agent_stream\"", "name: \"resume_agent_stream\""] {
      XCTAssertTrue(bridgeSource.contains(needle), "bridge missing action: \(needle)")
    }
    // Both actions must be behind the non-prod guard.
    let suspendIdx = bridgeSource.range(of: "name: \"suspend_agent_stream\"")!.lowerBound
    let afterSuspend = String(bridgeSource[suspendIdx...].prefix(600))
    XCTAssertTrue(afterSuspend.contains("AppBuild.isNonProduction"),
      "suspend_agent_stream must be gated to non-production bundles")
  }

  func testV2ResultParsingPreservesCanonicalAndAdapterIds() {
    let line = """
      {"type":"result","protocolVersion":2,"requestId":"req-1","clientId":"client-1","sessionId":"omi-1","runId":"run-1","attemptId":"attempt-1","adapterSessionId":"acp-1","terminalStatus":"succeeded","text":"done","costUsd":1.25,"inputTokens":3,"outputTokens":4,"cacheReadTokens":5,"cacheWriteTokens":6}
      """

    let message = AgentRuntimeProcess.RuntimeMessage.parse(line)

    XCTAssertEqual(message?.kind, .result)
    XCTAssertEqual(message?.requestId, "req-1")
    XCTAssertEqual(message?.clientId, "client-1")
    XCTAssertEqual(message?.requestKey, AgentRuntimeProcess.RuntimeMessage.RequestKey(clientId: "client-1", requestId: "req-1"))
    XCTAssertEqual(message?.payload["sessionId"] as? String, "omi-1")
    XCTAssertEqual(message?.payload["adapterSessionId"] as? String, "acp-1")
    XCTAssertEqual(message?.payload["terminalStatus"] as? String, "succeeded")
  }

  func testCancelAckRoutesByRequestId() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"cancel_ack","protocolVersion":2,"requestId":"cancel-me","clientId":"client-1","accepted":true,"dispatchAttempted":true,"adapterAcknowledged":false}"#
    )

    XCTAssertEqual(message?.kind, .cancelAck)
    XCTAssertEqual(message?.requestKey, AgentRuntimeProcess.RuntimeMessage.RequestKey(clientId: "client-1", requestId: "cancel-me"))
    XCTAssertEqual(message?.payload["accepted"] as? Bool, true)
    XCTAssertEqual(message?.payload["adapterAcknowledged"] as? Bool, false)
  }

  func testInitMessageCarriesAdvertisedAgentControlTools() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"init","sessionId":"","agentControlTools":["list_agent_sessions","spawn_background_agent"]}"#
    )

    XCTAssertEqual(message?.kind, .initMessage)
    XCTAssertEqual(message?.payload["agentControlTools"] as? [String], ["list_agent_sessions", "spawn_background_agent"])
  }

  func testControlToolResultRoutesByRequestId() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"control_tool_result","protocolVersion":2,"requestId":"control-1","clientId":"client-1","ownerId":"owner-1","name":"inspect_agent_artifacts","result":"{\"ok\":true,\"artifacts\":[]}"}"#
    )

    XCTAssertEqual(message?.kind, .controlToolResult)
    XCTAssertEqual(message?.requestKey, AgentRuntimeProcess.RuntimeMessage.RequestKey(clientId: "client-1", requestId: "control-1"))
    XCTAssertEqual(message?.payload["ownerId"] as? String, "owner-1")
    XCTAssertEqual(message?.payload["name"] as? String, "inspect_agent_artifacts")
    XCTAssertEqual(message?.payload["result"] as? String, #"{"ok":true,"artifacts":[]}"#)
  }

  func testDirectControlWireAndResultValidationAreOwnerBound() {
    let request = AgentRuntimeProcess.directControlToolWireMessage(
      clientId: "client-1",
      requestId: "control-1",
      ownerId: "owner-a",
      name: "spawn_agent",
      input: ["objective": "Inspect memories"])

    XCTAssertEqual(request["type"] as? String, "direct_control_tool")
    XCTAssertEqual(request["ownerId"] as? String, "owner-a")
    XCTAssertTrue(AgentRuntimeProcess.isDirectControlResultOwnerCurrent(
      expectedOwnerId: "owner-a",
      expectedOwnerEpoch: 1,
      resultOwnerId: "owner-a",
      currentOwnerId: "owner-a",
      currentOwnerEpoch: 1))
    XCTAssertFalse(AgentRuntimeProcess.isDirectControlResultOwnerCurrent(
      expectedOwnerId: "owner-a",
      expectedOwnerEpoch: 1,
      resultOwnerId: nil,
      currentOwnerId: "owner-a",
      currentOwnerEpoch: 1))
    XCTAssertFalse(AgentRuntimeProcess.isDirectControlResultOwnerCurrent(
      expectedOwnerId: "owner-a",
      expectedOwnerEpoch: 1,
      resultOwnerId: "owner-b",
      currentOwnerId: "owner-a",
      currentOwnerEpoch: 1))
    XCTAssertFalse(AgentRuntimeProcess.isDirectControlResultOwnerCurrent(
      expectedOwnerId: "owner-a",
      expectedOwnerEpoch: 1,
      resultOwnerId: "owner-a",
      currentOwnerId: "owner-b",
      currentOwnerEpoch: 2))
    XCTAssertFalse(AgentRuntimeProcess.isDirectControlResultOwnerCurrent(
      expectedOwnerId: "owner-a",
      expectedOwnerEpoch: 1,
      resultOwnerId: "owner-a",
      currentOwnerId: "owner-a",
      currentOwnerEpoch: 3))
  }

  func testLocalProviderRuntimeOwnerHandshakePrecedesOwnerScopedStartupWork() throws {
    let handshake = AgentRuntimeProcess.runtimeOwnerHandshakeWireMessage(ownerId: "signed-in-owner")
    XCTAssertEqual(handshake["type"] as? String, "refresh_owner")
    XCTAssertEqual(handshake["ownerId"] as? String, "signed-in-owner")
    XCTAssertNil(handshake["token"])

    // omi-test-quality: source-inspection -- static contract: every harness must synchronize daemon owner authority before owner-scoped legacy migration; wire and resource-layout behavior are tested directly beside this ordering guard
    let bridgeSource = try sourceFile("Chat/AgentBridge.swift")
    let startRange = try XCTUnwrap(bridgeSource.range(
      of: "private func start(\n    authorizationSnapshot:"))
    let restartRange = try XCTUnwrap(bridgeSource.range(
      of: "\n  func restart() async throws",
      range: startRange.upperBound..<bridgeSource.endIndex))
    let startBody = String(bridgeSource[startRange.lowerBound..<restartRange.lowerBound])
    let handshakeRange = try XCTUnwrap(startBody.range(
      of: "await synchronizeRuntimeAuthority(authorizationSnapshot: authorizationSnapshot)"))
    let migrationRange = try XCTUnwrap(startBody.range(
      of: "await migrateLegacyMainChatSessionsIfNeeded("))
    XCTAssertLessThan(handshakeRange.lowerBound, migrationRange.lowerBound)
    XCTAssertTrue(bridgeSource.contains("guard isPiMonoHarness else"))
    XCTAssertTrue(bridgeSource.contains("await runtime.refreshRuntimeOwner("))
  }

  func testRuntimeStartupSingleFlightLaunchesExactlyOnceForConcurrentSameKey() async throws {
    let singleFlight = AgentRuntimeStartupSingleFlight<String, UInt64>()
    let harness = GatedRuntimeStartupHarness()
    let first = Task {
      try await singleFlight.run(key: "owner-a:generation-1") {
        await harness.launch(receipt: 41)
      }
    }
    await harness.waitUntilLaunchStarted()
    let second = Task {
      try await singleFlight.run(key: "owner-a:generation-1") {
        await harness.launch(receipt: 99)
      }
    }

    var observedTwoParticipants = false
    for _ in 0..<10_000 {
      if await singleFlight.participantCountForTesting() == 2 {
        observedTwoParticipants = true
        break
      }
      await Task.yield()
    }
    XCTAssertTrue(observedTwoParticipants)
    let launchesBeforeRelease = await harness.launches()
    let released = await harness.release()
    XCTAssertEqual(launchesBeforeRelease, 1)
    XCTAssertTrue(released)

    let firstReceipt = try await first.value
    let secondReceipt = try await second.value
    XCTAssertEqual(firstReceipt, 41)
    XCTAssertEqual(secondReceipt, 41)
    let finalLaunches = await harness.launches()
    XCTAssertEqual(finalLaunches, 1)
  }

  func testRuntimeStartupSingleFlightRejectsDifferentOwnerGenerationWhileSuspended() async throws {
    let singleFlight = AgentRuntimeStartupSingleFlight<String, UInt64>()
    let harness = GatedRuntimeStartupHarness()
    let first = Task {
      try await singleFlight.run(key: "owner-a:generation-1") {
        await harness.launch(receipt: 7)
      }
    }
    await harness.waitUntilLaunchStarted()

    do {
      _ = try await singleFlight.run(key: "owner-a:generation-2") { 8 }
      XCTFail("new owner generation must not join an older credential-bearing launch")
    } catch BridgeError.restarting {
      // Expected: caller retries only after the exact older flight terminates.
    } catch {
      XCTFail("unexpected mismatch error: \(error)")
    }

    let launchesBeforeRelease = await harness.launches()
    let released = await harness.release()
    XCTAssertEqual(launchesBeforeRelease, 1)
    XCTAssertTrue(released)
    let receipt = try await first.value
    XCTAssertEqual(receipt, 7)
  }

  func testOwnerBoundTokenRefreshDropsDelayedTokenAcrossSameOwnerSessionReplacement() async throws {
    let harness = DelayedOwnerBoundTokenRefreshHarness()
    let refreshTask = Task {
      try await AgentBridge.refreshOwnerBoundToken(
        captureAuthorization: {
          await harness.captureAuthorization()
        },
        authorizationOwnerId: { authorization in
          authorization.ownerID
        },
        isAuthorizationCurrent: { authorization in
          await harness.isAuthorizationCurrent(authorization)
        },
        fetchAuthHeader: { expectedOwnerId in
          try await harness.fetchAuthHeader(expectedOwnerId: expectedOwnerId)
        },
        sendToken: { token, expectedOwnerId, _ in
          await harness.recordSend(token: token, ownerId: expectedOwnerId)
        }
      )
    }

    await harness.waitUntilFetchStarted()
    let resumed = await harness.replaceOwnerASessionAndCompleteFetch(
      header: "Bearer owner-a-token")
    XCTAssertTrue(resumed)
    let refreshed = try await refreshTask.value
    XCTAssertFalse(refreshed)

    let snapshot = await harness.snapshot()
    XCTAssertEqual(snapshot.fetchedOwnerIds, ["owner-a"])
    XCTAssertNil(snapshot.sentToken, "stale owner-A token must never reach the runtime sender")
    XCTAssertNil(snapshot.sentOwnerId, "stale refresh must not mutate runtime owner credentials")
  }

  func testRuntimeRefreshTokenWireRequiresCapturedOwnerToRemainCurrent() {
    let authorized = AgentRuntimeProcess.refreshTokenWireMessage(
      token: "owner-a-token",
      expectedOwnerId: "owner-a",
      currentOwnerId: "owner-a"
    )

    XCTAssertEqual(authorized?["type"] as? String, "refresh_token")
    XCTAssertEqual(authorized?["token"] as? String, "owner-a-token")
    XCTAssertEqual(authorized?["ownerId"] as? String, "owner-a")
    XCTAssertNil(AgentRuntimeProcess.refreshTokenWireMessage(
      token: "owner-a-token",
      expectedOwnerId: "owner-a",
      currentOwnerId: "owner-b"
    ))
    XCTAssertNil(AgentRuntimeProcess.refreshTokenWireMessage(
      token: "owner-a-token",
      expectedOwnerId: "owner-a",
      currentOwnerId: nil
    ))
  }

  func testOwnerRuntimeRevocationWireAndCorrelatedReceiptShape() {
    let wire = AgentRuntimeProcess.revokeOwnerRuntimeWireMessage(
      clientId: "runtime-owner-transition",
      requestId: "revoke-1",
      ownerId: "owner-a")
    XCTAssertEqual(wire["type"] as? String, "revoke_owner_runtime")
    XCTAssertEqual(wire["protocolVersion"] as? Int, 2)
    XCTAssertEqual(wire["requestId"] as? String, "revoke-1")
    XCTAssertEqual(wire["clientId"] as? String, "runtime-owner-transition")
    XCTAssertEqual(wire["ownerId"] as? String, "owner-a")

    let receipt = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"owner_runtime_revoked","protocolVersion":2,"requestId":"revoke-1","clientId":"runtime-owner-transition","ownerId":"owner-a","ok":true,"duplicate":false,"revokedRunIds":["run-1"],"invalidatedBindingIds":["binding-1"]}"#)
    XCTAssertEqual(receipt?.kind, .ownerRuntimeRevoked)
    XCTAssertEqual(
      receipt?.requestKey,
      AgentRuntimeProcess.RuntimeMessage.RequestKey(
        clientId: "runtime-owner-transition",
        requestId: "revoke-1"))
    XCTAssertEqual(receipt?.payload["ownerId"] as? String, "owner-a")
    XCTAssertEqual(receipt?.payload["revokedRunIds"] as? [String], ["run-1"])
    XCTAssertEqual(receipt?.payload["invalidatedBindingIds"] as? [String], ["binding-1"])
  }

  func testRuntimeNodeResourceLookupSupportsAppAndSwiftPMTestLayoutsWithoutFatalAccessor() {
    let appBundle = URL(fileURLWithPath: "/Applications/omi-test.app")
    let testBundle = URL(fileURLWithPath: "/tmp/debug/Omi ComputerPackageTests.xctest")
    let executable = testBundle
      .appendingPathComponent("Contents/MacOS/Omi ComputerPackageTests")
    let candidates = AgentRuntimeProcess.runtimeResourceExecutableCandidates(
      named: "node",
      bundleURLs: [appBundle, testBundle],
      executableURL: executable)

    XCTAssertTrue(candidates.contains(
      "/Applications/omi-test.app/Contents/Resources/Omi Computer_Omi Computer.bundle/node"))
    XCTAssertTrue(candidates.contains(
      "/tmp/debug/Omi Computer_Omi Computer.bundle/node"))
    XCTAssertFalse(candidates.isEmpty)
  }

  func testLegacyMainChatAliasReceiptRoutesByRequestAndOwner() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"legacy_main_chat_sessions_imported","protocolVersion":2,"requestId":"legacy-1","clientId":"client-1","ownerId":"owner-1","acceptedEntries":[{"chatId":"default","agentSessionId":"ses-1"}],"acceptedCount":1,"importedCount":1}"#
    )

    XCTAssertEqual(message?.kind, .legacyMainChatSessionsImported)
    XCTAssertEqual(
      message?.requestKey,
      AgentRuntimeProcess.RuntimeMessage.RequestKey(clientId: "client-1", requestId: "legacy-1")
    )
    XCTAssertEqual(message?.payload["ownerId"] as? String, "owner-1")
  }

  func testLegacyMainChatAliasImportWireMessageCarriesOwnerAndEntries() {
    let entry = LegacyMainChatSessionAliasEntry(chatId: "default", agentSessionId: "ses-1")
    let message = AgentRuntimeProcess.importLegacyMainChatSessionsWireMessage(
      clientId: "client-1",
      requestId: "legacy-1",
      ownerId: "owner-1",
      entries: [entry]
    )

    XCTAssertEqual(message["type"] as? String, "import_legacy_main_chat_sessions")
    XCTAssertEqual(message["protocolVersion"] as? Int, 2)
    XCTAssertEqual(message["ownerId"] as? String, "owner-1")
    XCTAssertEqual(
      message["entries"] as? [[String: String]],
      [["chatId": "default", "agentSessionId": "ses-1"]]
    )
  }

  func testAuthorizedToolExecutionCarriesLedgerIdentityWithoutRequestScope() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"authorized_tool_execution","protocolVersion":2,"invocationId":"invoke-1","ownerId":"owner-1","sessionId":"session-1","runId":"run-1","attemptId":"attempt-1","profileGeneration":2,"manifestVersion":1,"manifestDigest":"sha256:test","daemonBootEpoch":"boot-1","executionGeneration":3,"toolName":"get_memories","input":{},"inputHash":"sha256:e3b0","effectClass":"read_only","retryPolicy":"safe_retry","surfaceKind":"background_agent","externalRefKind":null,"externalRefId":null,"originatingUserText":"find memories","precedingAssistantText":null,"runMode":"act","chatMode":null}"#)

    XCTAssertEqual(message?.kind, .authorizedToolExecution)
    XCTAssertNil(message?.requestKey)
    XCTAssertEqual(message?.payload["invocationId"] as? String, "invoke-1")
    XCTAssertEqual(message?.payload["attemptId"] as? String, "attempt-1")
  }

  func testSwiftHasNoCapabilityAuthorityOrRequestScopedExecution() throws {
    let processSourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let processSource = try String(contentsOf: processSourceURL, encoding: .utf8)

    XCTAssertTrue(processSource.contains("AuthorizedToolExecution.parse("))
    XCTAssertTrue(processSource.contains(#"case .authorizedToolExecution:"#))
    XCTAssertFalse(processSource.contains("RunToolCapabilityRegistry"))
    XCTAssertFalse(processSource.contains("toolCapabilities"))
    XCTAssertFalse(processSource.contains("tool_capability_register"))
    XCTAssertFalse(processSource.contains("guard let request = routedRequest(for: message) else"))
  }

  func testV2MessagesWithoutClientIdDoNotHaveRequestKey() {
    let message = AgentRuntimeProcess.RuntimeMessage.parse(
      #"{"type":"result","protocolVersion":2,"requestId":"req-1","sessionId":"omi-1","runId":"run-1","attemptId":"attempt-1","terminalStatus":"succeeded","text":"done"}"#
    )

    XCTAssertEqual(message?.kind, .result)
    XCTAssertNil(message?.requestKey)
  }

  func testHarnessModeMapsNamedAdapters() {
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "piMono"), "pi-mono")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "pi-mono"), "pi-mono")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "hermes"), "hermes")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "openclaw"), "openclaw")
    XCTAssertEqual(AgentRuntimeProcess.adapterId(forHarnessMode: "openClaw"), "openclaw")
    XCTAssertNil(AgentRuntimeProcess.adapterId(forHarnessMode: "unknown"))
  }

  func testPiMonoAliasUsesCanonicalAdapterForAuthGuards() throws {
    let processSourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let processSource = try String(contentsOf: processSourceURL, encoding: .utf8)

    XCTAssertTrue(processSource.contains("let preferredAdapterId = AgentRuntimeRouting.adapterId(for: preferredHarness)"))
    XCTAssertTrue(processSource.contains("preferredAdapterId == .piMono"))
    XCTAssertFalse(processSource.contains(#"preferredHarnessMode == "piMono""#))

    let bridgeSourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentBridge.swift")
    let bridgeSource = try String(contentsOf: bridgeSourceURL, encoding: .utf8)

    XCTAssertTrue(bridgeSource.contains("AgentRuntimeProcess.adapterId(forHarnessMode: harnessMode) == AgentAdapterId.piMono.rawValue"))
    XCTAssertTrue(bridgeSource.contains("guard isPiMonoHarness else"))
    XCTAssertTrue(bridgeSource.contains("if adapterId == AgentAdapterId.piMono.rawValue"))
    XCTAssertTrue(bridgeSource.contains(
      "ensureTokenRefreshTask(authorizationSnapshot: authorizationSnapshot)"))
    XCTAssertFalse(bridgeSource.contains("guard isPiMonoHarness else { return false }"))
    XCTAssertFalse(bridgeSource.contains(#"harnessMode == "piMono""#))
  }

  func testPiMonoInvalidTokenRetriesAfterForcedAuthRefresh() throws {
    let bridgeSourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentBridge.swift")
    let bridgeSource = try String(contentsOf: bridgeSourceURL, encoding: .utf8)

    XCTAssertTrue(bridgeSource.contains("error.isSessionAuthenticationFailure"))
    XCTAssertTrue(bridgeSource.contains("!bridgeOutputTracker.hasOutput"))
    XCTAssertTrue(bridgeSource.contains("private final class BridgeOutputTracker: @unchecked Sendable"))
    XCTAssertTrue(bridgeSource.contains("refreshing token and retrying once"))
    // The refresh must convert real auth failures to authMissing so ChatProvider
    // routes to the sign-in recovery CTA, while propagating CancellationError so a
    // cancelled request is not misrouted to auth recovery.
    XCTAssertTrue(bridgeSource.contains("catch is CancellationError"))
    XCTAssertTrue(bridgeSource.contains("throw CancellationError()"))
    XCTAssertTrue(bridgeSource.contains("catch {"))
    XCTAssertTrue(bridgeSource.contains("throw BridgeError.authMissing"))
    XCTAssertFalse(bridgeSource.contains("guard try await refreshAuthToken()"))
    XCTAssertFalse(bridgeSource.contains("(try? await refreshAuthToken()) == true"))
    XCTAssertTrue(bridgeSource.contains("let retryRequestId = UUID().uuidString"))
  }

  func testNamedBundleStateDirectoriesAreIsolated() {
    let home = URL(fileURLWithPath: "/tmp/test-home")

    let firstState = AgentRuntimeProcess.defaultStateDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-a",
      homeDirectory: home
    )
    let secondState = AgentRuntimeProcess.defaultStateDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-b",
      homeDirectory: home
    )
    let firstArtifacts = AgentRuntimeProcess.defaultArtifactsDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-a",
      homeDirectory: home
    )
    let secondArtifacts = AgentRuntimeProcess.defaultArtifactsDirectory(
      bundleIdentifier: "com.omi.omi-ticket-five-b",
      homeDirectory: home
    )

    XCTAssertNotEqual(firstState, secondState)
    XCTAssertNotEqual(firstArtifacts, secondArtifacts)
    XCTAssertTrue(firstState.hasSuffix("AgentRuntime/com.omi.omi-ticket-five-a"))
    XCTAssertTrue(secondState.hasSuffix("AgentRuntime/com.omi.omi-ticket-five-b"))
    XCTAssertTrue(firstArtifacts.hasSuffix("Artifacts/com.omi.omi-ticket-five-a"))
    XCTAssertTrue(secondArtifacts.hasSuffix("Artifacts/com.omi.omi-ticket-five-b"))
  }

  func testCompatibilitySessionIdPrefersAdapterSession() {
    let withAdapter = AgentBridge.QueryResult(
      text: "done",
      costUsd: 0,
      omiSessionId: "omi-session",
      runId: "run",
      attemptId: "attempt",
      adapterSessionId: "adapter-session",
      terminalStatus: "succeeded",
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0
    )
    let withoutAdapter = AgentBridge.QueryResult(
      text: "done",
      costUsd: 0,
      omiSessionId: "omi-session",
      runId: "run",
      attemptId: "attempt",
      adapterSessionId: nil,
      terminalStatus: "succeeded",
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0
    )

    XCTAssertEqual(withAdapter.adapterSessionId, "adapter-session")
    XCTAssertEqual(withoutAdapter.omiSessionId, "omi-session")
    XCTAssertNil(withoutAdapter.adapterSessionId)
  }

  @MainActor
  func testEveryNonTaskQueryResultLayerFailsClosedWithoutTypedSuccess() throws {
    XCTAssertEqual(AgentQueryTerminalStatus(wireValue: "succeeded"), .succeeded)
    XCTAssertEqual(AgentQueryTerminalStatus(wireValue: "cancelled"), .cancelled)
    XCTAssertEqual(AgentQueryTerminalStatus(wireValue: nil), .invalid(nil))
    XCTAssertEqual(AgentQueryTerminalStatus(wireValue: "future_terminal"), .invalid("future_terminal"))

    let successfulBridgeResult = AgentBridge.QueryResult(
      text: "accepted",
      costUsd: 0,
      omiSessionId: "omi-session",
      runId: "run",
      attemptId: "attempt",
      adapterSessionId: nil,
      terminalStatus: "succeeded",
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0
    )
    let successfulClientResult = AgentClient.QueryResult(successfulBridgeResult)
    XCTAssertEqual(try successfulBridgeResult.requireSucceeded().text, "accepted")
    XCTAssertEqual(try successfulClientResult.requireSucceeded().text, "accepted")
    XCTAssertEqual(
      try ChatProvider.requireSuccessfulQueryResult(successfulClientResult).text,
      "accepted"
    )

    for rawStatus in [nil, "future_terminal", "failed", "timed_out", "orphaned", "cancelled"] as [String?] {
      let bridgeResult = AgentBridge.QueryResult(
        text: "not successful",
        costUsd: 0,
        omiSessionId: "omi-session",
        runId: "run",
        attemptId: "attempt",
        adapterSessionId: nil,
        terminalStatus: rawStatus,
        inputTokens: 0,
        outputTokens: 0,
        cacheReadTokens: 0,
        cacheWriteTokens: 0
      )
      let clientResult = AgentClient.QueryResult(bridgeResult)
      let label = "\(String(describing: rawStatus)) must fail closed"
      XCTAssertThrowsError(try bridgeResult.requireSucceeded(), label)
      XCTAssertThrowsError(try clientResult.requireSucceeded(), label)
      XCTAssertThrowsError(try ChatProvider.requireSuccessfulQueryResult(clientResult), label)
    }
  }

  func testSharedRuntimeDoesNotTrackCurrentHarnessMode() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertFalse(source.contains("currentHarnessMode"))
    XCTAssertFalse(source.contains("harness changed"))
    XCTAssertFalse(source.contains(#""adapterId": harnessMode == "piMono" ? "pi-mono" : "acp""#))
  }

  func testLocalAdapterDiscoveryRunsForSharedRuntimeStartup() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("applyLocalAgentEnvironment(to: &env)"))
    XCTAssertFalse(source.contains("applyLocalAgentEnvironment(to: &env, adapterId: preferredAdapterId)"))
    XCTAssertFalse(source.contains("guard adapterId == .hermes || adapterId == .openclaw else"))
    XCTAssertTrue(source.contains(#"env["HOME"] = home"#))
    XCTAssertTrue(source.contains(#"env["HERMES_HOME"] = "\(home)/.hermes""#))
    XCTAssertTrue(source.contains(#""\(home)/.hermes/hermes-agent/venv/bin""#))
    XCTAssertTrue(source.contains("existingPath.split(separator: \":\").map(String.init) + trustedPathDirs"))
    XCTAssertTrue(source.contains("+ adapterPathDirs"))
    XCTAssertFalse(source.contains("adapterPathPrefixDirs + existingPath.split"))
    XCTAssertTrue(source.contains(#"env["PATH"] = pathElements.joined(separator: ":")"#))
    XCTAssertTrue(source.contains(#"env["OMI_OPENCLAW_ADAPTER_COMMAND"]"#))
    XCTAssertTrue(source.contains(#"env["OMI_HERMES_ADAPTER_COMMAND"]"#))
  }

  @MainActor
  func testUsableByokEnvironmentSuppressesAllKeysWhenOneProviderIsKnownBad() {
    let savedKeys = Dictionary(
      uniqueKeysWithValues: BYOKProvider.allCases.map { provider in
        (provider, UserDefaults.standard.string(forKey: provider.storageKey))
      })
    defer {
      for provider in BYOKProvider.allCases {
        if let saved = savedKeys[provider] ?? nil {
          UserDefaults.standard.set(saved, forKey: provider.storageKey)
        } else {
          UserDefaults.standard.removeObject(forKey: provider.storageKey)
        }
      }
      CredentialHealthManager.shared.reset()
    }

    for provider in BYOKProvider.allCases {
      UserDefaults.standard.set("sk-agent-\(provider.rawValue)", forKey: provider.storageKey)
    }
    let openAIKey = APIKeyService.byokKey(.openai)!
    CredentialHealthManager.shared.recordProviderFailure(
      .providerAuthFailed(provider: .openai, mode: .byok),
      provider: .openai,
      authMode: .byok,
      fingerprint: APIKeyService.byokFingerprint(openAIKey),
      context: "test")

    let result = AgentRuntimeProcess.usableBYOKEnvironment()

    XCTAssertTrue(result.values.isEmpty)
    XCTAssertEqual(result.suppressedProviders, [.openai])
  }

  @MainActor
  func testUsableByokEnvironmentIncludesAllKeysWhenAllProvidersAreUsable() {
    let savedKeys = Dictionary(
      uniqueKeysWithValues: BYOKProvider.allCases.map { provider in
        (provider, UserDefaults.standard.string(forKey: provider.storageKey))
      })
    defer {
      for provider in BYOKProvider.allCases {
        if let saved = savedKeys[provider] ?? nil {
          UserDefaults.standard.set(saved, forKey: provider.storageKey)
        } else {
          UserDefaults.standard.removeObject(forKey: provider.storageKey)
        }
      }
      CredentialHealthManager.shared.reset()
    }

    for provider in BYOKProvider.allCases {
      UserDefaults.standard.set("sk-agent-\(provider.rawValue)", forKey: provider.storageKey)
    }

    let result = AgentRuntimeProcess.usableBYOKEnvironment()

    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .openai)], "sk-agent-openai")
    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .anthropic)], "sk-agent-anthropic")
    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .gemini)], "sk-agent-gemini")
    XCTAssertEqual(result.values[AgentRuntimeProcess.byokEnvironmentKey(for: .deepgram)], "sk-agent-deepgram")
    XCTAssertTrue(result.suppressedProviders.isEmpty)
  }

  func testRemoveInheritedByokEnvironmentScrubsPrefixCaseInsensitively() {
    var env = [
      "OMI_BYOK_OPENAI": "stale-openai",
      "omi_byok_experimental": "stale-experimental",
      "OmI_bYoK_LEGACY": "stale-legacy",
      "OMI_AUTH_TOKEN": "token",
      "PATH": "/usr/bin",
    ]

    AgentRuntimeProcess.removeInheritedBYOKEnvironment(from: &env)

    XCTAssertNil(env["OMI_BYOK_OPENAI"])
    XCTAssertNil(env["omi_byok_experimental"])
    XCTAssertNil(env["OmI_bYoK_LEGACY"])
    XCTAssertEqual(env["OMI_AUTH_TOKEN"], "token")
    XCTAssertEqual(env["PATH"], "/usr/bin")
  }

  func testPiMonoStartupRefreshesAuthTokenAndFiltersByokEnvironment() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("Self.removeInheritedBYOKEnvironment(from: &env)"))
    XCTAssertTrue(source.contains("let byok = await Self.usableBYOKEnvironment()"))
    XCTAssertTrue(source.contains("let forceRefreshToken = preferredAdapterId == .piMono && !DesktopLocalProfile.isEnabled"))
    XCTAssertTrue(source.contains("getAuthHeader("))
    XCTAssertTrue(source.contains("forceRefresh: forceRefreshToken"))
    XCTAssertTrue(source.contains("expectedUserId: authorizationSnapshot.ownerID"))
    XCTAssertFalse(source.contains("log(\"AgentRuntimeProcess: pi-mono BYOK active, forwarding \\(BYOKProvider.allCases.count) user keys\")"))
    XCTAssertTrue(source.contains("forwarding \\(byok.values.count) usable user keys"))
  }

  func testOpenClawAdapterCommandUsesSiblingNodeWhenAvailable() throws {
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("openclaw-command-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let nodePath = tempDir.appendingPathComponent("node").path
    let openClawPath = tempDir.appendingPathComponent("openclaw").path
    FileManager.default.createFile(atPath: nodePath, contents: Data("#!/bin/sh\n".utf8))
    FileManager.default.createFile(atPath: openClawPath, contents: Data("#!/usr/bin/env node\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: nodePath)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: openClawPath)

    let command = AgentRuntimeProcess.openClawAdapterCommand(openClawPath: openClawPath)

    XCTAssertEqual(command, "'\(nodePath)' '\(openClawPath)' acp")
  }

  func testOpenClawAdapterCommandFallsBackToLauncherWithoutSiblingNode() throws {
    let tempDir = FileManager.default.temporaryDirectory
      .appendingPathComponent("openclaw-command-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: tempDir) }

    let openClawPath = tempDir.appendingPathComponent("openclaw").path
    FileManager.default.createFile(atPath: openClawPath, contents: Data("#!/usr/bin/env node\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: openClawPath)

    let command = AgentRuntimeProcess.openClawAdapterCommand(openClawPath: openClawPath)

    XCTAssertEqual(command, "'\(openClawPath)' acp")
  }

  func testOpenClawDiscoveryFindsXDGFnmInstall() throws {
    let home = FileManager.default.temporaryDirectory
      .appendingPathComponent("openclaw-fnm-home-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: home) }

    let bin = home
      .appendingPathComponent(".local/share/fnm/node-versions/v24.12.0/installation/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    let openClaw = bin.appendingPathComponent("openclaw")
    FileManager.default.createFile(atPath: openClaw.path, contents: Data("#!/bin/sh\n".utf8))
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: openClaw.path)

    let directories = AgentRuntimeProcess.localAdapterSearchDirectories(home: home.path)
    let discovered = AgentRuntimeProcess.firstExecutable(named: "openclaw", in: directories)

    XCTAssertEqual(discovered, openClaw.path)
  }

  func testStdoutReaderIsEventDrivenInsteadOfDetachedAvailableDataLoop() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("handle.readabilityHandler = { [weak self] handle in"))
    // The implementation now uses a generation-guarded signature; match the current
    // function name without coupling the test to the exact parameter list.
    XCTAssertTrue(source.contains("func processStdoutData("))
    XCTAssertFalse(source.contains("Task.detached { [weak self] in"))
    XCTAssertFalse(source.contains("while !Task.isCancelled"))
  }

  func testStdoutChunksAreReorderedBeforeJSONLFraming() {
    let frame = Data(
      #"{"type":"context_snapshot","protocolVersion":2,"requestId":"context-1","clientId":"client-1","ownerId":"owner-1","snapshot":{}}"#.utf8
    ) + Data([UInt8(ascii: "\n")])
    let split = frame.count / 2
    let first = Data(frame[..<split])
    let second = Data(frame[split...])
    var buffer = AgentRuntimeOrderedStdoutBuffer()

    XCTAssertTrue(buffer.ingest(second, sequence: 1).isEmpty)
    let lines = buffer.ingest(first, sequence: 0)
    let parsed = lines.compactMap { lineData -> AgentRuntimeProcess.RuntimeMessage? in
      guard let line = String(data: lineData, encoding: .utf8) else { return nil }
      return AgentRuntimeProcess.RuntimeMessage.parse(line)
    }

    XCTAssertEqual(lines.count, 1)
    XCTAssertEqual(parsed.count, 1, "ordered delivery must produce zero malformed JSONL frames")
    XCTAssertEqual(parsed.first?.kind, .contextSnapshot)
    XCTAssertEqual(parsed.first?.requestId, "context-1")
  }

  func testFailedRuntimeStartCleansUpLatchedRunningState() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("cleanupFailedStart(process: proc, error: error)"))
    XCTAssertTrue(source.contains("isRunning = false"))
    XCTAssertTrue(source.contains("receivedInit = false"))
    XCTAssertTrue(source.contains("resumeInitContinuations(throwing: BridgeError.stopped)"))
  }

  func testSharedRestartIsBlockedWhileRequestsAreActive() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("guard activeRequests.isEmpty, activeControlRequests.isEmpty else"))
    XCTAssertTrue(source.contains("isRestarting = true"))
    XCTAssertTrue(source.contains("guard !isRestarting, !isStopping else"))
    XCTAssertTrue(source.contains("BridgeError.restarting"))
    XCTAssertTrue(source.contains("BridgeError.requestAlreadyActive"))
  }

  func testClientRegistrationWaitsForInitWhenProcessIsAlreadyRunning() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("if isRunning {"))
    XCTAssertTrue(source.contains("try await waitForInit(timeout: 30.0)"))
    XCTAssertTrue(source.contains("try assertStartupAuthority("))
    XCTAssertTrue(source.contains(
      "try assertClientRegistration(clientId: clientId, registrationID: registrationID)"))
    XCTAssertTrue(source.contains("case .initMessage:"))
    XCTAssertTrue(source.contains("resolveInitContinuations()"))
  }

  func testAppSurfacesUseDirectControlToolOnly() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertFalse(source.contains("func requestScopedControlTool("))
    XCTAssertFalse(source.contains(#""type": "control_tool""#))
    XCTAssertTrue(source.contains("func directControlTool("))
    XCTAssertTrue(source.contains("activeControlRequests[requestKey]"))
    XCTAssertTrue(source.contains("completeControlRequest(message)"))
    XCTAssertTrue(source.contains("if !sent, let request = activeControlRequests.removeValue(forKey: requestKey)"))
    XCTAssertTrue(source.contains("failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)"))
    XCTAssertTrue(source.contains("request.continuation.resume(returning: queryResult(from: message))"))
    XCTAssertFalse(source.contains(#"terminalStatus: payload["terminalStatus"] as? String ?? "succeeded""#))
  }

  func testDirectControlToolRequestsUseDedicatedSignedInOwnerEnvelope() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("func directControlTool("))
    XCTAssertTrue(source.contains("RuntimeOwnerIdentity.captureAuthorizationSnapshot()"))
    XCTAssertTrue(source.contains("try assertAuthorization(authorizationSnapshot)"))
    XCTAssertTrue(source.contains("advertisedAgentControlTools.contains(name)"))
    XCTAssertTrue(source.contains("Agent runtime does not advertise direct control tool"))
    XCTAssertTrue(source.contains(#""type": "direct_control_tool""#))
    XCTAssertTrue(source.contains(#""ownerId": ownerId"#))
    XCTAssertTrue(source.contains("let expectedOwnerId: String"))
    XCTAssertTrue(source.contains("let expectedOwnerEpoch: UInt64"))
    XCTAssertTrue(source.contains("resultOwnerId == expectedOwnerId"))
    XCTAssertTrue(source.contains("currentOwnerId == expectedOwnerId"))
    XCTAssertTrue(source.contains("currentOwnerEpoch == expectedOwnerEpoch"))
  }

  func testAuthorizedToolResultsEchoExactLedgerTupleWithoutRequestScope() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("completeAuthorizedToolExecution("))
    XCTAssertTrue(source.contains(#""type": "authorized_tool_execution_result""#))
    XCTAssertTrue(source.contains(#""invocationId": command.invocationID"#))
    XCTAssertTrue(source.contains(#""profileGeneration": command.profileGeneration"#))
    XCTAssertTrue(source.contains(#""manifestDigest": command.manifestDigest"#))
    XCTAssertTrue(source.contains(#""daemonBootEpoch": command.daemonBootEpoch"#))
    XCTAssertTrue(source.contains(#""executionGeneration": command.executionGeneration"#))
    XCTAssertTrue(source.contains(#""inputHash": command.inputHash"#))
    XCTAssertFalse(source.contains(#""requestId": command."#))
    XCTAssertFalse(source.contains(#""clientId": command."#))
  }

  func testStartupTimeoutResumesInitContinuations() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("resumeInitContinuations(throwing: BridgeError.timeout)"))
    XCTAssertFalse(source.contains("withThrowingTaskGroup(of: Void.self)"))
  }

  func testOutOfMemoryDiagnosticRequiresConfirmedRuntimeSignature() {
    XCTAssertTrue(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory"
      )
    )
    XCTAssertTrue(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "FatalProcessOutOfMemory: Zone Allocation failed"
      )
    )
    XCTAssertTrue(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "Failed to reserve virtual memory for CodeRange"
      )
    )

    XCTAssertFalse(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "Provider returned: the requested model is out of memory for this prompt"
      )
    )
    XCTAssertFalse(
      AgentRuntimeProcess.isConfirmedOutOfMemoryDiagnostic(
        "The browser extension reported out of memory while reading a page"
      )
    )
  }

  func testRuntimeDoesNotTreatGenericAbortSignalsAsOutOfMemory() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("let likelyOOM = lastExitWasOOM || oomDiagnosticLatch.isConfirmed(generation: processGeneration)"))
    XCTAssertFalse(source.contains("exitCode == 134"))
    XCTAssertFalse(source.contains("exitCode == 133"))
  }

  func testStderrOutOfMemoryLatchIsSynchronousAndGenerationScoped() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("oomDiagnosticLatch.markIfConfirmed(text, generation: expectedGeneration)"))
    XCTAssertTrue(source.contains("private final class AgentRuntimeOOMDiagnosticLatch: @unchecked Sendable"))
    XCTAssertTrue(source.contains("guard self.generation == generation else { return }"))
    XCTAssertFalse(source.contains("Task { await self?.markOOM"))
  }

  func testIntentionalStopInvalidatesOldProcessGenerationBeforeTerminating() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    let stopStart = try XCTUnwrap(source.range(
      of: "private func stopProcess(resumeRequestsWith error: BridgeError) async"))
    let stopEnd = try XCTUnwrap(source.range(
      of: "private func startReadingStdout()",
      range: stopStart.upperBound..<source.endIndex))
    let stopBody = String(source[stopStart.lowerBound..<stopEnd.lowerBound])
    XCTAssertTrue(stopBody.contains("await cancelAndDrainAuthorizedToolExecutionTasks()"))
    XCTAssertTrue(stopBody.contains("markRuntimeOwnerAuthorityDirty()"))
    let generationAdvance = try XCTUnwrap(stopBody.range(of: "processGeneration &+= 1"))
    let gracefulStop = try XCTUnwrap(stopBody.range(of: "sendJson([\"type\": \"stop\"])"))
    let terminate = try XCTUnwrap(stopBody.range(of: "proc?.terminate()"))
    XCTAssertLessThan(generationAdvance.lowerBound, gracefulStop.lowerBound)
    XCTAssertLessThan(generationAdvance.lowerBound, terminate.lowerBound)
  }

  func testIsAliveRequiresUnderlyingProcessRunning() throws {
    let source = try agentRuntimeSource()
    XCTAssertTrue(source.contains("let processRunning = process?.isRunning ?? false"))
    XCTAssertTrue(source.contains("return isRunning && processRunning"))
    XCTAssertTrue(source.contains("recordAgentRuntimeStaleAliveCheck"))
  }

  func testUnexpectedExitRecordsHealthEvent() throws {
    let source = try agentRuntimeSource()
    XCTAssertTrue(source.contains("recordAgentRuntimeUnexpectedExit"))
    XCTAssertTrue(source.contains("recovery_action=restart_on_next_send"))
  }

  func testEnsureBridgeStartedPreparesCrashRecoveryBeforeRestart() throws {
    let chatSource = try sourceFile("Providers/ChatProvider.swift")
    XCTAssertTrue(chatSource.contains("prepareForCrashRecovery()"))
    XCTAssertTrue(chatSource.contains("agent bridge process died, will restart"))

    let bridgeSource = try sourceFile("Chat/AgentBridge.swift")
    XCTAssertTrue(bridgeSource.contains("func prepareForCrashRecovery()"))
    XCTAssertTrue(bridgeSource.contains("registered = false"))
  }

  func testContextAdmissionMismatchRefreshesCompleteFreshnessAndRetriesOnce() async throws {
    let initial = AgentContextFreshness(
      version: "snapshot-v1",
      generation: 7,
      rendererFingerprint: "renderer-v1",
      capabilityVersion: "capabilities-v1"
    )
    let refreshed = AgentContextFreshness(
      version: "snapshot-v2",
      generation: 8,
      rendererFingerprint: "renderer-v2",
      capabilityVersion: "capabilities-v2"
    )
    var attempts: [AgentContextFreshness?] = []
    var refreshCount = 0

    let result: String = try await AgentContextAdmissionRetry.run(
      expectedContext: initial,
      refresh: {
        refreshCount += 1
        return refreshed
      },
      attempt: { context in
        attempts.append(context)
        if attempts.count == 1 {
          throw self.contextProjectionMismatchError()
        }
        return "admitted"
      }
    )

    XCTAssertEqual(result, "admitted")
    XCTAssertEqual(refreshCount, 1)
    XCTAssertEqual(attempts, [initial, refreshed])
  }

  func testContextAdmissionSecondMismatchFailsWithoutAnotherRefreshOrRetry() async {
    let initial = AgentContextFreshness(
      version: "snapshot-v1",
      generation: 11,
      rendererFingerprint: "renderer-v1",
      capabilityVersion: "capabilities-v1"
    )
    let refreshed = AgentContextFreshness(
      version: "snapshot-v2",
      generation: 12,
      rendererFingerprint: "renderer-v2",
      capabilityVersion: "capabilities-v2"
    )
    var attempts: [AgentContextFreshness?] = []
    var refreshCount = 0

    do {
      let _: String = try await AgentContextAdmissionRetry.run(
        expectedContext: initial,
        refresh: {
          refreshCount += 1
          return refreshed
        },
        attempt: { context in
          attempts.append(context)
          throw self.contextProjectionMismatchError()
        }
      )
      XCTFail("expected the second projection mismatch to fail closed")
    } catch let error as BridgeError {
      XCTAssertTrue(error.isContextSnapshotProjectionMismatch)
    } catch {
      XCTFail("unexpected error: \(error)")
    }

    XCTAssertEqual(refreshCount, 1)
    XCTAssertEqual(attempts, [initial, refreshed])
  }

  func testContextAdmissionMismatchClassifierRequiresExactRuntimeCode() {
    XCTAssertTrue(contextProjectionMismatchError().isContextSnapshotProjectionMismatch)
    XCTAssertFalse(
      BridgeError.agentError("prefix context_snapshot_projection_mismatch suffix")
        .isContextSnapshotProjectionMismatch
    )
    XCTAssertFalse(
      BridgeError.agentRuntimeFailure(AgentRuntimeFailure(
        code: "runtime_query_failed",
        userMessage: "context_snapshot_projection_mismatch",
        technicalMessage: nil,
        source: "adapter_execution",
        adapterId: nil,
        provider: nil,
        retryable: false
      )).isContextSnapshotProjectionMismatch
    )
  }

  private func contextProjectionMismatchError() -> BridgeError {
    .agentRuntimeFailure(AgentRuntimeFailure(
      code: "runtime_query_failed",
      userMessage: "context_snapshot_projection_mismatch",
      technicalMessage: "context_snapshot_projection_mismatch",
      source: "runtime",
      adapterId: nil,
      provider: nil,
      retryable: false
    ))
  }

  private func agentRuntimeSource() throws -> String {
    try sourceFile("Chat/AgentRuntimeProcess.swift")
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}

import XCTest

@testable import Omi_Computer

private final class Box<T>: @unchecked Sendable {
  var value: T
  init(_ value: T) { self.value = value }
}

private actor SuspendedJournalListGate {
  private var ownerAStarted = false
  private var ownerAStartedWaiters: [CheckedContinuation<Void, Never>] = []
  private var ownerAResult: CheckedContinuation<AgentRuntimeProcess.JournalOperationResult, Never>?
  private let ownerBPage: AgentRuntimeProcess.JournalOperationResult

  init(ownerBPage: AgentRuntimeProcess.JournalOperationResult) {
    self.ownerBPage = ownerBPage
  }

  func fetch(
    ownerID: String,
    ownerAPage: AgentRuntimeProcess.JournalOperationResult
  ) async -> AgentRuntimeProcess.JournalOperationResult {
    guard ownerID == "owner-a" else { return ownerBPage }
    ownerAStarted = true
    for waiter in ownerAStartedWaiters { waiter.resume() }
    ownerAStartedWaiters.removeAll()
    return await withCheckedContinuation { continuation in
      ownerAResult = continuation
    }
  }

  func waitUntilOwnerAStarted() async {
    guard !ownerAStarted else { return }
    await withCheckedContinuation { continuation in
      ownerAStartedWaiters.append(continuation)
    }
  }

  func releaseOwnerA(with page: AgentRuntimeProcess.JournalOperationResult) {
    ownerAResult?.resume(returning: page)
    ownerAResult = nil
  }
}

@MainActor
final class KernelTurnRecordedProjectionTests: XCTestCase {
  func testRealtimeVoiceCompanionPreservesTheMainChatIdentity() {
    let main = AgentSurfaceReference.mainChat(chatId: "conversation-42")
    let surface = main.realtimeVoiceCompanion()
    XCTAssertEqual(surface.surfaceKind, "realtime_voice")
    XCTAssertEqual(surface.externalRefKind, "chat")
    XCTAssertEqual(surface.externalRefId, main.externalRefId)
  }

  func testVoiceContextSnapshotRejectsOnlyTheUnresolvedTransportSentinel() {
    XCTAssertFalse(KernelVoiceContextSnapshot.empty.isResolved)

    let blankNewConversation = KernelVoiceContextSnapshot(
      sessionId: "session-new",
      conversationId: "conversation-new",
      context: "",
      freshnessIdentity: "1:renderer:capabilities",
      contextPlanID: "plan-new",
      stableCacheIdentity: "sha256:stable-new",
      dynamicContextIdentity: "sha256:dynamic-new",
      semanticGuidance: "Kernel guidance",
      turnIDs: []
    )
    XCTAssertTrue(blankNewConversation.isResolved)
  }

  func testSpawnProjectionPinsItsProducingSurfaceAcrossLaterCompletion() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let pillsManager = AgentPillsManager.shared
    defer { pillsManager.quiesceProjectionRefreshForTesting() }
    let pillID = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000043"))
    let spawn = ChatContentBlock.agentSpawn(
      id: KernelAgentLifecycleMutation.stableSpawnBlockID(pillID: pillID),
      pillId: pillID,
      sessionId: "session-pinned",
      runId: "run-pinned",
      title: "Pinned agent",
      objective: "Finish after the user changes chats"
    )

    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "assistant-pinned-spawn",
        turnSeq: 1,
        content: "I started a background agent.",
        blocks: [spawn]
      ))

    XCTAssertEqual(
      pillsManager.producingJournalSurface(for: pillID),
      surface
    )
  }

  func testAgentCompletionEnrichesProducingSpawnTurnIdempotently() throws {
    let surface = AgentSurfaceReference.mainChat(chatId: "default")
    let pillID = try XCTUnwrap(UUID(uuidString: "00000000-0000-0000-0000-000000000042"))
    let spawn = ChatContentBlock.agentSpawn(
      id: KernelAgentLifecycleMutation.stableSpawnBlockID(pillID: pillID),
      pillId: pillID,
      sessionId: "session-1",
      runId: "run-1",
      title: "Research",
      objective: "Find the answer"
    )
    let originalResource = ChatResource.localGeneratedFile(
      id: "artifact-original",
      title: "original.md",
      subtitle: "text/markdown",
      mimeType: "text/markdown",
      uri: "file:///tmp/original.md"
    )
    let producedResource = ChatResource.localGeneratedFile(
      id: "artifact-result",
      title: "result.md",
      subtitle: "text/markdown",
      mimeType: "text/markdown",
      uri: "file:///tmp/result.md"
    )
    let producingTurn = try turn(
      surface: surface,
      turnId: "assistant-producing-spawn",
      turnSeq: 1,
      content: "I started a background agent.",
      blocks: [spawn],
      resources: [originalResource]
    )

    let first = try XCTUnwrap(
      KernelAgentLifecycleMutation.completion(
        in: [producingTurn],
        pillID: pillID,
        sessionID: "session-1",
        runID: "run-1",
        title: "Research",
        promptSnippet: "Find the answer",
        output: "The answer is 42.",
        status: "completed",
        resources: [producedResource]
      ))
    XCTAssertEqual(first.message.id, "assistant-producing-spawn")
    XCTAssertEqual(first.message.text, "I started a background agent.")
    XCTAssertEqual(first.message.resources.map(\.id), ["artifact-original", "artifact-result"])
    XCTAssertEqual(first.message.contentBlocks.count, 2)
    let atomicUpdate = KernelAgentLifecycleMutation.atomicAppendUpdate(first).dictionary
    XCTAssertNotNil(atomicUpdate["appendContentBlocks"])
    XCTAssertNotNil(atomicUpdate["appendResources"])
    XCTAssertNil(atomicUpdate["replaceContentBlocks"])
    XCTAssertNil(atomicUpdate["replaceResources"])
    XCTAssertNil(atomicUpdate["status"])
    XCTAssertNil(atomicUpdate["producingRunId"])

    let revisedTurn = try turn(
      surface: surface,
      turnId: first.message.id,
      turnSeq: 2,
      content: first.message.text,
      blocks: first.message.contentBlocks,
      resources: first.message.resources
    )
    let repeated = try XCTUnwrap(
      KernelAgentLifecycleMutation.completion(
        in: [producingTurn, revisedTurn],
        pillID: pillID,
        sessionID: "session-1",
        runID: "run-1",
        title: "Research",
        promptSnippet: "Find the answer",
        output: "The answer is 42.",
        status: "completed",
        resources: [producedResource]
      ))
    XCTAssertEqual(repeated.message.id, producingTurn.turnId)
    XCTAssertEqual(
      repeated.message.contentBlocks.filter {
        if case .agentCompletion = $0 { return true }
        return false
      }.count, 1)
    XCTAssertEqual(repeated.message.resources.map(\.id), ["artifact-original", "artifact-result"])
  }

  func testAgentCompletionRequiresPersistedProducingSpawn() throws {
    let surface = AgentSurfaceReference.mainChat(chatId: "default")
    let ordinary = try turn(
      surface: surface,
      turnId: "assistant-without-spawn",
      turnSeq: 1,
      content: "No child was started"
    )
    XCTAssertNil(
      KernelAgentLifecycleMutation.completion(
        in: [ordinary],
        pillID: UUID(),
        sessionID: nil,
        runID: nil,
        title: "Agent",
        promptSnippet: "Task",
        output: "Done",
        status: "completed",
        resources: []
      ))
  }

  func testLegacyBackendCollectorReadsEveryBoundedPageBeforeCheckpoint() async throws {
    let requested = Box<[(limit: Int, offset: Int)]>([])
    let rows = try await ChatLegacyPageCollector.all { limit, offset in
      requested.value.append((limit, offset))
      let end = min(offset + limit, 235)
      return offset < end ? Array(offset..<end) : []
    }

    XCTAssertEqual(rows, Array(0..<235))
    XCTAssertEqual(requested.value.map(\.limit), [100, 100, 100])
    XCTAssertEqual(requested.value.map(\.offset), [0, 100, 200])
    XCTAssertEqual(ChatLegacyCompatibilityMetadata.owner, "desktop-main-chat")
    XCTAssertFalse(ChatLegacyCompatibilityMetadata.removalCondition.isEmpty)
    XCTAssertEqual(ChatLegacyCompatibilityMetadata.removeBy, "2026-10-01")
  }

  func testLegacyBackendImportChronologyNormalizesCoarseTimestampPairs() {
    struct Row: Equatable {
      let id: String
      let createdAt: Date
      let sender: String
    }
    let timestamp = Date(timeIntervalSince1970: 100)
    let rows = [
      Row(id: "assistant", createdAt: timestamp, sender: "ai"),
      Row(id: "user", createdAt: timestamp, sender: "human"),
    ]

    let plan = ChatLegacyImportChronology.plan(
      rows,
      createdAt: { $0.createdAt },
      role: { $0.sender }
    )

    XCTAssertEqual(plan.map(\.row.id), ["user", "assistant"])
    XCTAssertEqual(plan.map(\.createdAtMs), [100_000, 100_001])
  }

  func testJournalProjectionUpsertsMutationByCanonicalTurnID() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "assistant-1",
        turnSeq: 1,
        content: "Part",
        status: .streaming
      ))
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "assistant-1",
        turnSeq: 2,
        content: "Part complete",
        status: .completed
      ))

    XCTAssertEqual(provider.messages.count, 1)
    XCTAssertEqual(provider.messages[0].id, "assistant-1")
    XCTAssertEqual(provider.messages[0].text, "Part complete")
    XCTAssertFalse(provider.messages[0].isStreaming)
  }

  func testRejectedJournalExchangeNeverCreatesAVisibleOrphan() async {
    let provider = ChatProvider()

    let rejected = await provider.admitJournalExchange(
      continuityKey: "typed-chat:rejected",
      userText: "Do not orphan me",
      assistantText: "Rejected",
      recordCanonicalExchange: { false }
    )

    XCTAssertNil(rejected.user)
    XCTAssertNil(rejected.assistant)
    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testRejectedStreamingExchangeKeepsBothRowsInvisible() async {
    let provider = ChatProvider()
    let continuityKey = "typed-chat:second-half-collision"
    let user = ChatMessage(
      id: "typed-user",
      clientTurnId: continuityKey,
      text: "Keep this atomic",
      sender: .user
    )
    let assistant = ChatMessage(
      id: "typed-assistant",
      clientTurnId: continuityKey,
      text: "",
      sender: .ai,
      isStreaming: true
    )
    var captured: [KernelTurnProjection.ExchangeTurn] = []

    let admitted = await provider.admitStreamingJournalExchange(
      userMessage: user,
      assistantMessage: assistant
    ) { turns in
      captured = turns
      // The kernel transaction rejected its second half. Node's journal
      // behavioral test proves the first durable row rolls back; this surface
      // seam proves Swift cannot expose either row on that rejection.
      return nil
    }

    XCTAssertFalse(admitted)
    XCTAssertEqual(captured.count, 2)
    XCTAssertEqual(captured.map(\.status), [.completed, .streaming])
    XCTAssertEqual(captured.map(\.message.id), ["typed-user", "typed-assistant"])
    XCTAssertEqual(captured.last?.message.text, "")
    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testSuspendedOwnerAReplayCannotProjectAfterOwnerBInvalidation() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let ownerATurn = try turn(
      surface: surface,
      turnId: "owner-a-turn",
      turnSeq: 1,
      content: "Owner A private history"
    )
    let ownerBTurn = try turn(
      surface: surface,
      turnId: "owner-b-turn",
      turnSeq: 1,
      content: "Owner B history"
    )
    let ownerAPage = journalPage(conversationId: "conversation-a", turns: [ownerATurn])
    let ownerBPage = journalPage(conversationId: "conversation-b", turns: [ownerBTurn])
    let gate = SuspendedJournalListGate(ownerBPage: ownerBPage)
    var ownerID = "owner-a"
    let projection = KernelTurnProjection(
      host: provider,
      client: AgentClient.Session(harnessMode: "piMono"),
      ownerIDProvider: { ownerID },
      journalListOperation: { _, _, requestedOwnerID, _, _ in
        await gate.fetch(ownerID: requestedOwnerID, ownerAPage: ownerAPage)
      }
    )

    let ownerARefresh = Task { @MainActor in
      await projection.refresh(surface: surface)
    }
    await gate.waitUntilOwnerAStarted()

    ownerID = "owner-b"
    projection.invalidateOwnerState()
    await projection.refresh(surface: surface)
    await gate.releaseOwnerA(with: ownerAPage)
    await ownerARefresh.value

    XCTAssertEqual(provider.messages.map(\.id), ["owner-b-turn"])
    XCTAssertEqual(provider.messages.map(\.text), ["Owner B history"])
  }

  func testClearBootstrapsExactGenerationAfterOwnerProjectionInvalidation() async {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    var ownerID = "owner-a"
    var listCalls: [(ownerID: String, after: Int, limit: Int)] = []
    var clearCalls: [(ownerID: String, generation: Int)] = []
    let projection = KernelTurnProjection(
      host: provider,
      client: AgentClient.Session(harnessMode: "piMono"),
      ownerIDProvider: { ownerID },
      journalListOperation: { _, _, requestedOwnerID, afterTurnSeq, limit in
        listCalls.append((requestedOwnerID, afterTurnSeq, limit))
        return self.journalPage(
          conversationId: requestedOwnerID == "owner-a" ? "conversation-a" : "conversation-b",
          turns: [],
          generation: requestedOwnerID == "owner-a" ? 3 : 7
        )
      },
      journalClearOperation: { _, _, requestedOwnerID, expectedGeneration in
        clearCalls.append((requestedOwnerID, expectedGeneration))
        return 0
      },
      kernelReadyOperation: { true }
    )

    await projection.refresh(surface: surface)
    ownerID = "owner-b"
    projection.invalidateOwnerState()

    let cleared = await projection.clear(surface: surface, ownerID: "owner-b")
    XCTAssertTrue(cleared)
    XCTAssertEqual(listCalls.last?.ownerID, "owner-b")
    XCTAssertEqual(listCalls.last?.after, 0)
    XCTAssertEqual(listCalls.last?.limit, 1)
    XCTAssertEqual(clearCalls.map(\.ownerID), ["owner-b"])
    XCTAssertEqual(clearCalls.map(\.generation), [7])
  }

  func testTemporaryAutomationOwnerKeepsFaultResetOnKernelBoundary() async {
    let suiteName = "KernelTurnRecordedProjectionTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      return XCTFail("failed to create isolated defaults")
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    var clearCalls: [(ownerID: String, generation: Int)] = []
    let projection = KernelTurnProjection(
      host: provider,
      client: AgentClient.Session(harnessMode: "piMono"),
      ownerIDProvider: {
        RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: true)
      },
      journalListOperation: { _, _, ownerID, _, _ in
        self.journalPage(conversationId: "fault-conversation", turns: [], generation: 9)
      },
      journalClearOperation: { _, _, ownerID, generation in
        clearCalls.append((ownerID, generation))
        return 0
      },
      kernelReadyOperation: { true }
    )

    XCTAssertNil(RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: true))
    let cleared = await RuntimeOwnerIdentity.withAutomationOwnerIfMissing(
      "desktop-harness-reset-omi-fault",
      defaults: defaults
    ) {
      await projection.clear(surface: surface)
    }

    XCTAssertTrue(cleared)
    XCTAssertEqual(clearCalls.map(\.ownerID), ["desktop-harness-reset-omi-fault"])
    XCTAssertEqual(clearCalls.map(\.generation), [9])
    XCTAssertNil(
      RuntimeOwnerIdentity.currentOwnerId(defaults: defaults, allowAutomationOverride: true),
      "the temporary owner must not turn an auth-recovery fault bundle into a signed-in session"
    )
  }

  func testClearOwnerSurfaceStateUsesAuthoritativeJournalControlWhenModelReadinessIsUnavailable() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "visible-before-reset",
        turnSeq: 1,
        content: "This must be cleared only after the journal confirms it"
      ))
    var modelReadinessRequests = 0
    var clearCalls: [(ownerID: String, generation: Int)] = []
    let projection = KernelTurnProjection(
      host: provider,
      client: AgentClient.Session(harnessMode: "piMono"),
      ownerIDProvider: { "fault-harness-owner" },
      journalListOperation: { _, _, ownerID, afterTurnSeq, limit in
        XCTAssertEqual(ownerID, "fault-harness-owner")
        XCTAssertEqual(afterTurnSeq, 0)
        XCTAssertEqual(limit, 1)
        return self.journalPage(conversationId: "fault-harness-conversation", turns: [], generation: 9)
      },
      journalClearOperation: { _, _, ownerID, expectedGeneration in
        clearCalls.append((ownerID, expectedGeneration))
        return 1
      },
      kernelReadyOperation: {
        modelReadinessRequests += 1
        return false
      }
    )

    let cleared = await projection.clearOwnerSurfaceState(chatId: "default")

    XCTAssertTrue(cleared)
    XCTAssertEqual(modelReadinessRequests, 0)
    XCTAssertEqual(clearCalls.map(\.ownerID), ["fault-harness-owner"])
    XCTAssertEqual(clearCalls.map(\.generation), [9])
    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testFaultHarnessResetUsesCredentialFreeControlClearOnceAndCompletesProjectionReset() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let statusStore = AgentRuntimeStatusStore.shared
    statusStore.reset()
    defer { statusStore.reset() }
    statusStore.beginRequest(surface: surface)
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "visible-before-fault-reset",
        turnSeq: 1,
        content: "This must disappear after the authoritative control clear"
      ))
    var modelReadinessRequests = 0
    var clearCalls: [(ownerID: String, generation: Int)] = []
    provider.kernelTurnProjection = KernelTurnProjection(
      host: provider,
      client: AgentClient.Session(harnessMode: "piMono"),
      ownerIDProvider: {
        RuntimeOwnerIdentity.currentOwnerId(allowAutomationOverride: true)
      },
      journalListOperation: { _, _, ownerID, afterTurnSeq, limit in
        XCTAssertFalse(ownerID.isEmpty)
        XCTAssertEqual(afterTurnSeq, 0)
        XCTAssertEqual(limit, 1)
        return self.journalPage(
          conversationId: "fault-harness-conversation",
          turns: [],
          generation: 9
        )
      },
      journalClearOperation: { _, _, ownerID, expectedGeneration in
        clearCalls.append((ownerID, expectedGeneration))
        return 1
      },
      kernelReadyOperation: {
        modelReadinessRequests += 1
        return false
      }
    )

    let error = await provider.performMainChatHarnessResetTransaction()

    XCTAssertNil(error)
    XCTAssertEqual(modelReadinessRequests, 0)
    XCTAssertEqual(clearCalls.map(\.generation), [9])
    XCTAssertTrue(provider.messages.isEmpty)
    XCTAssertNil(statusStore.projection(for: surface))
  }

  func testClearFailsClosedWhenGenerationBootstrapFails() async throws {
    struct BootstrapFailure: Error {}

    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "owner-b-visible",
        turnSeq: 1,
        content: "Keep visible when clear is rejected"
      ))
    var clearCallCount = 0
    let projection = KernelTurnProjection(
      host: provider,
      client: AgentClient.Session(harnessMode: "piMono"),
      ownerIDProvider: { "owner-b" },
      journalListOperation: { _, _, _, _, _ in throw BootstrapFailure() },
      journalClearOperation: { _, _, _, _ in
        clearCallCount += 1
        return 1
      },
      kernelReadyOperation: { true }
    )

    let cleared = await projection.clear(surface: surface, ownerID: "owner-b")
    XCTAssertFalse(cleared)
    XCTAssertEqual(clearCallCount, 0)
    XCTAssertEqual(provider.messages.map(\.id), ["owner-b-visible"])
  }

  func testRuntimeOwnerNotificationSynchronouslyInvalidatesVisibleProjection() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "owner-a-visible",
        turnSeq: 1,
        content: "Owner A history"
      ))
    XCTAssertEqual(provider.messages.map(\.id), ["owner-a-visible"])

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testJournalAdmissionPublishesImmediateProjectionWithOneStableIdentity() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let continuityKey = "typed-chat:request-9515"
    let expectedUserID = KernelTurnProjection.stableTurnID(
      continuityKey: continuityKey,
      role: "user"
    )
    let expectedAssistantID = KernelTurnProjection.stableTurnID(
      continuityKey: continuityKey,
      role: "assistant"
    )
    let userAck = try turn(
      surface: surface,
      turnId: expectedUserID,
      turnSeq: 1,
      role: "user",
      content: "Find one surprising memory insight"
    )
    let assistantAck = try turn(
      surface: surface,
      turnId: expectedAssistantID,
      turnSeq: 2,
      content: "I started an agent."
    )
    let admitted = await provider.admitJournalExchange(
      continuityKey: continuityKey,
      userText: "Find one surprising memory insight",
      assistantText: "I started an agent."
    ) {
      XCTAssertTrue(provider.messages.isEmpty, "no surface row may precede journal acceptance")
      provider.projectJournalTurn(userAck)
      provider.projectJournalTurn(assistantAck)
      return true
    }

    XCTAssertEqual(admitted.user?.id, expectedUserID)
    XCTAssertEqual(admitted.assistant?.id, expectedAssistantID)
    XCTAssertEqual(provider.messages.map(\.id), [expectedUserID, expectedAssistantID])
    // A restart/replay of the same revisions is also replace-only.
    provider.projectJournalTurn(userAck)
    provider.projectJournalTurn(assistantAck)

    XCTAssertEqual(provider.messages.count, 2)
    XCTAssertEqual(provider.messages.map(\.id), [expectedUserID, expectedAssistantID])
    XCTAssertEqual(provider.messages.map(\.sender), [.user, .ai])
  }

  func testIdenticalTextWithDistinctTurnIDsRemainsDistinct() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "user-1",
        turnSeq: 1,
        role: "user",
        content: "Same text"
      ))
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "user-2",
        turnSeq: 2,
        role: "user",
        content: "Same text"
      ))

    XCTAssertEqual(provider.messages.map(\.id), ["user-1", "user-2"])
    XCTAssertEqual(provider.messages.map(\.text), ["Same text", "Same text"])
  }

  func testStructuredBlocksResourcesAndContinuityMetadataSurviveProjection() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let blocks: [ChatContentBlock] = [
      .agentCompletion(
        id: "completion-1",
        pillId: UUID(uuidString: "00000000-0000-0000-0000-000000000001"),
        sessionId: "session-1",
        runId: "run-1",
        title: "Research complete",
        promptSnippet: "Find the answer",
        output: "42",
        status: "completed"
      )
    ]
    let resources = [
      ChatResource(
        id: "artifact:answer",
        origin: .generatedArtifact,
        title: "answer.md",
        subtitle: "text/markdown",
        mimeType: "text/markdown",
        thumbnailURL: nil,
        imageData: nil,
        uri: "omi-artifact://answer",
        artifactId: "answer",
        sessionId: "session-1",
        runId: "run-1",
        state: .ready
      )
    ]
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "assistant-structured",
        turnSeq: 1,
        content: "Finished",
        blocks: blocks,
        resources: resources,
        metadata: #"{"continuityKey":"continuity-1","notificationContext":"context"}"#
      ))

    let projected = try XCTUnwrap(provider.messages.first)
    XCTAssertEqual(projected.clientTurnId, "continuity-1")
    XCTAssertEqual(projected.notificationContext, "context")
    XCTAssertEqual(projected.resources.map(\.id), ["artifact:answer"])
    let journalTurn = try turn(
      surface: surface,
      turnId: "identity-check",
      turnSeq: 2,
      content: "identity"
    )
    XCTAssertEqual(journalTurn.producerId, "producer:identity-check")
    XCTAssertEqual(journalTurn.payloadHash, "sha256:identity-check")
    guard let firstBlock = projected.contentBlocks.first,
      case .agentCompletion(
        "completion-1", _, "session-1", "run-1", "Research complete", "Find the answer", "42", "completed"
      ) = firstBlock
    else {
      return XCTFail("Expected structured completion block to round-trip through the journal codec")
    }

    let automation = provider.automationMainChatSnapshot(limit: 10)
    let rowsData = try XCTUnwrap(automation["messages_json"]?.data(using: .utf8))
    let rows = try XCTUnwrap(
      JSONSerialization.jsonObject(with: rowsData) as? [[String: String]])
    let assistantRow = try XCTUnwrap(rows.first { $0["id"] == "assistant-structured" })
    let encodedBlocks = try XCTUnwrap(assistantRow["content_blocks_json"])
    let encodedResources = try XCTUnwrap(assistantRow["resources_json"])
    XCTAssertEqual(ChatContentBlockCodec.decode(encodedBlocks)?.count, 1)
    XCTAssertEqual(ChatResource.decodeResourcesFromPersistence(encodedResources).map(\.id), ["artifact:answer"])
  }

  func testFailedEmptyPlaceholderIsRemovedFromProjection() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "assistant-empty",
        turnSeq: 1,
        content: "",
        status: .streaming
      ))
    XCTAssertEqual(provider.messages.count, 1)

    provider.projectJournalTurn(
      try turn(
        surface: surface,
        turnId: "assistant-empty",
        turnSeq: 2,
        content: "",
        status: .failed
      ))
    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testProjectionRejectsAnotherSurface() throws {
    let provider = ChatProvider()
    provider.projectJournalTurn(
      try turn(
        surface: .workstream(workstreamId: "workstream-1"),
        turnId: "wrong-surface",
        turnSeq: 1,
        content: "Do not project"
      ))
    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testReplayStopsAtGapAndAcceptsOutOfOrderCompleteRange() throws {
    let surface = AgentSurfaceReference.mainChat(chatId: "default")
    let first = try turn(surface: surface, turnId: "turn-1", turnSeq: 1, content: "one")
    let second = try turn(surface: surface, turnId: "turn-2", turnSeq: 2, content: "two")
    let third = try turn(surface: surface, turnId: "turn-1", turnSeq: 3, content: "one revised")

    XCTAssertEqual(
      KernelJournalReplay.contiguousTurns(from: [third, first], after: 0).map(\.turnSeq),
      [1]
    )
    XCTAssertEqual(
      KernelJournalReplay.contiguousTurns(from: [third, first, second], after: 0).map(\.turnSeq),
      [1, 2, 3]
    )
    let postClear = try turn(
      surface: surface,
      turnId: "turn-after-clear",
      turnSeq: 7,
      content: "new generation"
    )
    XCTAssertEqual(
      KernelJournalReplay.contiguousTurns(from: [postClear], after: 6).map(\.turnSeq),
      [7]
    )
  }

  func testJournalChangedHandlerIsReplaceOnly() async throws {
    final class Counter: @unchecked Sendable {
      private let lock = NSLock()
      private var value = 0
      func increment() { lock.withLock { value += 1 } }
      var count: Int { lock.withLock { value } }
    }

    let runtime = AgentRuntimeProcess()
    let bridge = AgentBridge(runtime: runtime)
    let counter = Counter()
    let changed = try turn(
      surface: .mainChat(chatId: "default"),
      turnId: "turn-1",
      turnSeq: 1,
      content: "hello"
    )
    await bridge.setJournalTurnChangedHandler { _ in counter.increment() }
    await bridge.setJournalTurnChangedHandler { _ in counter.increment() }

    let handlerCount = await runtime.journalTurnChangedHandlerCount()
    XCTAssertEqual(handlerCount, 1)
    await runtime.dispatchJournalTurnChangedForTesting(changed)
    XCTAssertEqual(counter.count, 1)
  }

  func testBackendSyncRejectsClientMessageIDDifferentFromTurnID() {
    let valid: [String: Any] = [
      "ownerId": "owner-1",
      "turnId": "turn-1",
      "conversationId": "conversation-1",
      "clientMessageId": "turn-1",
      "conversationGeneration": 3,
      "attemptCount": 2,
      "deliveryGeneration": 4,
      "payloadHash": "sha256:payload",
      "journalRevision": 11,
      "text": "hello",
      "sender": "human",
      "messageSource": "desktop_chat",
    ]
    XCTAssertEqual(KernelJournalBackendSyncDriver.Request(payload: valid)?.turnId, "turn-1")
    XCTAssertEqual(KernelJournalBackendSyncDriver.Request(payload: valid)?.ownerId, "owner-1")
    XCTAssertEqual(KernelJournalBackendSyncDriver.Request(payload: valid)?.journalRevision, 11)

    var invalid = valid
    invalid["clientMessageId"] = "another-id"
    XCTAssertNil(KernelJournalBackendSyncDriver.Request(payload: invalid))

    invalid = valid
    invalid.removeValue(forKey: "payloadHash")
    XCTAssertNil(KernelJournalBackendSyncDriver.Request(payload: invalid))

    invalid = valid
    invalid.removeValue(forKey: "ownerId")
    XCTAssertNil(KernelJournalBackendSyncDriver.Request(payload: invalid))

    invalid = valid
    invalid["journalRevision"] = 0
    XCTAssertNil(KernelJournalBackendSyncDriver.Request(payload: invalid))

  }

  func testBackendSyncRejectsOwnerChangeBeforeHTTP() async throws {
    let request = try XCTUnwrap(
      KernelJournalBackendSyncDriver.Request(payload: [
        "ownerId": "impossible-owner-\(UUID().uuidString)",
        "turnId": "turn-1",
        "conversationId": "conversation-1",
        "clientMessageId": "turn-1",
        "conversationGeneration": 3,
        "attemptCount": 2,
        "deliveryGeneration": 4,
        "payloadHash": "sha256:payload",
        "journalRevision": 11,
        "text": "hello",
        "sender": "human",
        "messageSource": "desktop_chat",
      ]))

    do {
      _ = try await KernelJournalBackendSyncDriver.shared.sync(request)
      XCTFail("owner mismatch must fail before backend POST")
    } catch {
      XCTAssertEqual(
        KernelJournalBackendSyncDriver.boundedErrorCode(for: error),
        "backend_sync_owner_changed"
      )
    }
  }

  func testBackendSyncUsesBoundedPermanentAndTransientErrorCodes() {
    XCTAssertEqual(
      KernelJournalBackendSyncDriver.boundedErrorCode(
        for: APIError.httpError(statusCode: 422, detail: "payload rejected")
      ),
      "backend_sync_http_4xx"
    )
    XCTAssertEqual(
      KernelJournalBackendSyncDriver.boundedErrorCode(
        for: APIError.httpError(statusCode: 503, detail: "unavailable")
      ),
      "backend_sync_failed"
    )
    for statusCode in [408, 425, 429] {
      XCTAssertEqual(
        KernelJournalBackendSyncDriver.boundedErrorCode(
          for: APIError.httpError(statusCode: statusCode, detail: "retry")
        ),
        "backend_sync_http_retryable"
      )
    }
    XCTAssertEqual(
      KernelJournalBackendSyncDriver.boundedErrorCode(
        for: URLError(.networkConnectionLost)
      ),
      "backend_sync_failed"
    )
  }

  /// Static architecture tripwire; behavioral journal coverage lives above.
  func testKernelJournalIsOnlyDurableDesktopChatWriter() throws {
    let provider = try sourceFile("Providers/ChatProvider.swift")
    let taskState = try sourceFile(
      "ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")
    let taskStorage = try sourceFile("Rewind/Core/TaskChatMessageStorage.swift")
    let realtime = try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
    let runtime = try sourceFile("Chat/AgentRuntimeProcess.swift")

    XCTAssertFalse(provider.contains("APIClient.shared.saveMessage("))
    XCTAssertFalse(provider.contains("messages.append(greetingMessage)"))
    XCTAssertFalse(provider.contains("func recordCompletedTurn("))
    XCTAssertTrue(provider.contains("remoteId: response.messageId"))
    XCTAssertTrue(provider.contains("canonicalTurnId: response.messageId"))
    XCTAssertTrue(provider.contains("await kernelTurnProjection.refresh(surface: surface)"))
    let greetingStart = try XCTUnwrap(provider.range(of: "private func fetchInitialMessage("))
    let greetingSource = provider[greetingStart.lowerBound...]
    let admission = try XCTUnwrap(greetingSource.range(of: "guard accepted else"))
    let preview = try XCTUnwrap(greetingSource.range(of: "sessions[index].preview = response.message"))
    let analytics = try XCTUnwrap(greetingSource.range(of: "initialMessageGenerated("))
    XCTAssertLessThan(admission.lowerBound, preview.lowerBound)
    XCTAssertLessThan(preview.lowerBound, analytics.lowerBound)
    XCTAssertEqual(provider.components(separatedBy: "APIClient.shared.getMessages(").count - 1, 2)
    XCTAssertEqual(provider.components(separatedBy: "expectedOwnerId: ownerId").count - 1, 3)
    XCTAssertFalse(taskState.contains("persistMessage("))
    XCTAssertFalse(taskStorage.contains("PersistableRecord"))
    XCTAssertFalse(taskStorage.contains("func insert("))
    XCTAssertFalse(taskStorage.contains("func save("))
    XCTAssertFalse(taskStorage.contains("func getMessages("))
    XCTAssertFalse(taskStorage.contains("func getMessagesForWorkstream("))
    XCTAssertFalse(taskStorage.contains("func search("))
    XCTAssertFalse(realtime.contains("RealtimeVoiceTurnOutbox"))
    XCTAssertFalse(runtime.contains("import_conversation_turns"))
    XCTAssertFalse(runtime.contains("record_surface_turn"))
    XCTAssertFalse(runtime.contains("project_cross_surface_turn"))
    XCTAssertFalse(runtime.contains("turn_recorded"))
    let projection = try sourceFile("Chat/KernelTurnProjection.swift")
    let floating = try sourceFile("FloatingControlBar/FloatingControlBarWindow.swift")
    let pills = try sourceFile("FloatingControlBar/AgentPill.swift")
    XCTAssertTrue(provider.contains("AgentPillsManager.shared.bindProducingJournalSurface("))
    XCTAssertTrue(floating.contains("pill?.producingJournalSurface"))
    XCTAssertTrue(pills.contains("producingSurface: pill.producingJournalSurface"))
    for source in [projection, floating, pills] {
      XCTAssertFalse(source.contains("recordSurfaceTurn"))
      XCTAssertFalse(source.contains("projectCrossSurfaceTurn"))
      XCTAssertFalse(source.contains("pill_completion"))
      XCTAssertFalse(source.contains("[Background agent id="))
    }
  }

  private func turn(
    surface: AgentSurfaceReference,
    turnId: String,
    turnSeq: Int,
    role: String = "assistant",
    content: String,
    status: KernelJournalTurnStatus = .completed,
    blocks: [ChatContentBlock] = [],
    resources: [ChatResource] = [],
    metadata: String = "{}"
  ) throws -> KernelJournalTurn {
    let contentBlocks =
      ChatContentBlockCodec.encode(blocks)
      .flatMap(Self.jsonArray) ?? []
    let encodedResources =
      ChatResource.encodeResourcesForPersistence(resources)
      .flatMap(Self.jsonArray) ?? []
    return try XCTUnwrap(
      KernelJournalTurn(dictionary: [
        "conversationId": "conversation-1",
        "turnId": turnId,
        "turnSeq": turnSeq,
        "conversationGeneration": 1,
        "generationBaseTurnSeq": 0,
        "producerId": "producer:\(turnId)",
        "payloadHash": "sha256:\(turnId)",
        "role": role,
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
        "content": content,
        "origin": "test",
        "status": status.rawValue,
        "contentBlocks": contentBlocks,
        "resources": encodedResources,
        "metadataJson": metadata,
        "createdAtMs": 1_700_000_000_000 + turnSeq,
        "updatedAtMs": 1_700_000_000_000 + turnSeq,
      ]))
  }

  private static func jsonArray(_ raw: String) -> [Any]? {
    guard let data = raw.data(using: .utf8) else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [Any]
  }

  private func journalPage(
    conversationId: String,
    turns: [KernelJournalTurn],
    generation: Int = 1
  ) -> AgentRuntimeProcess.JournalOperationResult {
    AgentRuntimeProcess.JournalOperationResult(
      operation: "list",
      conversationId: conversationId,
      turn: nil,
      turns: turns,
      clearedCount: 0,
      highWaterTurnSeq: turns.map(\.turnSeq).max() ?? 0,
      conversationGeneration: generation,
      generationBaseTurnSeq: 0
    )
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources", isDirectory: true)
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}

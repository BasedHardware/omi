import XCTest

@testable import Omi_Computer

final class MessageMetadataTests: XCTestCase {
  func testCompletedTurnUsesKernelSnapshotNotAServedModel() throws {
    let metadata = try MessageMetadata.fromCompletedTurn(
      snapshot: makeSnapshot(
        sources: [
          ("memories", "available"),
          ("tasks", "empty"),
          ("goals", "unavailable"),
          ("screen", "redacted"),
        ],
        retainedTurnCount: 12,
        totalTurnCount: 40,
        allowedToolNames: ["get_daily_recap", "execute_sql", "get_conversations"]
      ),
      profile: try makeProfile(adapterId: "pi-mono", credentialScope: "managed_cloud"),
      imageByteCount: nil,
      toolNames: ["get_daily_recap", "get_conversations", "execute_sql", "execute_sql"],
      sqlRowsReturned: 0,
      sqlQueryCount: 1
    )

    XCTAssertEqual(
      metadata.sourceOutcomes.map { "\($0.source):\($0.outcome)" },
      ["memories:available", "goals:unavailable", "tasks:empty", "screen:redacted"]
    )
    XCTAssertEqual(metadata.historySummary, "12 of 40 turns (28 omitted)")
    XCTAssertEqual(metadata.offeredToolsSummary, "3 tools")
    XCTAssertEqual(metadata.pathSummary, "pi-mono · managed")
    XCTAssertEqual(metadata.sqlSummary, "1 query · 0 rows")
    XCTAssertEqual(metadata.screenshotSummary, "None")
    XCTAssertEqual(metadata.toolNames, ["get_daily_recap", "get_conversations", "execute_sql", "execute_sql"])
  }

  func testBYOKPathAndScreenshotAreObservedFacts() throws {
    let metadata = try MessageMetadata.fromCompletedTurn(
      snapshot: makeSnapshot(sources: [], retainedTurnCount: 0, totalTurnCount: 0, allowedToolNames: []),
      profile: try makeProfile(adapterId: "pi-mono", credentialScope: "local_user"),
      imageByteCount: 2048,
      toolNames: [],
      sqlRowsReturned: 0,
      sqlQueryCount: 0
    )

    XCTAssertEqual(metadata.pathSummary, "pi-mono · BYOK")
    XCTAssertEqual(metadata.screenshotSummary, "1 image (2 KB)")
    XCTAssertNil(metadata.sqlSummary)
    XCTAssertEqual(metadata.historySummary, "none")
    XCTAssertEqual(metadata.offeredToolsSummary, "0 tools")
  }

  func testResponseContextPopoverDoesNotClaimAServedModelOrPromptBody() throws {
    // omi-test-quality: source-inspection -- static contract: Response Context must not restore
    // Full System Prompt, XML prompt-count parsers, or untrusted token/cost usage. The Model row
    // returned in #12331-follow-up by Nik's direction, but ONLY bound to `modelsSummary` — the
    // response-OBSERVED served identities (chunk.model from the provider stream; verified live:
    // the managed gateway lane serves and reports "gpt-5.6-luna") — never the request alias that
    // #11521 removed as dishonest.
    let popover = try String(contentsOfFile: popoverSourcePath(), encoding: .utf8)
    XCTAssertFalse(popover.contains("Full System Prompt"))
    XCTAssertFalse(popover.contains("Context in Prompt"))
    XCTAssertTrue(popover.contains("metadata.modelsSummary"))
    XCTAssertFalse(popover.contains("metadata.adapterModel"))
    XCTAssertFalse(popover.contains("requestedModel"))
    XCTAssertFalse(popover.contains("memoriesCount"))
    XCTAssertFalse(popover.contains("metadata.tokenSummary"))
    XCTAssertFalse(popover.contains("metadata.costSummary"))
    XCTAssertFalse(popover.contains("Kernel gen"))
    XCTAssertTrue(popover.contains("Context admitted"))
    XCTAssertTrue(popover.contains("metadata.historySummary"))

    // omi-test-quality: source-inspection -- static contract: completion must stamp kernel snapshot evidence, not a kernel-hash systemPrompt.
    let provider = try String(contentsOfFile: chatProviderSourcePath(), encoding: .utf8)
    XCTAssertTrue(provider.contains("MessageMetadata.fromCompletedTurn"))
    XCTAssertFalse(provider.contains("systemPrompt: \"kernel-context:"))
  }

  private func makeProfile(adapterId: String, credentialScope: String) throws -> AgentExecutionProfile {
    try XCTUnwrap(
      AgentExecutionProfile(dictionary: [
        "profileGeneration": 1,
        "adapterId": adapterId,
        "credentialScope": credentialScope,
        "modelProfile": "claude-sonnet-4-6",
        "workingDirectory": "/tmp",
        "executionRole": "coordinator",
      ])
    )
  }

  private func makeSnapshot(
    sources: [(String, String)],
    retainedTurnCount: Int,
    totalTurnCount: Int,
    allowedToolNames: [String]
  ) throws -> AgentContextSnapshot {
    let omitted = totalTurnCount - retainedTurnCount
    return try XCTUnwrap(
      AgentContextSnapshot(dictionary: [
        "snapshotId": "snapshot-id",
        "version": "sha256:version",
        "snapshotGeneration": 11,
        "rendererPolicyVersion": "kernel-context-renderer@1",
        "rendererFingerprint": "renderer-2",
        "capabilityVersion": "1:digest",
        "renderedContext": "[Kernel Context Snapshot]",
        "contextPlan": [
          "version": 1,
          "planId": "sha256:plan",
          "semanticGuidanceVersion": "kernel-semantic-guidance@1",
          "semanticGuidance": "Kernel-owned semantic guidance.",
          "retainedTurnStartSeq": retainedTurnCount == 0 ? NSNull() : 1,
          "retainedTurnEndSeq": retainedTurnCount == 0 ? NSNull() : retainedTurnCount,
          "retainedTurnCount": retainedTurnCount,
          "totalTurnCount": totalTurnCount,
          "omittedTurnCount": omitted,
          "olderHistoryStrategy": omitted > 0 ? "truncated" : "none",
          "stableCacheIdentity": "sha256:stable",
          "dynamicContextIdentity": "sha256:dynamic",
        ] as [String: Any],
        "ownerId": "owner",
        "sessionId": "session",
        "conversationId": "conversation",
        "recentTurns": [],
        "sourceOutcomes": sources.map { source, outcome in
          [
            "source": source,
            "sourceRevision": "revision",
            "outcome": outcome,
          ] as [String: Any]
        },
        "activeRuns": [],
        "capabilities": [
          "executionRole": "coordinator",
          "manifestVersion": 1,
          "manifestDigest": "sha256:digest",
          "allowedToolNames": allowedToolNames,
        ],
      ])
    )
  }

  private func popoverSourcePath() -> String {
    sourcePath("FloatingControlBar/AIResponseView.swift")
  }

  private func chatProviderSourcePath() -> String {
    sourcePath("Providers/ChatProvider.swift")
  }

  private func sourcePath(_ relative: String) -> String {
    let testsDir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    return
      testsDir
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relative)
      .path
  }
}

/// Served-model attribution: the Response Context "Model" row must reflect the
/// models observed on the turn's completions, and a journaled voice turn must
/// round-trip its attribution through the kernel metadata so the (i) survives
/// surfaces that never run ChatProvider's typed finalize path.
@MainActor
final class MessageMetadataModelAttributionTests: XCTestCase {
  func testModelsSummaryJoinsObservedIdentities() {
    XCTAssertEqual(MessageMetadata(modelsUsed: ["gpt-5.6-luna"]).modelsSummary, "gpt-5.6-luna")
    XCTAssertEqual(
      MessageMetadata(modelsUsed: ["gpt-5.6-luna", "claude-sonnet-4-6"]).modelsSummary,
      "gpt-5.6-luna, claude-sonnet-4-6")
    XCTAssertEqual(MessageMetadata().modelsSummary, "")
  }

  func testJournalWritePersistsModelsAndChatMessageRestoresThem() throws {
    var message = ChatMessage(
      id: "turn-a", clientTurnId: "ck-1", text: "answer", sender: .ai)
    message.metadata = MessageMetadata(
      adapterId: "realtime", modelsUsed: ["gemini-3.1-flash-live-preview"])
    let write = message.journalWrite(
      origin: "realtime_voice", status: .completed,
      continuityKey: "ck-1", messageSource: "realtime_voice")

    let object =
      try JSONSerialization.jsonObject(with: Data(write.metadataJSON.utf8)) as? [String: Any]
    XCTAssertEqual(object?["modelsUsed"] as? [String], ["gemini-3.1-flash-live-preview"])

    let turn = try XCTUnwrap(
      KernelJournalTurn(
        dictionary: [
          "turnId": "turn-a",
          "role": "assistant",
          "origin": "realtime_voice",
          "status": "completed",
          "content": "answer",
          "metadataJson": write.metadataJSON,
          "createdAtMs": 1,
        ],
        surfaceFallback: AgentSurfaceReference(
          surfaceKind: "main_chat", externalRefKind: "", externalRefId: ""),
        conversationGenerationFallback: 1,
        generationBaseTurnSeqFallback: 0
      ))
    let restored = turn.chatMessage()
    XCTAssertEqual(restored.metadata?.modelsUsed, ["gemini-3.1-flash-live-preview"])
    XCTAssertEqual(restored.metadata?.adapterId, "realtime")
  }

  /// A voice projection pins the answering session's model at admission.
  func testVoiceProjectionAssistantMessageCarriesModel() {
    let projection = RealtimeStreamingJournalProjection(
      ownerID: "owner", continuityKey: "ck-2",
      admissionSurface: AgentSurfaceReference(
        surfaceKind: "main_chat", externalRefKind: "", externalRefId: ""),
      modelsUsed: ["gemini-3.1-flash-live-preview"])
    let message = projection.assistantMessage(text: "hi", isStreaming: true)
    XCTAssertEqual(message.metadata?.modelsUsed, ["gemini-3.1-flash-live-preview"])
  }
}

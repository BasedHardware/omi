import CryptoKit
import Foundation

struct KernelVoiceContextSnapshot: Equatable, Sendable {
  static let empty = KernelVoiceContextSnapshot(
    sessionId: "",
    conversationId: "",
    context: "",
    freshnessIdentity: "",
    turnIDs: []
  )

  let sessionId: String
  let conversationId: String
  let context: String
  let freshnessIdentity: String
  let turnIDs: Set<String>
}

struct KernelAutomationTurnRange: Equatable, Sendable {
  let conversationId: String
  let turns: [KernelJournalTurn]
}

/// Pure lifecycle mutation used by the journal writer and its behavioral
/// tests. A terminal agent fact enriches the assistant row that originally
/// produced the matching `agentSpawn`; it never creates a second chat turn.
@MainActor
enum KernelAgentLifecycleMutation {
  struct Result {
    let sourceTurn: KernelJournalTurn
    let message: ChatMessage
    let completionBlock: ChatContentBlock
    let resources: [ChatResource]
  }

  static func completion(
    in revisions: [KernelJournalTurn],
    pillID: UUID,
    sessionID: String?,
    runID: String?,
    title: String,
    promptSnippet: String,
    output: String,
    status: String,
    resources: [ChatResource]
  ) -> Result? {
    var latestByTurnID: [String: KernelJournalTurn] = [:]
    for revision in revisions {
      if let current = latestByTurnID[revision.turnId], current.turnSeq >= revision.turnSeq {
        continue
      }
      latestByTurnID[revision.turnId] = revision
    }

    let normalizedRunID = normalized(runID)
    guard let sourceTurn = latestByTurnID.values
      .filter({ $0.role == "assistant" })
      .filter({ turn in
        let blocks = ChatContentBlockCodec.decode(turn.contentBlocksJSON) ?? []
        return blocks.contains { block in
          guard case .agentSpawn(_, let spawnPillID, _, let spawnRunID, _, _) = block else {
            return false
          }
          if spawnPillID == pillID { return true }
          guard let normalizedRunID else { return false }
          return normalized(spawnRunID) == normalizedRunID
        }
      })
      .max(by: { $0.turnSeq < $1.turnSeq })
    else { return nil }

    var message = sourceTurn.chatMessage()
    let completionID = stableCompletionBlockID(pillID: pillID, runID: normalizedRunID)
    let completion = ChatContentBlock.agentCompletion(
      id: completionID,
      pillId: pillID,
      sessionId: normalized(sessionID),
      runId: normalizedRunID,
      title: normalized(title) ?? "Background agent",
      promptSnippet: normalized(promptSnippet) ?? "Background agent",
      output: output.trimmingCharacters(in: .whitespacesAndNewlines),
      status: normalized(status) ?? "completed"
    )

    if let index = message.contentBlocks.firstIndex(where: {
      guard case .agentCompletion(let id, let existingPillID, _, let existingRunID, _, _, _, _) = $0
      else { return false }
      if id == completionID { return true }
      if let normalizedRunID { return normalized(existingRunID) == normalizedRunID }
      return existingPillID == pillID && normalized(existingRunID) == nil
    }) {
      message.contentBlocks[index] = completion
    } else {
      message.contentBlocks.append(completion)
    }

    for resource in resources {
      if let index = message.resources.firstIndex(where: { $0.id == resource.id }) {
        message.resources[index] = resource
      } else {
        message.resources.append(resource)
      }
    }
    return Result(
      sourceTurn: sourceTurn,
      message: message,
      completionBlock: completion,
      resources: resources
    )
  }

  static func atomicAppendUpdate(_ result: Result) -> KernelJournalTurnUpdate {
    KernelJournalTurnUpdate(
      turnId: result.sourceTurn.turnId,
      status: nil,
      content: nil,
      contentBlocksJSON: nil,
      appendContentBlocksJSON: ChatContentBlockCodec.encode([
        result.completionBlock
      ]) ?? "[]",
      resourcesJSON: nil,
      appendResourcesJSON: ChatResource.encodeResourcesForPersistence(
        result.resources
      ) ?? "[]",
      producingRunId: nil,
      metadataJSON: nil
    )
  }

  nonisolated static func stableSpawnBlockID(pillID: UUID) -> String {
    stableDigest(prefix: "agent_spawn", identity: pillID.uuidString.lowercased())
  }

  nonisolated static func stableCompletionBlockID(pillID: UUID, runID: String?) -> String {
    stableDigest(
      prefix: "agent_completion",
      identity: normalized(runID) ?? pillID.uuidString.lowercased()
    )
  }

  nonisolated private static func stableDigest(prefix: String, identity: String) -> String {
    let digest = SHA256.hash(data: Data("\(prefix)\u{0}\(identity)".utf8))
    return prefix + "_" + digest.prefix(12).map { String(format: "%02x", $0) }.joined()
  }

  nonisolated private static func normalized(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
}

/// Main-chat projection over the kernel-owned journal. Runtime notifications
/// are wakeups only; every mutation is replayed in contiguous turnSeq order.
@MainActor
final class KernelTurnProjection {
  private weak var host: ChatProvider?
  private var client: AgentClient.Session?
  private var eventToken: UUID?
  private var highWaterByConversation: [String: Int] = [:]
  private var generationByConversation: [String: Int] = [:]
  private var conversationBySurface: [String: String] = [:]
  private var refreshingSurfaces = Set<String>()
  private var refreshRequestedSurfaces = Set<String>()

  init(host: ChatProvider) {
    self.host = host
  }

  func attachClient(_ client: AgentClient.Session) async {
    self.client = client
    KernelJournalEventHub.shared.unsubscribe(eventToken)
    await KernelJournalEventHub.shared.attach(client: client)
    eventToken = KernelJournalEventHub.shared.subscribe(surface: nil) { [weak self] in
      guard let self, let surface = self.host?.mainChatSurfaceReference() else { return }
      Task { @MainActor [weak self] in await self?.refresh(surface: surface) }
    }
    if let surface = host?.mainChatSurfaceReference() {
      await refresh(surface: surface)
    }
  }

  /// Ordered replay. A gap never advances the checkpoint: the next page starts
  /// from the last contiguous turnSeq, so out-of-order wakeups cannot drop data.
  func refresh(surface: AgentSurfaceReference) async {
    guard let client else { return }
    let surfaceKey = surface.key
    if refreshingSurfaces.contains(surfaceKey) {
      refreshRequestedSurfaces.insert(surfaceKey)
      return
    }
    refreshingSurfaces.insert(surfaceKey)
    defer { refreshingSurfaces.remove(surfaceKey) }

    repeat {
      refreshRequestedSurfaces.remove(surfaceKey)
      var shouldContinue = true
      while shouldContinue {
        let knownConversation = conversationBySurface[surfaceKey]
        let knownCheckpoint = knownConversation.map {
          checkpointKeyFor(conversationId: $0, surface: surface)
        }
        let after = knownCheckpoint.flatMap { highWaterByConversation[$0] } ?? 0
        do {
          let page = try await client.listJournalTurns(
            surface: surface,
            afterTurnSeq: after,
            limit: 100
          )
          let conversationId = page.conversationId
          guard !conversationId.isEmpty else {
            shouldContinue = false
            break
          }
          conversationBySurface[surfaceKey] = conversationId
          let checkpointKey = checkpointKeyFor(conversationId: conversationId, surface: surface)
          let currentGeneration = generationByConversation[checkpointKey]
          if currentGeneration != page.conversationGeneration {
            highWaterByConversation[checkpointKey] = page.generationBaseTurnSeq
            generationByConversation[checkpointKey] = page.conversationGeneration
            host?.resetJournalProjection(surface: surface)
          }
          generationByConversation[checkpointKey] = page.conversationGeneration
          var contiguous = highWaterByConversation[checkpointKey] ?? 0
          let contiguousPage = KernelJournalReplay.contiguousTurns(
            from: page.turns,
            after: contiguous
          )
          for turn in contiguousPage {
            host?.projectJournalTurn(turn)
            contiguous = turn.turnSeq
            highWaterByConversation[checkpointKey] = contiguous
          }
          let firstUnapplied = page.turns
            .filter { $0.turnSeq > contiguous }
            .min { $0.turnSeq < $1.turnSeq }
          if let firstUnapplied {
            log(
              "KernelTurnProjection: journal gap detected "
                + "(conversation=\(conversationId), expected=\(contiguous + 1), got=\(firstUnapplied.turnSeq))"
            )
            shouldContinue = false
          } else if contiguousPage.isEmpty || contiguous >= page.highWaterTurnSeq {
            shouldContinue = false
          } else if !shouldContinue {
            // Leave the checkpoint at the last contiguous sequence. A later
            // wakeup or explicit refresh requests the missing range again.
            break
          }
        } catch {
          log("KernelTurnProjection: journal replay failed (code=journal_range_fetch_failed)")
          shouldContinue = false
        }
      }
    } while refreshRequestedSurfaces.remove(surfaceKey) != nil
  }

  func reload(surface: AgentSurfaceReference) async {
    let surfaceKey = surface.key
    if let conversationId = conversationBySurface.removeValue(forKey: surfaceKey) {
      let key = checkpointKeyFor(conversationId: conversationId, surface: surface)
      highWaterByConversation.removeValue(forKey: key)
      generationByConversation.removeValue(forKey: key)
    }
    host?.resetJournalProjection(surface: surface)
    await refresh(surface: surface)
  }

  @discardableResult
  func recordTurn(
    surface: AgentSurfaceReference,
    message: ChatMessage,
    origin: String,
    status: KernelJournalTurnStatus,
    delivery: KernelJournalDelivery,
    continuityKey: String? = nil,
    producingRunId: String? = nil,
    appId: String? = nil,
    sessionId: String? = nil,
    messageSource: String? = nil,
    ownerID: String? = nil
  ) async -> KernelJournalTurn? {
    guard let host, await host.ensureBridgeStartedForKernel(), let client else { return nil }
    do {
      let turn = try await client.recordJournalTurn(
        surface: surface,
        ownerID: ownerID,
        turn: message.journalWrite(
          origin: origin,
          status: status,
          delivery: delivery,
          continuityKey: continuityKey,
          producingRunId: producingRunId,
          appId: appId,
          sessionId: sessionId,
          messageSource: messageSource
        )
      )
      await refresh(surface: surface)
      return turn
    } catch {
      log("KernelTurnProjection: journal record failed (code=journal_record_failed)")
      return nil
    }
  }

  @discardableResult
  func updateTurn(
    surface: AgentSurfaceReference,
    message: ChatMessage,
    status: KernelJournalTurnStatus? = nil,
    producingRunId: String? = nil,
    ownerID: String? = nil
  ) async -> KernelJournalTurn? {
    guard let host, await host.ensureBridgeStartedForKernel(), let client else { return nil }
    do {
      let turn = try await client.updateJournalTurn(
        surface: surface,
        ownerID: ownerID,
        update: message.journalUpdate(status: status, producingRunId: producingRunId)
      )
      await refresh(surface: surface)
      return turn
    } catch {
      log("KernelTurnProjection: journal update failed (code=journal_update_failed)")
      return nil
    }
  }

  /// Convenience for a logical exchange. IDs derive from the opaque continuity
  /// key, so retries cannot create a second user/assistant row.
  @discardableResult
  func recordExchange(
    surface: AgentSurfaceReference,
    userText: String,
    assistantText: String,
    origin: String,
    continuityKey: String,
    assistantContentBlocks: [ChatContentBlock] = [],
    resources: [ChatResource] = [],
    producingRunId: String? = nil,
    ownerID: String? = nil
  ) async -> Bool {
    let delivery: KernelJournalDelivery = ["task_chat", "workstream"].contains(surface.surfaceKind)
      ? .local : .backend
    var succeeded = true
    if !userText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      let user = ChatMessage(
        id: Self.stableTurnID(continuityKey: continuityKey, role: "user"),
        clientTurnId: continuityKey,
        text: userText,
        sender: .user
      )
      succeeded = await recordTurn(
        surface: surface,
        message: user,
        origin: origin,
        status: .completed,
        delivery: delivery,
        continuityKey: continuityKey,
        producingRunId: producingRunId,
        messageSource: origin,
        ownerID: ownerID
      ) != nil
    }
    if !assistantText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      || !assistantContentBlocks.isEmpty || !resources.isEmpty
    {
      let assistant = ChatMessage(
        id: Self.stableTurnID(continuityKey: continuityKey, role: "assistant"),
        clientTurnId: continuityKey,
        text: assistantText.isEmpty ? "Done." : assistantText,
        sender: .ai,
        contentBlocks: assistantContentBlocks,
        resources: resources
      )
      succeeded = await recordTurn(
        surface: surface,
        message: assistant,
        origin: origin,
        status: .completed,
        delivery: delivery,
        continuityKey: continuityKey,
        producingRunId: producingRunId,
        messageSource: origin,
        ownerID: ownerID
      ) != nil && succeeded
    }
    return succeeded
  }

  /// Append one deterministic terminal block to the assistant turn that
  /// produced the matching agent spawn. The bounded retry closes the race where
  /// a fast child finishes before the parent spawn projection reaches SQLite.
  @discardableResult
  func appendAgentCompletion(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    pillID: UUID,
    sessionID: String?,
    runID: String?,
    title: String,
    promptSnippet: String,
    output: String,
    status: String,
    resources: [ChatResource] = [],
    maxLookupAttempts: Int = 8,
    retryDelayNanoseconds: UInt64 = 150_000_000
  ) async -> KernelJournalTurn? {
    guard let host, await host.ensureBridgeStartedForKernel(), let client else { return nil }
    let attempts = max(1, min(maxLookupAttempts, 8))
    for attempt in 0..<attempts {
      do {
        let revisions = try await journalRevisions(
          client: client,
          surface: surface,
          ownerID: ownerID
        )
        if let mutation = KernelAgentLifecycleMutation.completion(
          in: revisions,
          pillID: pillID,
          sessionID: sessionID,
          runID: runID,
          title: title,
          promptSnippet: promptSnippet,
          output: output,
          status: status,
          resources: resources
        ) {
          let turn = try await client.updateJournalTurn(
            surface: surface,
            ownerID: ownerID,
            update: KernelAgentLifecycleMutation.atomicAppendUpdate(mutation)
          )
          await refresh(surface: surface)
          return turn
        }
      } catch {
        log("KernelTurnProjection: agent completion update failed (code=journal_agent_completion_failed)")
      }
      if attempt + 1 < attempts, retryDelayNanoseconds > 0 {
        try? await Task.sleep(nanoseconds: retryDelayNanoseconds)
      }
    }
    log("KernelTurnProjection: matching agent spawn unavailable (code=journal_agent_spawn_missing)")
    return nil
  }

  func clear(surface: AgentSurfaceReference, ownerID: String? = nil) async -> Bool {
    guard let host, await host.ensureBridgeStartedForKernel(), let client else { return false }
    do {
      let checkpointKey = conversationBySurface[surface.key].map {
        checkpointKeyFor(conversationId: $0, surface: surface)
      }
      let expectedGeneration = checkpointKey.flatMap { generationByConversation[$0] }
      _ = try await client.clearJournalTurns(
        surface: surface,
        ownerID: ownerID,
        expectedGeneration: expectedGeneration
      )
      for key in highWaterByConversation.keys where key.hasSuffix("|\(surface.key)") {
        highWaterByConversation.removeValue(forKey: key)
        generationByConversation.removeValue(forKey: key)
      }
      conversationBySurface.removeValue(forKey: surface.key)
      host.resetJournalProjection(surface: surface)
      return true
    } catch {
      log("KernelTurnProjection: journal clear failed (code=journal_clear_failed)")
      return false
    }
  }

  func clearOwnerSurfaceState(chatId: String = "default") async {
    _ = await clear(surface: .mainChat(chatId: chatId))
  }

  @discardableResult
  func importRemoteTurn(
    surface: AgentSurfaceReference,
    turn: KernelJournalRemoteTurn,
    ownerID: String? = nil
  ) async -> Bool {
    guard let host, await host.ensureBridgeStartedForKernel(), let client else { return false }
    do {
      _ = try await client.importRemoteJournalTurn(
        surface: surface,
        ownerID: ownerID,
        turn: turn
      )
      return true
    } catch {
      log("KernelTurnProjection: bounded legacy import failed (code=journal_legacy_import_failed)")
      return false
    }
  }

  func fetchVoiceContextSnapshot(
    surface: AgentSurfaceReference
  ) async -> KernelVoiceContextSnapshot {
    guard let host, await host.ensureBridgeStartedForKernel(), let client else {
      return .empty
    }
    do {
      let session = try await client.resolveSurfaceSession(surface)
      let snapshot = try await client.getContextSnapshot(
        sessionId: session.sessionId,
        surfaceKind: surface.surfaceKind)
      return Self.voiceContextSnapshot(from: snapshot, sessionId: session.sessionId)
    } catch {
      log("KernelTurnProjection: voice context snapshot fetch failed: \(error.localizedDescription)")
      return .empty
    }
  }

  func fetchJournalTurnTail(
    surface: AgentSurfaceReference,
    limit: Int = 8
  ) async -> KernelAutomationTurnRange? {
    guard let host, await host.ensureBridgeStartedForKernel(), let client else { return nil }
    do {
      let boundedLimit = max(1, min(limit, 100))
      var page = try await client.listJournalTurns(
        surface: surface,
        afterTurnSeq: 0,
        limit: 1
      )
      guard !page.conversationId.isEmpty else {
        return KernelAutomationTurnRange(conversationId: "", turns: [])
      }

      // The first range supplies the generation and high-water mark. Read from
      // the calculated tail boundary, retrying if a concurrent append moves the
      // high-water mark beyond the returned range.
      for _ in 0..<3 {
        let afterTurnSeq = max(
          page.generationBaseTurnSeq,
          page.highWaterTurnSeq - boundedLimit
        )
        page = try await client.listJournalTurns(
          surface: surface,
          afterTurnSeq: afterTurnSeq,
          limit: 100
        )
        let current = page.turns
          .filter { $0.conversationGeneration == page.conversationGeneration }
          .sorted { $0.turnSeq < $1.turnSeq }
        if page.highWaterTurnSeq <= page.generationBaseTurnSeq
          || current.last?.turnSeq == page.highWaterTurnSeq
        {
          return KernelAutomationTurnRange(
            conversationId: page.conversationId,
            turns: Array(current.suffix(boundedLimit))
          )
        }
      }
      let current = page.turns
        .filter { $0.conversationGeneration == page.conversationGeneration }
        .sorted { $0.turnSeq < $1.turnSeq }
      return KernelAutomationTurnRange(
        conversationId: page.conversationId,
        turns: Array(current.suffix(boundedLimit))
      )
    } catch {
      log("KernelTurnProjection: journal tail range fetch failed: \(error.localizedDescription)")
      return nil
    }
  }

  private func checkpointKeyFor(
    conversationId: String,
    surface: AgentSurfaceReference
  ) -> String {
    "\(conversationId)|\(surface.key)"
  }

  /// Reads one immutable 100-revision page at a time. If clear/reset advances
  /// the generation mid-read, restart from that generation's base rather than
  /// mixing two histories into the lifecycle match.
  private func journalRevisions(
    client: AgentClient.Session,
    surface: AgentSurfaceReference,
    ownerID: String?
  ) async throws -> [KernelJournalTurn] {
    var revisions: [KernelJournalTurn] = []
    var afterTurnSeq = 0
    var expectedGeneration: Int?
    var generationRestarts = 0
    while true {
      let page = try await client.listJournalTurns(
        surface: surface,
        ownerID: ownerID,
        afterTurnSeq: afterTurnSeq,
        limit: 100
      )
      if let currentGeneration = expectedGeneration,
        currentGeneration != page.conversationGeneration
      {
        generationRestarts += 1
        guard generationRestarts <= 2 else {
          throw NSError(
            domain: "KernelTurnProjection",
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "journal generation changed repeatedly"]
          )
        }
        revisions = []
        afterTurnSeq = page.generationBaseTurnSeq
        expectedGeneration = page.conversationGeneration
        continue
      }
      expectedGeneration = page.conversationGeneration
      revisions.append(contentsOf: page.turns)
      guard let lastTurnSeq = page.turns.map(\.turnSeq).max() else { break }
      afterTurnSeq = lastTurnSeq
      if afterTurnSeq >= page.highWaterTurnSeq { break }
    }
    return revisions
  }

  nonisolated static func stableTurnIDs(continuityKey: String) -> Set<String> {
    [
      stableTurnID(continuityKey: continuityKey, role: "user"),
      stableTurnID(continuityKey: continuityKey, role: "assistant"),
    ]
  }

  /// Canonical message identity for every projection of one logical journal turn.
  /// Optimistic UI rows must use this before SQLite/backend acknowledgement so
  /// reconciliation promotes them in place instead of replacing their identity.
  nonisolated static func stableTurnID(continuityKey: String, role: String) -> String {
    let digest = SHA256.hash(data: Data("\(continuityKey)\u{0}\(role)".utf8))
    return "turn_" + digest.prefix(16).map { String(format: "%02x", $0) }.joined()
  }

  nonisolated static func voiceContextSnapshot(
    from snapshot: AgentContextSnapshot,
    sessionId: String = ""
  ) -> KernelVoiceContextSnapshot {
    let freshnessIdentity = [
      snapshot.version,
      snapshot.rendererFingerprint,
      snapshot.capabilityVersion,
    ].joined(separator: ":")
    return KernelVoiceContextSnapshot(
      sessionId: sessionId,
      conversationId: snapshot.conversationId,
      context: snapshot.renderedContext,
      freshnessIdentity: freshnessIdentity,
      turnIDs: Set(snapshot.typedRecentTurns.map(\.turnId))
    )
  }
}

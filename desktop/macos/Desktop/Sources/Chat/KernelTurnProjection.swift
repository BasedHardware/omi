import CryptoKit
import Foundation

struct KernelVoiceContextSnapshot: Equatable, Sendable {
  static let empty = KernelVoiceContextSnapshot(
    sessionId: "",
    conversationId: "",
    context: "",
    freshnessIdentity: "",
    cachePlanID: "",
    stableCachePrefixFingerprint: "",
    dynamicContextFingerprint: "",
    retainedFirstTurnSeq: nil,
    retainedLastTurnSeq: nil,
    omittedTurnCount: 0,
    turnIDs: []
  )

  let sessionId: String
  let conversationId: String
  let context: String
  let freshnessIdentity: String
  let cachePlanID: String
  let stableCachePrefixFingerprint: String
  let dynamicContextFingerprint: String
  let retainedFirstTurnSeq: Int?
  let retainedLastTurnSeq: Int?
  let omittedTurnCount: Int
  let turnIDs: Set<String>

  /// `.empty` is a transport/bridge failure sentinel, not a valid blank
  /// conversation. A valid new conversation may render no text, but it still
  /// has a kernel session and a deterministic freshness identity.
  var isResolved: Bool {
    !sessionId.isEmpty && !freshnessIdentity.isEmpty && !cachePlanID.isEmpty
  }
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
          guard case .agentSpawn(_, let spawnPillID, _, let spawnRunID, _, _, _) = block else {
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
  private struct OwnerLease: Equatable {
    let ownerID: String
    let epoch: UInt64
  }

  struct ExchangeTurn {
    let message: ChatMessage
    let status: KernelJournalTurnStatus
  }

  typealias JournalListOperation = (
    _ client: AgentClient.Session,
    _ surface: AgentSurfaceReference,
    _ ownerID: String,
    _ afterTurnSeq: Int,
    _ limit: Int
  ) async throws -> AgentRuntimeProcess.JournalOperationResult

  typealias JournalClearOperation = (
    _ client: AgentClient.Session,
    _ surface: AgentSurfaceReference,
    _ ownerID: String,
    _ expectedGeneration: Int
  ) async throws -> Int

  typealias KernelReadyOperation = () async -> Bool

  private weak var host: ChatProvider?
  private var client: AgentClient.Session?
  private var eventToken: UUID?
  private let ownerIDProvider: () -> String?
  private let journalListOperation: JournalListOperation?
  private let journalClearOperation: JournalClearOperation?
  private let kernelReadyOperation: KernelReadyOperation?
  private var projectionEpoch: UInt64 = 0
  private var boundOwnerID: String?
  private var highWaterByConversation: [String: Int] = [:]
  private var generationByConversation: [String: Int] = [:]
  private var conversationBySurface: [String: String] = [:]
  private var refreshingSurfaceEpochs: [String: UInt64] = [:]
  private var refreshRequestedSurfaceEpochs: [String: UInt64] = [:]

  init(
    host: ChatProvider,
    client: AgentClient.Session? = nil,
    ownerIDProvider: @escaping () -> String? = { RuntimeOwnerIdentity.currentOwnerId() },
    journalListOperation: JournalListOperation? = nil,
    journalClearOperation: JournalClearOperation? = nil,
    kernelReadyOperation: KernelReadyOperation? = nil
  ) {
    self.host = host
    self.client = client
    self.ownerIDProvider = ownerIDProvider
    self.journalListOperation = journalListOperation
    self.journalClearOperation = journalClearOperation
    self.kernelReadyOperation = kernelReadyOperation
  }

  func attachClient(_ client: AgentClient.Session) async {
    self.client = client
    guard let lease = captureOwnerLease() else { return }
    KernelJournalEventHub.shared.unsubscribe(eventToken)
    await KernelJournalEventHub.shared.attach(client: client)
    guard isCurrent(lease) else { return }
    eventToken = KernelJournalEventHub.shared.subscribe(surface: nil) { [weak self] in
      Task { @MainActor [weak self] in
        guard let self, let surface = self.host?.mainChatSurfaceReference() else { return }
        await self.refresh(surface: surface)
      }
    }
    if let surface = host?.mainChatSurfaceReference() {
      await refresh(surface: surface, lease: lease)
    }
  }

  /// Synchronous owner teardown. Suspended work retains its old epoch and can
  /// neither mutate checkpoints nor project owner A rows after owner B starts.
  func invalidateOwnerState() {
    projectionEpoch &+= 1
    boundOwnerID = nil
    highWaterByConversation.removeAll()
    generationByConversation.removeAll()
    conversationBySurface.removeAll()
    refreshingSurfaceEpochs.removeAll()
    refreshRequestedSurfaceEpochs.removeAll()
    if let host {
      host.resetJournalProjection(surface: host.mainChatSurfaceReference())
    }
  }

  /// Ordered replay. A gap never advances the checkpoint: the next page starts
  /// from the last contiguous turnSeq, so out-of-order wakeups cannot drop data.
  func refresh(surface: AgentSurfaceReference) async {
    guard let lease = captureOwnerLease() else { return }
    await refresh(surface: surface, lease: lease)
  }

  private func refresh(surface: AgentSurfaceReference, lease: OwnerLease) async {
    guard isCurrent(lease), let client else { return }
    let surfaceKey = surface.key
    if refreshingSurfaceEpochs[surfaceKey] == lease.epoch {
      refreshRequestedSurfaceEpochs[surfaceKey] = lease.epoch
      return
    }
    refreshingSurfaceEpochs[surfaceKey] = lease.epoch
    defer {
      if refreshingSurfaceEpochs[surfaceKey] == lease.epoch {
        refreshingSurfaceEpochs.removeValue(forKey: surfaceKey)
      }
    }

    repeat {
      guard isCurrent(lease) else { return }
      if refreshRequestedSurfaceEpochs[surfaceKey] == lease.epoch {
        refreshRequestedSurfaceEpochs.removeValue(forKey: surfaceKey)
      }
      var shouldContinue = true
      while shouldContinue {
        guard isCurrent(lease) else { return }
        let knownConversation = conversationBySurface[surfaceKey]
        let knownCheckpoint = knownConversation.map {
          checkpointKeyFor(conversationId: $0, surface: surface)
        }
        let after = knownCheckpoint.flatMap { highWaterByConversation[$0] } ?? 0
        do {
          let page = try await listJournalTurns(
            client: client,
            surface: surface,
            ownerID: lease.ownerID,
            afterTurnSeq: after,
            limit: 100
          )
          guard isCurrent(lease) else { return }
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
            guard isCurrent(lease) else { return }
            host?.resetJournalProjection(surface: surface)
          }
          generationByConversation[checkpointKey] = page.conversationGeneration
          var contiguous = highWaterByConversation[checkpointKey] ?? 0
          let contiguousPage = KernelJournalReplay.contiguousTurns(
            from: page.turns,
            after: contiguous
          )
          for turn in contiguousPage {
            guard isCurrent(lease) else { return }
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
          if isCurrent(lease) {
            log("KernelTurnProjection: journal replay failed (code=journal_range_fetch_failed)")
          }
          shouldContinue = false
        }
      }
    } while isCurrent(lease) && refreshRequestedSurfaceEpochs[surfaceKey] == lease.epoch
  }

  func reload(surface: AgentSurfaceReference) async {
    guard let lease = captureOwnerLease(), isCurrent(lease) else { return }
    let surfaceKey = surface.key
    if let conversationId = conversationBySurface.removeValue(forKey: surfaceKey) {
      let key = checkpointKeyFor(conversationId: conversationId, surface: surface)
      highWaterByConversation.removeValue(forKey: key)
      generationByConversation.removeValue(forKey: key)
    }
    guard isCurrent(lease) else { return }
    host?.resetJournalProjection(surface: surface)
    await refresh(surface: surface, lease: lease)
  }

  @discardableResult
  func recordTurn(
    surface: AgentSurfaceReference,
    message: ChatMessage,
    origin: String,
    status: KernelJournalTurnStatus,
    continuityKey: String? = nil,
    appId: String? = nil,
    sessionId: String? = nil,
    messageSource: String? = nil,
    ownerID: String? = nil
  ) async -> KernelJournalTurn? {
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return nil }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return nil }
    do {
      let turn = try await client.recordJournalTurn(
        surface: surface,
        ownerID: lease.ownerID,
        turn: message.journalWrite(
          origin: origin,
          status: status,
          continuityKey: continuityKey,
          appId: appId,
          sessionId: sessionId,
          messageSource: messageSource
        )
      )
      guard isCurrent(lease) else { return nil }
      await refresh(surface: surface, lease: lease)
      guard isCurrent(lease) else { return nil }
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
    ownerID: String? = nil
  ) async -> KernelJournalTurn? {
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return nil }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return nil }
    do {
      let turn = try await client.updateJournalTurn(
        surface: surface,
        ownerID: lease.ownerID,
        update: message.journalUpdate(status: status)
      )
      guard isCurrent(lease) else { return nil }
      await refresh(surface: surface, lease: lease)
      guard isCurrent(lease) else { return nil }
      return turn
    } catch {
      log("KernelTurnProjection: journal update failed (code=journal_update_failed)")
      return nil
    }
  }

  @discardableResult
  func terminalizeTurn(
    surface: AgentSurfaceReference,
    turnId: String,
    message: ChatMessage?,
    producingRunId: String,
    producingAttemptId: String,
    disposition: KernelJournalTerminalDisposition,
    acceptedContent: String? = nil,
    acceptedResources: [ChatResource]? = nil,
    ownerID: String
  ) async -> KernelJournalTurn? {
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return nil }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return nil }
    let acceptedText = message.flatMap { $0.text.isEmpty ? nil : $0.text } ?? acceptedContent
    let terminalization = KernelJournalTurnTerminalization(
      turnId: turnId,
      producingRunId: producingRunId,
      producingAttemptId: producingAttemptId,
      disposition: disposition,
      content: disposition == .accept ? acceptedText : nil,
      contentBlocksJSON: disposition == .accept
        ? message.flatMap { ChatContentBlockCodec.encode($0.contentBlocks) }
        : nil,
      resourcesJSON: disposition == .accept
        ? message.flatMap { ChatResource.encodeResourcesForPersistence($0.displayResources) }
          ?? acceptedResources.flatMap { resources in
            resources.isEmpty ? nil : ChatResource.encodeResourcesForPersistence(resources)
          }
        : nil
    )
    do {
      let turn = try await client.terminalizeJournalTurn(
        surface: surface,
        ownerID: lease.ownerID,
        terminalization: terminalization
      )
      guard isCurrent(lease) else { return nil }
      await refresh(surface: surface, lease: lease)
      return isCurrent(lease) ? turn : nil
    } catch {
      log("KernelTurnProjection: journal terminalization failed (code=journal_terminalize_failed)")
      return nil
    }
  }

  /// Terminalize an existing turn without sourcing payload from the current UI
  /// projection. Stopped turns can legitimately have no visible placeholder;
  /// lifecycle durability must not depend on one being present.
  @discardableResult
  func updateTurnStatus(
    surface: AgentSurfaceReference,
    turnId: String,
    status: KernelJournalTurnStatus,
    ownerID: String? = nil
  ) async -> KernelJournalTurn? {
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return nil }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return nil }
    do {
      let turn = try await client.updateJournalTurn(
        surface: surface,
        ownerID: lease.ownerID,
        update: .statusOnly(turnId: turnId, status: status)
      )
      guard isCurrent(lease) else { return nil }
      await refresh(surface: surface, lease: lease)
      guard isCurrent(lease) else { return nil }
      return turn
    } catch {
      log("KernelTurnProjection: journal status update failed (code=journal_status_update_failed)")
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
    ownerID: String? = nil
  ) async -> Bool {
    let baseDate = Date()
    var writes: [KernelJournalTurnWrite] = []
    if !userText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      let user = ChatMessage(
        id: Self.stableTurnID(continuityKey: continuityKey, role: "user"),
        clientTurnId: continuityKey,
        text: userText,
        createdAt: baseDate,
        sender: .user
      )
      writes.append(user.journalWrite(
        origin: origin,
        status: .completed,
        continuityKey: continuityKey,
        messageSource: origin
      ))
    }
    if !assistantText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      || !assistantContentBlocks.isEmpty || !resources.isEmpty
    {
      let assistant = ChatMessage(
        id: Self.stableTurnID(continuityKey: continuityKey, role: "assistant"),
        clientTurnId: continuityKey,
        text: assistantText.isEmpty ? "Done." : assistantText,
        createdAt: baseDate.addingTimeInterval(0.001),
        sender: .ai,
        contentBlocks: assistantContentBlocks,
        resources: resources
      )
      writes.append(assistant.journalWrite(
        origin: origin,
        status: .completed,
        continuityKey: continuityKey,
        messageSource: origin
      ))
    }

    return await recordExchange(
      surface: surface,
      writes: writes,
      ownerID: ownerID
    ) != nil
  }

  /// Admit prebuilt visible turns under one journal transaction. This is the
  /// canonical typed/task-chat entry point because it preserves caller-owned
  /// message IDs, attachments, and a deliberately empty streaming placeholder.
  @discardableResult
  func recordExchange(
    surface: AgentSurfaceReference,
    turns: [ExchangeTurn],
    origin: String,
    continuityKey: String,
    appId: String? = nil,
    sessionId: String? = nil,
    messageSource: String,
    ownerID: String? = nil
  ) async -> [KernelJournalTurn]? {
    let writes = turns.map { entry in
      entry.message.journalWrite(
        origin: origin,
        status: entry.status,
        continuityKey: continuityKey,
        appId: appId,
        sessionId: sessionId,
        messageSource: messageSource
      )
    }
    return await recordExchange(surface: surface, writes: writes, ownerID: ownerID)
  }

  @discardableResult
  private func recordExchange(
    surface: AgentSurfaceReference,
    writes: [KernelJournalTurnWrite],
    ownerID: String?
  ) async -> [KernelJournalTurn]? {
    guard !writes.isEmpty, writes.count <= 2 else { return nil }
    let roles = writes.map(\.role)
    guard roles == ["user"] || roles == ["assistant"]
      || roles == ["user", "assistant"]
    else { return nil }
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return nil }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return nil }

    do {
      let result = try await client.recordJournalExchange(
        surface: surface,
        ownerID: lease.ownerID,
        turns: writes
      )
      guard isCurrent(lease), result.operation == "record_exchange" else { return nil }
      let expectedTurnIDs = Set(writes.map(\.turnId))
      guard
        result.turns.count == writes.count,
        Set(result.turns.map(\.turnId)) == expectedTurnIDs,
        !result.conversationId.isEmpty
      else {
        log("KernelTurnProjection: journal exchange returned an invalid receipt")
        return nil
      }
      applyAcceptedExchange(result, surface: surface, lease: lease)
      return isCurrent(lease) ? result.turns : nil
    } catch {
      if isCurrent(lease) {
        log("KernelTurnProjection: journal exchange failed (code=journal_exchange_failed)")
      }
      return nil
    }
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
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return nil }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return nil }
    let attempts = max(1, min(maxLookupAttempts, 8))
    for attempt in 0..<attempts {
      guard isCurrent(lease) else { return nil }
      do {
        let revisions = try await journalRevisions(
          client: client,
          surface: surface,
          lease: lease
        )
        guard isCurrent(lease) else { return nil }
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
            ownerID: lease.ownerID,
            update: KernelAgentLifecycleMutation.atomicAppendUpdate(mutation)
          )
          guard isCurrent(lease) else { return nil }
          await refresh(surface: surface, lease: lease)
          guard isCurrent(lease) else { return nil }
          return turn
        }
      } catch {
        if isCurrent(lease) {
          log("KernelTurnProjection: agent completion update failed (code=journal_agent_completion_failed)")
        }
      }
      if attempt + 1 < attempts, retryDelayNanoseconds > 0 {
        try? await Task.sleep(nanoseconds: retryDelayNanoseconds)
        guard isCurrent(lease) else { return nil }
      }
    }
    log("KernelTurnProjection: matching agent spawn unavailable (code=journal_agent_spawn_missing)")
    return nil
  }

  func clear(surface: AgentSurfaceReference, ownerID: String? = nil) async -> Bool {
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return false }
    let kernelReady = if let kernelReadyOperation {
      await kernelReadyOperation()
    } else {
      await host.ensureBridgeStartedForKernel()
    }
    guard kernelReady, isCurrent(lease), let client else { return false }
    do {
      let surfaceKey = surface.key
      let checkpointKey = conversationBySurface[surfaceKey].map {
        checkpointKeyFor(conversationId: $0, surface: surface)
      }
      var expectedGeneration = checkpointKey.flatMap { generationByConversation[$0] }
      if expectedGeneration.map({ $0 <= 0 }) ?? true {
        let page = try await listJournalTurns(
          client: client,
          surface: surface,
          ownerID: lease.ownerID,
          afterTurnSeq: 0,
          limit: 1
        )
        guard isCurrent(lease),
          !page.conversationId.isEmpty,
          page.conversationGeneration > 0
        else { return false }
        let bootstrapCheckpointKey = checkpointKeyFor(
          conversationId: page.conversationId,
          surface: surface
        )
        conversationBySurface[surfaceKey] = page.conversationId
        generationByConversation[bootstrapCheckpointKey] = page.conversationGeneration
        expectedGeneration = page.conversationGeneration
      }
      guard isCurrent(lease), let expectedGeneration, expectedGeneration > 0 else { return false }
      if let journalClearOperation {
        _ = try await journalClearOperation(
          client,
          surface,
          lease.ownerID,
          expectedGeneration
        )
      } else {
        _ = try await client.clearJournalTurns(
          surface: surface,
          ownerID: lease.ownerID,
          expectedGeneration: expectedGeneration
        )
      }
      guard isCurrent(lease) else { return false }
      for key in highWaterByConversation.keys where key.hasSuffix("|\(surface.key)") {
        highWaterByConversation.removeValue(forKey: key)
        generationByConversation.removeValue(forKey: key)
      }
      conversationBySurface.removeValue(forKey: surfaceKey)
      host.resetJournalProjection(surface: surface)
      return true
    } catch {
      log("KernelTurnProjection: journal clear failed (code=journal_clear_failed)")
      return false
    }
  }

  func clearOwnerSurfaceState(chatId: String = "default") async -> Bool {
    await clear(surface: .mainChat(chatId: chatId))
  }

  @discardableResult
  func importRemoteTurn(
    surface: AgentSurfaceReference,
    turn: KernelJournalRemoteTurn,
    ownerID: String? = nil
  ) async -> Bool {
    guard let lease = captureOwnerLease(ownerID: ownerID), let host else { return false }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return false }
    do {
      _ = try await client.importRemoteJournalTurn(
        surface: surface,
        ownerID: lease.ownerID,
        turn: turn
      )
      return isCurrent(lease)
    } catch {
      log("KernelTurnProjection: bounded legacy import failed (code=journal_legacy_import_failed)")
      return false
    }
  }

  func fetchVoiceContextSnapshot(
    surface: AgentSurfaceReference
  ) async -> KernelVoiceContextSnapshot {
    guard let lease = captureOwnerLease(), let host else {
      return .empty
    }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else {
      return .empty
    }
    do {
      let session = try await client.resolveSurfaceSession(surface)
      guard isCurrent(lease) else { return .empty }
      let snapshot = try await client.getContextSnapshot(
        sessionId: session.sessionId,
        surfaceKind: surface.surfaceKind)
      guard isCurrent(lease) else { return .empty }
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
    guard let lease = captureOwnerLease(), let host else { return nil }
    guard await host.ensureBridgeStartedForKernel(), isCurrent(lease), let client else { return nil }
    do {
      let boundedLimit = max(1, min(limit, 100))
      var page = try await listJournalTurns(
        client: client,
        surface: surface,
        ownerID: lease.ownerID,
        afterTurnSeq: 0,
        limit: 1
      )
      guard isCurrent(lease) else { return nil }
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
        page = try await listJournalTurns(
          client: client,
          surface: surface,
          ownerID: lease.ownerID,
          afterTurnSeq: afterTurnSeq,
          limit: 100
        )
        guard isCurrent(lease) else { return nil }
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

  private func applyAcceptedExchange(
    _ result: AgentRuntimeProcess.JournalOperationResult,
    surface: AgentSurfaceReference,
    lease: OwnerLease
  ) {
    guard isCurrent(lease), let host else { return }
    let surfaceKey = surface.key
    conversationBySurface[surfaceKey] = result.conversationId
    let checkpointKey = checkpointKeyFor(
      conversationId: result.conversationId,
      surface: surface
    )
    if let generation = generationByConversation[checkpointKey],
      generation != result.conversationGeneration
    {
      highWaterByConversation[checkpointKey] = result.generationBaseTurnSeq
      generationByConversation[checkpointKey] = result.conversationGeneration
      guard isCurrent(lease) else { return }
      host.resetJournalProjection(surface: surface)
    } else if generationByConversation[checkpointKey] == nil {
      highWaterByConversation[checkpointKey] = result.generationBaseTurnSeq
      generationByConversation[checkpointKey] = result.conversationGeneration
    }

    for turn in result.turns.sorted(by: { $0.turnSeq < $1.turnSeq }) {
      guard isCurrent(lease) else { return }
      host.projectJournalTurn(turn)
    }

    let checkpoint = highWaterByConversation[checkpointKey]
      ?? result.generationBaseTurnSeq
    let contiguous = KernelJournalReplay.contiguousTurns(
      from: result.turns,
      after: checkpoint
    )
    if let last = contiguous.last {
      highWaterByConversation[checkpointKey] = last.turnSeq
    }
  }

  private func listJournalTurns(
    client: AgentClient.Session,
    surface: AgentSurfaceReference,
    ownerID: String,
    afterTurnSeq: Int,
    limit: Int
  ) async throws -> AgentRuntimeProcess.JournalOperationResult {
    if let journalListOperation {
      return try await journalListOperation(
        client,
        surface,
        ownerID,
        afterTurnSeq,
        limit
      )
    }
    return try await client.listJournalTurns(
      surface: surface,
      ownerID: ownerID,
      afterTurnSeq: afterTurnSeq,
      limit: limit
    )
  }

  private func captureOwnerLease(ownerID: String? = nil) -> OwnerLease? {
    guard let currentOwnerID = Self.normalizedOwnerID(ownerIDProvider()) else {
      return nil
    }
    if let ownerID {
      guard
        let requestedOwnerID = Self.normalizedOwnerID(ownerID),
        requestedOwnerID == currentOwnerID
      else { return nil }
    }
    if let boundOwnerID, boundOwnerID != currentOwnerID {
      invalidateOwnerState()
    }
    boundOwnerID = currentOwnerID
    return OwnerLease(ownerID: currentOwnerID, epoch: projectionEpoch)
  }

  private func isCurrent(_ lease: OwnerLease) -> Bool {
    projectionEpoch == lease.epoch
      && boundOwnerID == lease.ownerID
      && Self.normalizedOwnerID(ownerIDProvider()) == lease.ownerID
  }

  nonisolated private static func normalizedOwnerID(_ ownerID: String?) -> String? {
    guard let ownerID else { return nil }
    let normalized = ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }

  /// Reads one immutable 100-revision page at a time. If clear/reset advances
  /// the generation mid-read, restart from that generation's base rather than
  /// mixing two histories into the lifecycle match.
  private func journalRevisions(
    client: AgentClient.Session,
    surface: AgentSurfaceReference,
    lease: OwnerLease
  ) async throws -> [KernelJournalTurn] {
    var revisions: [KernelJournalTurn] = []
    var afterTurnSeq = 0
    var expectedGeneration: Int?
    var generationRestarts = 0
    while true {
      guard isCurrent(lease) else { throw CancellationError() }
      let page = try await listJournalTurns(
        client: client,
        surface: surface,
        ownerID: lease.ownerID,
        afterTurnSeq: afterTurnSeq,
        limit: 100
      )
      guard isCurrent(lease) else { throw CancellationError() }
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
      snapshot.conversationContextPlan.planID,
    ].joined(separator: ":")
    return KernelVoiceContextSnapshot(
      sessionId: sessionId,
      conversationId: snapshot.conversationId,
      context: snapshot.renderedContext,
      freshnessIdentity: freshnessIdentity,
      cachePlanID: snapshot.conversationContextPlan.planID,
      stableCachePrefixFingerprint: snapshot.conversationContextPlan.stableCachePrefixFingerprint,
      dynamicContextFingerprint: snapshot.conversationContextPlan.dynamicContextFingerprint,
      retainedFirstTurnSeq: snapshot.conversationContextPlan.retainedFirstTurnSeq,
      retainedLastTurnSeq: snapshot.conversationContextPlan.retainedLastTurnSeq,
      omittedTurnCount: snapshot.conversationContextPlan.omittedTurnCount,
      turnIDs: Set(snapshot.typedRecentTurns.map(\.turnId))
    )
  }
}

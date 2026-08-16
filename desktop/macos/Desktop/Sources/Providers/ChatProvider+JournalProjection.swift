import Foundation

extension ChatProvider {
  private enum JournalProjectionDivergence: String {
    case duplicateTurn = "duplicate_turn"
    case ordering = "projection_order_overridden"
    case value = "projection_value_overridden"
    case continuityIdentity = "continuity_identity_overridden"
  }

  /// Projects a journal refresh as one visible transcript update. The kernel
  /// can return a complete saved history in several pages; treating each row
  /// as a live UI mutation makes startup replay visibly scroll through old
  /// messages. Keep the journal ordered at the boundary, then publish its
  /// complete projection atomically.
  func projectJournalTurns(_ turns: [KernelJournalTurn]) {
    guard !turns.isEmpty else { return }

    let expected = mainChatSurfaceReference()
    let voiceCompanion = expected.realtimeVoiceCompanion()
    var updatedMessages = messages
    var divergences: Set<JournalProjectionDivergence> = []

    for turn in turns {
      let isCanonicalChatSurface =
        turn.surfaceKind == expected.surfaceKind
        || turn.surfaceKind == voiceCompanion.surfaceKind
      guard isCanonicalChatSurface,
        turn.externalRefKind == expected.externalRefKind,
        turn.externalRefId == expected.externalRefId
      else { continue }

      let projected = turn.chatMessage()
      let matchingIndexes = updatedMessages.indices.filter { index in
        let existing = updatedMessages[index]
        if existing.id == projected.id { return true }
        guard let continuityKey = projected.clientTurnId else { return false }
        return existing.clientTurnId == continuityKey && existing.sender == projected.sender
      }
      if matchingIndexes.count > 1 {
        divergences.insert(.duplicateTurn)
      }
      if let index = matchingIndexes.first {
        let existing = updatedMessages[index]
        if existing.id != projected.id {
          divergences.insert(.continuityIdentity)
        } else if existing.journalStatus == nil,
          Self.journalOwnedValueDiffers(projected, from: existing)
        {
          divergences.insert(.value)
        }
      }
      for block in projected.contentBlocks {
        guard case .agentSpawn(_, let projectedPillID, _, _, _, _, _) = block,
          let pillID = projectedPillID
        else { continue }
        AgentPillsManager.shared.bindProducingJournalSurface(
          pillID: pillID,
          surface: expected
        )
      }

      let isEmptyTerminalPlaceholder =
        turn.status == .failed
        && projected.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        && projected.contentBlocks.isEmpty
        && projected.resources.isEmpty
      if isEmptyTerminalPlaceholder {
        updatedMessages.removeAll { $0.id == projected.id }
      } else if let index = updatedMessages.firstIndex(where: { $0.id == projected.id }) {
        updatedMessages[index] = Self.carryingLocalOnlyFields(projected, from: updatedMessages[index])
      } else if let continuityKey = projected.clientTurnId,
        let index = updatedMessages.firstIndex(where: {
          $0.clientTurnId == continuityKey && $0.sender == projected.sender
        })
      {
        updatedMessages[index] = Self.carryingLocalOnlyFields(projected, from: updatedMessages[index])
      } else {
        updatedMessages.append(projected)
      }
    }

    let orderBeforeCanonicalSort = updatedMessages.map(\.id)
    updatedMessages.sort {
      if $0.createdAt == $1.createdAt { return $0.id < $1.id }
      return $0.createdAt < $1.createdAt
    }
    if updatedMessages.map(\.id) != orderBeforeCanonicalSort {
      divergences.insert(.ordering)
    }
    messages = updatedMessages
    flushPendingMessageRatings()
    Task { await bindKindOnlyCitationsIfNeeded() }

    for divergence in divergences {
      DesktopDiagnosticsManager.shared.recordStateAuthoritySignal(
        seam: .chatTranscriptProjection,
        from: "in_memory_projection",
        to: "kernel_journal",
        direction: divergence.rawValue)
    }
  }

  func projectJournalTurn(_ turn: KernelJournalTurn) {
    projectJournalTurns([turn])
  }

  /// Local memories/conversations/tasks used to bind kind-only labels such as `[memory]` when the
  /// model copied a category name instead of the numeric marker.
  func kindCitationLookupReferences() async -> [ChatCitationReference] {
    let formatter = ISO8601DateFormatter()
    async let memories = (try? await MemoryStorage.shared.getLocalMemories(limit: 200)) ?? []
    async let conversations =
      (try? await TranscriptionStorage.shared.getLocalConversations(limit: 80)) ?? []
    async let tasks =
      (try? await ActionItemStorage.shared.getLocalActionItems(limit: 20, completed: false)) ?? []
    let loadedMemories = await memories
    let loadedConversations = await conversations
    let loadedTasks = await tasks
    return lookupReferences(
      memories: loadedMemories,
      conversations: loadedConversations,
      tasks: loadedTasks,
      formatter: formatter)
  }

  func applyKindOnlyCitationBinding(to messageId: String, base: [ChatCitationReference]) async {
    guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
    messages[index].bindInlineCitations(using: base)
    guard let current = messages.first(where: { $0.id == messageId }),
      current.hasKindOnlyCitationMarkers
    else { return }
    let searched = await searchedMemoryReferences(in: current)
    guard !searched.isEmpty,
      let index = messages.firstIndex(where: { $0.id == messageId })
    else { return }
    let existing = messages[index].contentBlocks.compactMap { block -> ChatCitationReference? in
      guard case .citation(_, let reference) = block else { return nil }
      return reference
    }
    messages[index].bindInlineCitations(
      using: ChatCitationReference.appendingLookup(searched, to: existing),
      allowUniqueKindFallback: false)
  }

  func finalizeAssistantMessageCitations(
    messageId: String,
    queryText: String,
    selectedReferences: [ChatCitationReference],
    requestedSources: Bool,
    terminalCitationReferences: [ChatCitationReference]
  ) async -> String {
    guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return queryText }
    let durableToolReferences = messages[index].contentBlocks.compactMap {
      block -> ChatCitationReference? in
      guard case .citation(_, let reference) = block else { return nil }
      return reference
    }
    let turnReferences = ChatCitationReference.merging(
      terminalCitationReferences,
      durableToolReferences,
      ChatCitationProvenanceRegistry.references(
        fromToolCallBlocks: messages[index].contentBlocks))
    messages[index].applySelectedSourceFallback(
      selectedReferences: selectedReferences,
      requestedSources: requestedSources,
      retrievedReferences: turnReferences,
      fallbackText: queryText)
    messages[index].isStreaming = false
    let bindBase: [ChatCitationReference]
    if messages[index].hasKindOnlyCitationMarkers {
      bindBase = ChatCitationReference.appendingLookup(
        await kindCitationLookupReferences(),
        to: turnReferences)
    } else {
      bindBase = turnReferences
    }
    await applyKindOnlyCitationBinding(to: messageId, base: bindBase)
    guard let current = messages.first(where: { $0.id == messageId }) else { return queryText }
    let visible = current.visibleAnswerText
    return visible.isEmpty ? current.text : visible
  }

  func bindKindOnlyCitationsIfNeeded() async {
    let needsBind = messages.contains { message in
      message.sender == .ai && !message.isStreaming && message.hasKindOnlyCitationMarkers
    }
    guard needsBind else { return }
    let lookup = await kindCitationLookupReferences()
    let ids = messages.compactMap { message -> String? in
      guard message.sender == .ai, !message.isStreaming, message.hasKindOnlyCitationMarkers else {
        return nil
      }
      return message.id
    }
    for id in ids {
      guard let message = messages.first(where: { $0.id == id }),
        message.sender == .ai,
        !message.isStreaming,
        message.hasKindOnlyCitationMarkers
      else { continue }
      let existing = message.contentBlocks.compactMap { block -> ChatCitationReference? in
        guard case .citation(_, let reference) = block else { return nil }
        return reference
      }
      await applyKindOnlyCitationBinding(
        to: id,
        base: ChatCitationReference.appendingLookup(lookup, to: existing))
    }
  }

  private func lookupReferences(
    memories: [ServerMemory],
    conversations: [ServerConversation],
    tasks: [TaskActionItem],
    formatter: ISO8601DateFormatter
  ) -> [ChatCitationReference] {
    var result = [ChatCitationReference]()
    var seen = Set<String>()
    var ordinal = 1
    func append(
      kind: ChatCitationReference.Kind,
      sourceID: String,
      title: String,
      preview: String,
      createdAt: Date?
    ) {
      let trimmed = sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !trimmed.isEmpty, seen.insert("\(kind.rawValue):\(trimmed)").inserted else { return }
      result.append(
        ChatCitationReference(
          ordinal: ordinal,
          kind: kind,
          sourceID: trimmed,
          title: title,
          preview: preview,
          createdAt: createdAt.map { formatter.string(from: $0) }))
      ordinal += 1
    }
    for memory in memories {
      append(
        kind: .memory,
        sourceID: memory.id,
        title: memory.headline ?? "Memory",
        preview: memory.content,
        createdAt: memory.createdAt)
    }
    for conversation in conversations {
      append(
        kind: .conversation,
        sourceID: conversation.id,
        title: conversation.structured.title.isEmpty ? "Conversation" : conversation.structured.title,
        preview: conversation.structured.overview,
        createdAt: conversation.createdAt)
    }
    for task in tasks {
      append(
        kind: .task,
        sourceID: task.id,
        title: task.description,
        preview: task.contextSummary ?? task.description,
        createdAt: task.createdAt)
    }
    return result
  }

  private func searchedMemoryReferences(in message: ChatMessage) async -> [ChatCitationReference] {
    let corpus =
      ([message.text]
      + message.contentBlocks.compactMap { block -> String? in
        guard case .text(_, let text) = block else { return nil }
        return text
      }).joined(separator: "\n")
    var memories = [ServerMemory]()
    var seen = Set<String>()
    for item in ChatCitationMarkup.kindOnlySearchQueries(in: corpus).prefix(16) {
      guard item.kind == .memory else { continue }
      for query in [item.query, item.fallback] where !query.isEmpty {
        let found =
          (try? await MemoryStorage.shared.searchLocalMemories(query: query, limit: 8)) ?? []
        for memory in found where seen.insert(memory.id).inserted {
          memories.append(memory)
        }
        if !found.isEmpty { break }
      }
    }
    return lookupReferences(
      memories: memories,
      conversations: [],
      tasks: [],
      formatter: ISO8601DateFormatter())
  }

  /// Compare only journal-owned values. The comparison may inspect content in
  /// process, but telemetry receives the bounded divergence kind only.
  private static func journalOwnedValueDiffers(
    _ projected: ChatMessage,
    from existing: ChatMessage
  ) -> Bool {
    projected.text != existing.text
      || projected.createdAt != existing.createdAt
      || projected.sender != existing.sender
      || projected.clientTurnId != existing.clientTurnId
      || projected.isStreaming != existing.isStreaming
      || projected.isSynced != existing.isSynced
      || ChatContentBlockCodec.comparisonData(projected.contentBlocks)
        != ChatContentBlockCodec.comparisonData(existing.contentBlocks)
      || projected.attachments != existing.attachments
      || projected.resources != existing.resources
  }
}

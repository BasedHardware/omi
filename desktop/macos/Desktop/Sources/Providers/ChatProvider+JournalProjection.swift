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
    // Whether any row will differ from what is published. A refresh after a
    // streaming write echoes a row the live projection already has (and is
    // ahead of), and publishing an identical transcript re-ran every observer
    // of `messages` — a second full transcript pass per journal round trip,
    // for nothing the reader could see.
    var changed = false

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
      func replace(at index: Int) {
        let merged = Self.carryingLocalOnlyFields(projected, from: updatedMessages[index])
        guard !merged.isProjectionEquivalent(to: updatedMessages[index]) else { return }
        updatedMessages[index] = merged
        changed = true
      }
      if isEmptyTerminalPlaceholder {
        let countBefore = updatedMessages.count
        updatedMessages.removeAll { $0.id == projected.id }
        if updatedMessages.count != countBefore { changed = true }
      } else if let index = updatedMessages.firstIndex(where: { $0.id == projected.id }) {
        replace(at: index)
      } else if let continuityKey = projected.clientTurnId,
        let index = updatedMessages.firstIndex(where: {
          $0.clientTurnId == continuityKey && $0.sender == projected.sender
        })
      {
        replace(at: index)
      } else {
        updatedMessages.append(projected)
        changed = true
      }
    }

    // Citation inheritance is a projection over the whole transcript rather
    // than part of any single row replacement: a refresh can echo every row
    // it read unchanged and still owe a restored follow-up the chips it
    // borrows from an earlier turn. The publication gate therefore sits
    // behind the citation projection, and what inheritance bound counts as a
    // change worth publishing.
    let orderBeforeCanonicalSort = updatedMessages.map(\.id)
    updatedMessages.sort {
      if $0.createdAt == $1.createdAt { return $0.id < $1.id }
      return $0.createdAt < $1.createdAt
    }
    Self.inheritCitationsAcrossTurns(&updatedMessages)
    if !changed,
      Self.citationBlockIdentifiers(of: updatedMessages)
        != Self.citationBlockIdentifiers(of: messages)
    {
      changed = true
    }
    guard changed else {
      flushPendingMessageRatings()
      return
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

  /// A settled follow-up that cites a number it never retrieved itself is
  /// pointing at an earlier turn's list (`ChatCitationMarkup.inheritedReferences`).
  /// The binding is a projection over the journal, not a row written to it: the
  /// references it borrows were already persisted on the turn that earned them,
  /// and re-deriving them here is what lets restored history open the same
  /// source the reader could open live.
  static func inheritCitationsAcrossTurns(_ messages: inout [ChatMessage]) {
    for index in messages.indices where messages[index].sender == .ai && !messages[index].isStreaming {
      let inherited = ChatCitationMarkup.inheritedReferences(
        citedIn: messages[index],
        resolved: messages[index].inlineCitationReferences,
        earlierTurns: Array(messages[..<index]))
      guard !inherited.isEmpty else { continue }
      messages[index].persistCitedReferences(from: inherited)
    }
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
    // The authoritative answer replaces every streamed projection, so the raw
    // accumulator this turn was built from has no further reader.
    streamingBuffer.finishStreaming(messageId: messageId)
    // The streamed projection applied sentence spacing to every flush; the
    // terminal answer must honor the same contract or a joined agent handoff
    // ("…handle it.Capture the…") that was only ever visible as fixed would
    // reappear the moment the turn settles — and be persisted that way.
    let normalizedTerminalText = Self.normalizeAssistantSentenceSpacing(queryText)
    messages[index].applyAuthoritativeTerminalAnswer(normalizedTerminalText)
    messages[index].applySelectedSourceFallback(
      selectedReferences: selectedReferences,
      requestedSources: requestedSources,
      retrievedReferences: turnReferences,
      fallbackText: normalizedTerminalText)
    messages[index].isStreaming = false
    // A number this turn never assigned is one the reader was shown a turn ago.
    let inheritedReferences = ChatCitationMarkup.inheritedReferences(
      citedIn: messages[index],
      resolved: turnReferences,
      earlierTurns: Array(messages[..<index]))
    let bindableReferences = turnReferences + inheritedReferences
    let bindBase: [ChatCitationReference]
    if messages[index].hasKindOnlyCitationMarkers {
      bindBase = ChatCitationReference.appendingLookup(
        await kindCitationLookupReferences(),
        to: bindableReferences)
    } else {
      bindBase = bindableReferences
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
      let formattedDate: String?
      if let createdAt = createdAt {
        formattedDate = formatter.string(from: createdAt)
      } else {
        formattedDate = nil
      }
      result.append(
        ChatCitationReference(
          ordinal: ordinal,
          kind: kind,
          sourceID: trimmed,
          title: title,
          preview: preview,
          createdAt: formattedDate))
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

  /// Every citation block's identity across the transcript, in order — the
  /// signal that the citation projection moved without any journal row doing.
  private static func citationBlockIdentifiers(of messages: [ChatMessage]) -> [String] {
    messages.flatMap { message in
      message.contentBlocks.compactMap { block -> String? in
        guard case .citation(let id, _) = block else { return nil }
        return id
      }
    }
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
      // Resource `imageData` never comes from the journal, so the comparison
      // is against what the replace would actually publish: the projection
      // with local bytes carried back. Otherwise every echo of a row holding
      // attachment bytes reported a divergence that changed nothing.
      || ChatResource.carryingImageData(projected.resources, from: existing.resources)
        != existing.resources
  }
}

extension ChatProvider {
  /// Upsert by canonical turn ID only. Text equality is deliberately ignored:
  /// two identical messages with distinct turn IDs are distinct journal rows.
  /// Some `ChatMessage` fields live only in the in-memory row and are never
  /// written to the kernel journal, so `KernelJournalTurn.chatMessage()` cannot
  /// reconstruct them and a journal projection can never be their authority:
  /// `rating` (user-set), `metadata` (model/token/cost stats attached at
  /// completion, rendered in the message footer), `notificationScreenshot`,
  /// per-resource `imageData` (attachment thumbnails the tile renders from
  /// memory once the picked file — often a temp export — disappears), and
  /// in-memory kind-only citation rewrites until the journal catches up.
  /// Replacing a row wholesale with the projection would drop them, so carry
  /// them forward from the row being replaced. A field the projection *does*
  /// carry (non-nil) wins, so this stays correct if the journal schema later
  /// starts persisting one of them.
  static func carryingLocalOnlyFields(_ projected: ChatMessage, from existing: ChatMessage) -> ChatMessage {
    var merged = projected
    merged.resources = ChatResource.carryingImageData(merged.resources, from: existing.resources)
    // A journal echo of a row this client is still streaming is the snapshot
    // it wrote a round trip ago; the live projection has moved on since. Taking
    // the echo's text put the visible answer a few words back on every write
    // and forward again on the next flush — the stutter the reader saw. The
    // journal stays the durable authority: a terminal or kernel-owned row is
    // never streaming and is taken whole, and a streaming echo that has more
    // than the live row (a restore from another writer) still wins.
    if existing.isStreaming, projected.isStreaming, existing.text.utf8.count >= projected.text.utf8.count {
      merged.text = existing.text
      merged.contentBlocks = existing.contentBlocks
    }
    if merged.rating == nil { merged.rating = existing.rating }
    if let replayed = merged.metadata {
      if let persisted = existing.metadata {
        // The journal replay reconstructs only the metadata the kernel
        // persists — today the served-model attribution — while the in-memory
        // row carries the rest of the completion evidence. A nil test here
        // would let an echo erase all of it. Merge field-by-field: the replay
        // wins a field it observably carries; the row keeps every field the
        // replay left at its default.
        merged.metadata = Self.mergingCompletionMetadata(persisted, fromReplay: replayed)
      }
    } else {
      merged.metadata = existing.metadata
    }
    if merged.notificationScreenshot == nil { merged.notificationScreenshot = existing.notificationScreenshot }
    // Kind-only binding rewrites markers and appends citation blocks in memory.
    // A stale journal echo still has `[memory]` and no citation blocks; keep the
    // already-bound row so chips do not vanish between hydrate and the next bind.
    if existing.hasPersistedCitationBlocks, !projected.hasPersistedCitationBlocks {
      merged.text = existing.text
      merged.contentBlocks = existing.contentBlocks
    }
    return merged
  }

  /// The replayed metadata wins every field it observably carries (anything
  /// off its default — a journal replay only fills what the kernel writes);
  /// every other field keeps the in-memory row's value.
  private static func mergingCompletionMetadata(
    _ persisted: MessageMetadata, fromReplay replayed: MessageMetadata
  ) -> MessageMetadata {
    var merged = replayed
    if !merged.hasScreenshot { merged.hasScreenshot = persisted.hasScreenshot }
    if merged.screenshotSizeBytes == nil { merged.screenshotSizeBytes = persisted.screenshotSizeBytes }
    if merged.toolNames.isEmpty { merged.toolNames = persisted.toolNames }
    if merged.sqlRowsReturned == 0 { merged.sqlRowsReturned = persisted.sqlRowsReturned }
    if merged.sqlQueryCount == 0 { merged.sqlQueryCount = persisted.sqlQueryCount }
    if merged.sourceOutcomes.isEmpty { merged.sourceOutcomes = persisted.sourceOutcomes }
    if merged.retainedTurnCount == 0 { merged.retainedTurnCount = persisted.retainedTurnCount }
    if merged.totalTurnCount == 0 { merged.totalTurnCount = persisted.totalTurnCount }
    if merged.omittedTurnCount == 0 { merged.omittedTurnCount = persisted.omittedTurnCount }
    if merged.offeredToolCount == 0 { merged.offeredToolCount = persisted.offeredToolCount }
    if merged.adapterId.isEmpty { merged.adapterId = persisted.adapterId }
    if merged.credentialScopeLabel.isEmpty { merged.credentialScopeLabel = persisted.credentialScopeLabel }
    if merged.modelsUsed.isEmpty { merged.modelsUsed = persisted.modelsUsed }
    if merged.screenContext == nil { merged.screenContext = persisted.screenContext }
    return merged
  }
}

extension ChatMessage {
  /// Whether publishing `self` in place of `other` would change anything a
  /// reader or a persisted projection could observe. Every stored field is
  /// compared; `Citation` has no equality of its own, so its identities stand
  /// in for it.
  func isProjectionEquivalent(to other: ChatMessage) -> Bool {
    id == other.id
      && clientTurnId == other.clientTurnId
      && text == other.text
      && createdAt == other.createdAt
      && sender == other.sender
      && isStreaming == other.isStreaming
      && rating == other.rating
      && isSynced == other.isSynced
      && citations.map(\.id) == other.citations.map(\.id)
      && contentBlocks == other.contentBlocks
      && metadata == other.metadata
      && notificationContext == other.notificationContext
      && notificationScreenshot == other.notificationScreenshot
      && attachments == other.attachments
      && resources == other.resources
      && turnOwner == other.turnOwner
      && journalStatus == other.journalStatus
      && hidesEmptyStreamingPlaceholder == other.hidesEmptyStreamingPlaceholder
  }
}

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

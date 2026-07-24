import Foundation

extension ChatProvider {
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

    for turn in turns {
      let isCanonicalChatSurface =
        turn.surfaceKind == expected.surfaceKind
        || turn.surfaceKind == voiceCompanion.surfaceKind
      guard isCanonicalChatSurface,
        turn.externalRefKind == expected.externalRefKind,
        turn.externalRefId == expected.externalRefId
      else { continue }

      let projected = turn.chatMessage()
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

    updatedMessages.sort {
      if $0.createdAt == $1.createdAt { return $0.id < $1.id }
      return $0.createdAt < $1.createdAt
    }
    messages = updatedMessages
  }

  func projectJournalTurn(_ turn: KernelJournalTurn) {
    projectJournalTurns([turn])
  }
}

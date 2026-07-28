import Foundation

/// Shared display projection for one background-agent lifecycle in the
/// kernel-backed transcript. Launch and completion remain distinct canonical
/// facts, but a single run has one stable visible row across every chat
/// surface.
enum AgentLifecycleDisplayProjection {
  private struct Location: Hashable {
    let messageIndex: Int
    let blockIndex: Int
  }

  private struct Completion {
    let location: Location
    let block: ChatContentBlock
  }

  static func project(_ canonicalMessages: [ChatMessage]) -> [ChatMessage] {
    var spawnByRunID: [String: Location] = [:]
    var spawnByPillID: [UUID: Location] = [:]

    for (messageIndex, message) in canonicalMessages.enumerated() {
      for (blockIndex, block) in message.contentBlocks.enumerated() {
        guard case .agentSpawn(_, let pillID, _, let runID, _, _, _) = block else { continue }
        if let runID = nonEmpty(runID) {
          spawnByRunID[runID] = spawnByRunID[runID] ?? Location(messageIndex: messageIndex, blockIndex: blockIndex)
        }
        if let pillID {
          spawnByPillID[pillID] = spawnByPillID[pillID] ?? Location(messageIndex: messageIndex, blockIndex: blockIndex)
        }
      }
    }

    var completionsBySpawn: [Location: [Completion]] = [:]
    var matchedCompletionLocations = Set<Location>()

    for (messageIndex, message) in canonicalMessages.enumerated() {
      for (blockIndex, block) in message.contentBlocks.enumerated() {
        guard case .agentCompletion(_, let pillID, _, let runID, _, _, _, _) = block else { continue }

        // A completion with a run ID may only complete that exact run.
        // Pill IDs are a legacy fallback when the completion lacks a
        // durable run identity.
        let spawn: Location?
        if let runID = nonEmpty(runID) {
          spawn = spawnByRunID[runID]
        } else if let pillID {
          spawn = spawnByPillID[pillID]
        } else {
          spawn = nil
        }
        guard let spawn else { continue }

        let completion = Completion(
          location: Location(messageIndex: messageIndex, blockIndex: blockIndex),
          block: block
        )
        completionsBySpawn[spawn, default: []].append(completion)
        matchedCompletionLocations.insert(completion.location)
      }
    }

    // Transcript wording is a presentation concern too: the canonical
    // lifecycle receipt retains exact identifiers, while both chat surfaces
    // render the safe projection below.
    var projectedMessages = canonicalMessages.map(AgentLifecycleTranscriptProjection.project)
    guard !completionsBySpawn.isEmpty else { return projectedMessages }
    for (spawn, completions) in completionsBySpawn {
      guard let latestCompletion = completions.last else { continue }
      projectedMessages[spawn.messageIndex].contentBlocks[spawn.blockIndex] = latestCompletion.block
      let completionResources = completions.flatMap { completion in
        canonicalMessages[completion.location.messageIndex].resources
      }
      projectedMessages[spawn.messageIndex].resources = mergeResources(
        existing: projectedMessages[spawn.messageIndex].resources,
        adding: completionResources
      )
    }

    // A completion source can also carry ordinary text/tool blocks. Keep
    // those blocks in their original row, but remove the already-projected
    // completion card so one run never renders twice. Terminal-only source
    // rows become empty and are hidden below.
    for messageIndex in canonicalMessages.indices {
      let message = canonicalMessages[messageIndex]
      guard !message.contentBlocks.isEmpty else { continue }
      let hasMatchedCompletion = message.contentBlocks.indices.contains { blockIndex in
        matchedCompletionLocations.contains(Location(messageIndex: messageIndex, blockIndex: blockIndex))
      }
      guard hasMatchedCompletion else { continue }
      // Start from the display copy: a same-row lifecycle has already
      // replaced its spawn block with the terminal completion above.
      // Filtering the canonical blocks here would accidentally restore
      // that old spawn card while removing the terminal block.
      let retainedBlocks = projectedMessages[messageIndex].contentBlocks.enumerated().compactMap { blockIndex, block in
        matchedCompletionLocations.contains(Location(messageIndex: messageIndex, blockIndex: blockIndex))
          ? nil
          : block
      }
      projectedMessages[messageIndex].contentBlocks = retainedBlocks
    }

    let hiddenCompletionMessages = Set(
      canonicalMessages.indices.filter { messageIndex in
        let message = canonicalMessages[messageIndex]
        guard message.sender == .ai, !message.contentBlocks.isEmpty else { return false }
        let hadMatchedCompletion = message.contentBlocks.indices.contains { blockIndex in
          matchedCompletionLocations.contains(Location(messageIndex: messageIndex, blockIndex: blockIndex))
        }
        return hadMatchedCompletion && projectedMessages[messageIndex].contentBlocks.isEmpty
      })

    return projectedMessages.enumerated().compactMap { messageIndex, message in
      hiddenCompletionMessages.contains(messageIndex) ? nil : message
    }
  }

  /// Resolves a viewport anchor through the same projection as the main
  /// transcript. A legacy terminal-only completion may be hidden after it is
  /// folded into its spawn row, so resolve that identity to the visible row.
  static func projectedMessage(id: String, in canonicalMessages: [ChatMessage]) -> ChatMessage? {
    let projectedMessages = project(canonicalMessages)
    if let exact = projectedMessages.first(where: { $0.id == id }) {
      return exact
    }
    guard let canonical = canonicalMessages.first(where: { $0.id == id }) else { return nil }
    let terminalBlocks = canonical.contentBlocks.filter { block in
      if case .agentCompletion = block { return true }
      return false
    }
    guard !terminalBlocks.isEmpty else { return canonical }
    return projectedMessages.first { message in
      message.contentBlocks.contains { displayedBlock in
        terminalBlocks.contains { terminalBlock in
          isSameRun(displayedBlock, terminalBlock)
        }
      }
    } ?? canonical
  }

  private static func isSameRun(_ lhs: ChatContentBlock, _ rhs: ChatContentBlock) -> Bool {
    guard case .agentCompletion(_, let lhsPillID, _, let lhsRunID, _, _, _, _) = lhs,
      case .agentCompletion(_, let rhsPillID, _, let rhsRunID, _, _, _, _) = rhs
    else { return false }
    if let lhsRunID = nonEmpty(lhsRunID), let rhsRunID = nonEmpty(rhsRunID) {
      return lhsRunID == rhsRunID
    }
    return lhsPillID != nil && lhsPillID == rhsPillID
  }

  private static func nonEmpty(_ value: String?) -> String? {
    let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? nil : trimmed
  }

  private static func mergeResources(existing: [ChatResource], adding: [ChatResource]) -> [ChatResource] {
    var seen = Set(existing.map(\.id))
    return existing + adding.filter { seen.insert($0.id).inserted }
  }
}

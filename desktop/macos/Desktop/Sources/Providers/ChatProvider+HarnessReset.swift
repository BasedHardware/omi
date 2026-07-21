import Foundation

extension ChatProvider {
  /// Harness-only chat reset that awaits backend deletion before returning.
  /// Returns an error message when backend deletion fails so E2E flows don't
  /// proceed against stale persisted messages.
  func automationResetChatForHarness() async -> String? {
    guard AppBuild.isNonProduction else { return nil }
    return await resetChatForAuthorizedHarness()
  }

  /// Completes a harness reset after its non-production automation entrypoint
  /// has established eligibility. The main-chat transaction sets
  /// `defaultJournalAlreadyCleared` only after its authoritative owner-scoped
  /// control clear has succeeded.
  func resetChatForAuthorizedHarness(defaultJournalAlreadyCleared: Bool = false) async -> String? {
    isClearing = true
    defer { isClearing = false }

    if isInDefaultChat {
      let runtimeChatId = mainChatRuntimeChatId(sessionId: nil)
      let surface = AgentSurfaceReference.mainChat(chatId: runtimeChatId)
      AgentRuntimeStatusStore.shared.clear(surface: surface)
      if !defaultJournalAlreadyCleared {
        guard await kernelTurnProjection.clear(surface: surface) else {
          return "failed to clear default kernel journal"
        }
      }
    } else {
      let sessionToDelete = currentSession
      if let session = sessionToDelete {
        let surface = AgentSurfaceReference.mainChat(chatId: session.id)
        AgentRuntimeStatusStore.shared.clear(surface: surface)
        guard await kernelTurnProjection.clear(surface: surface) else {
          return "failed to clear session kernel journal"
        }
      }
      if let session = sessionToDelete {
        sessions.removeAll { $0.id == session.id }
      }
      currentSession = nil
      messages = []
      resetMessagesPagination()
      _ = await createNewSession()
    }
    return nil
  }

  /// Reset isolation must clear the same kernel-owned surface the flow will
  /// exercise. Fault bundles intentionally have no authenticated owner, so
  /// establish a temporary non-production owner for this transaction rather
  /// than bypassing the owner boundary or carrying a synthetic session forward.
  func automationResetMainChatForHarness() async -> String? {
    guard AppBuild.isNonProduction else { return nil }
    return await performMainChatHarnessResetTransaction()
  }

  /// Performs the owner-scoped reset transaction after the automation entrypoint
  /// has established that the bundle is non-production.
  func performMainChatHarnessResetTransaction() async -> String? {
    let bundleScope = (Bundle.main.bundleIdentifier ?? "desktop")
      .replacingOccurrences(of: ".", with: "-")
    let resetOwnerID = "desktop-harness-reset-\(bundleScope)"
    return await RuntimeOwnerIdentity.withAutomationOwnerIfMissing(resetOwnerID) { [self] in
      let clear = await clearOwnerSurfaceStateForAuthorizedHarness(chatId: "default")
      if let error = clear["error"] {
        return error
      }
      return await resetChatForAuthorizedHarness(defaultJournalAlreadyCleared: true)
    }
  }
}

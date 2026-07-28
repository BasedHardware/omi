extension ChatProvider {
  func beginOnboardingJournal() {
    guard !isOnboarding else { return }
    preOnboardingMainMessages = messages
    isOnboarding = true
  }

  /// Delete only setup-owned conversation state. Onboarding is a local-only
  /// journal surface, so this can never enqueue a backend chat deletion or
  /// mutate the user's normal main-chat history.
  func clearOnboardingJournal() async -> Bool {
    let surface = AgentSurfaceReference.onboarding()
    AgentRuntimeStatusStore.shared.clear(surface: surface)
    return await kernelTurnProjection.clear(surface: surface, deleteBackend: false)
  }

  /// Leave the setup-only chat surface, purge its local transcript, and restore
  /// the authoritative main-chat projection before the product UI is revealed.
  func finishOnboardingJournal() async {
    let fallbackMessages = preOnboardingMainMessages ?? []
    _ = await clearOnboardingJournal()
    isOnboarding = false
    let reloaded = await kernelTurnProjection.reload(surface: mainChatSurfaceReference())
    if !reloaded {
      messages = fallbackMessages
      resetMessagesPagination()
    }
    preOnboardingMainMessages = nil
  }
}

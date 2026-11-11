#if DEBUG
  @MainActor
  extension PushToTalkManager {
    /// Installs the production effect handler without starting capture or
    /// muting system audio in hermetic owner-boundary tests.
    func installOwnerBoundaryEffectHandlerFixture() {
      configureVoiceTurnCoordinator(barState: FloatingControlBarState())
    }
  }
#endif

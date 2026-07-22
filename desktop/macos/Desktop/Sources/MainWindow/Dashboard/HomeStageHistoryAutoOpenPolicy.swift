struct HomeStageHistoryAutoOpenPolicy: Equatable {
  private var didAutoOpen = false

  mutating func shouldAutoOpen(isLegacy: Bool, mode: HomeStageMode, hasMessages: Bool) -> Bool {
    guard !didAutoOpen, !isLegacy, mode == .hub, hasMessages else { return false }
    didAutoOpen = true
    return true
  }

  mutating func suppressAutoOpenForExplicitHubClose() {
    didAutoOpen = true
  }
}
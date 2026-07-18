import Foundation

extension ChatProvider {
  /// Reset isolation must clear the same kernel-owned surface the flow will
  /// exercise. Fault bundles intentionally have no authenticated owner, so
  /// establish a temporary non-production owner for this transaction rather
  /// than bypassing the owner boundary or carrying a synthetic session forward.
  func automationResetMainChatForHarness() async -> String? {
    guard AppBuild.isNonProduction else { return nil }
    let bundleScope = (Bundle.main.bundleIdentifier ?? "desktop")
      .replacingOccurrences(of: ".", with: "-")
    let resetOwnerID = "desktop-harness-reset-\(bundleScope)"
    return await RuntimeOwnerIdentity.withAutomationOwnerIfMissing(resetOwnerID) { [self] in
      let clear = await automationClearOwnerSurfaceState(chatId: "default")
      if let error = clear["error"] {
        return error
      }
      return await automationResetChatForHarness()
    }
  }
}

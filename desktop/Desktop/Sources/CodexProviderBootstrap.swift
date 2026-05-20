import Foundation

/// Starts the Codex loopback proxy when ChatGPT tier is enrolled (cloud desktop mode).
enum CodexProviderBootstrap {

  @MainActor
  static func applyIfNeeded() async {
    guard CodexAuthService.isActive else { return }
    await CodexProxyService.shared.ensureRunning()
  }

  @MainActor
  static func clearDaemonProviders() async {
    await CodexProxyService.shared.stop()
  }
}

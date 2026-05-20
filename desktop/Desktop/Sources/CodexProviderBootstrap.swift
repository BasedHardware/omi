import Foundation

/// Wires ChatGPT/Codex loopback proxy into hybrid daemon provider settings when enrolled.
enum CodexProviderBootstrap {

  static func codexProviderObject(model: String? = nil) -> [String: LocalDaemonSettingUpdateValue] {
    [
      "kind": "openai_compatible",
      "base_url": .string(CodexProxyEndpoints.baseURL),
      "model": .string(model ?? CodexAuthService.preferredModel),
      "api_key": .string(""),
    ]
  }

  /// After successful ChatGPT connect: start proxy and set chat + ai providers (not embeddings).
  @MainActor
  static func applyIfNeeded() async {
    guard CodexAuthService.isActive else { return }
    await CodexProxyService.shared.ensureRunning()
    guard CodexProxyService.shared.isRunning else { return }

    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else {
      return
    }

    do {
      let provider = codexProviderObject()
      let updates: [String: LocalDaemonSettingUpdateValue] = [
        "chat_provider": .object(provider),
        "ai_provider": .object(provider),
      ]
      _ = try await APIClient.shared.updateSelectedBackendSettings(updates)
      log("CodexProviderBootstrap: applied chat_provider + ai_provider → Codex loopback")
    } catch {
      logError("CodexProviderBootstrap: failed to update daemon settings", error: error)
    }
  }

  /// Clear Codex provider keys from daemon (logout).
  @MainActor
  static func clearDaemonProviders() async {
    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else { return }
    do {
      _ = try await APIClient.shared.updateSelectedBackendSettings([
        "chat_provider": .null,
        "ai_provider": .null,
      ])
    } catch {
      logError("CodexProviderBootstrap: failed to clear providers", error: error)
    }
  }
}

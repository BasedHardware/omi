import Foundation

/// Idempotent default hybrid provider keys for local daemon dev (Ollama loopback).
enum HybridProviderBootstrap {

  static func defaultProviderObject() -> [String: LocalDaemonSettingUpdateValue] {
    var object: [String: LocalDaemonSettingUpdateValue] = [
      "kind": "openai_compatible",
      "base_url": .string(HybridProviderReadiness.defaultBaseURL()),
      "model": .string(HybridProviderReadiness.defaultModel()),
    ]
    return object
  }

  /// Writes `ai_provider` and `chat_provider` when absent. Does not overwrite existing keys.
  @MainActor
  static func ensureDefaultsIfNeeded() async {
    guard DesktopBackendEnvironment.selectedBackendTarget.mode == .localDaemon else {
      return
    }

    do {
      let settings = try await APIClient.shared.getSelectedBackendSettings()
      var updates: [String: LocalDaemonSettingUpdateValue] = [:]
      let provider = defaultProviderObject()

      if !HybridProviderReadiness.hasOpenAICompatibleProvider(
        in: settings, keys: ["ai_provider", "provider"])
      {
        updates["ai_provider"] = .object(provider)
      }
      if !HybridProviderReadiness.hasOpenAICompatibleProvider(
        in: settings, keys: ["chat_provider"])
      {
        updates["chat_provider"] = .object(provider)
      }

      guard !updates.isEmpty else { return }

      _ = try await APIClient.shared.updateSelectedBackendSettings(updates)
      log(
        "HybridProviderBootstrap: seeded \(updates.keys.sorted().joined(separator: ", ")) at \(HybridProviderReadiness.defaultBaseURL())"
      )
    } catch {
      logError("HybridProviderBootstrap: failed to seed defaults", error: error)
    }
  }
}

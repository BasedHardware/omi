import Foundation

/// Vision provider configuration for hybrid local-daemon mode (screenshot / multimodal APIs).
enum HybridVisionProvider {
  /// Whether `vision_provider` is set to a supported OpenAI-compatible provider entry.
  static func isConfigured(settings: [LocalDaemonSetting]) -> Bool {
    guard let raw = settings.first(where: { $0.key == "vision_provider" })?.valueJson,
      let data = raw.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return false
    }
    let kind = (json["kind"] as? String) ?? ""
    guard kind == "openai_compatible" || kind == "openai" else {
      return false
    }
    guard let baseURL = json["base_url"] as? String, !baseURL.isEmpty else {
      return false
    }
    return true
  }

  static func providerConfig(from response: HybridProviderPolicy.SlotResolutionResponse?)
    -> HybridLLMClient.ProviderConfig?
  {
    guard let response else {
      return nil
    }
    return HybridProviderPolicy.providerConfig(from: response)
  }

  static func providerConfig(settings: [LocalDaemonSetting]) -> HybridLLMClient.ProviderConfig? {
    providerConfig(
      from: HybridProviderPolicy.resolveSlotFromSettings(
        HybridProviderPolicy.visionSlot,
        settings: settings
      )
    )
  }
}

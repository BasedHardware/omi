import Foundation

enum HybridProviderPolicy {
  static let chatSlot = "chat"
  static let postTranscriptSlot = "post_transcript"
  static let proactiveSlot = "proactive"
  static let visionSlot = "vision"
  static let sttSlot = "stt"
  static let memorySearchSlot = "memory_search"
  static let localProviderAccountID = "local-openai-compatible"
  static let localWikiModel = "local_wiki"

  struct ProviderCapabilities: Codable, Equatable {
    let chatCompletions: Bool
    let jsonMode: Bool
    let toolCalls: Bool
    let vision: Bool
    let speechToText: Bool

    enum CodingKeys: String, CodingKey {
      case chatCompletions = "chat_completions"
      case jsonMode = "json_mode"
      case toolCalls = "tool_calls"
      case vision
      case speechToText = "speech_to_text"
    }
  }

  struct ModelSlotOptions: Codable, Equatable {
    let jsonMode: Bool?
    let toolSupport: Bool?

    enum CodingKeys: String, CodingKey {
      case jsonMode = "json_mode"
      case toolSupport = "tool_support"
    }
  }

  struct ProviderAccount: Codable, Equatable {
    let id: String
    let kind: String
    let baseURL: String?
    let apiKey: String?
    let displayName: String?
    let capabilities: ProviderCapabilities?
    let subscriptionIntegration: String?

    enum CodingKeys: String, CodingKey {
      case id
      case kind
      case baseURL = "base_url"
      case apiKey = "api_key"
      case displayName = "display_name"
      case capabilities
      case subscriptionIntegration = "subscription_integration"
    }
  }

  struct ResolvedSlot: Decodable, Equatable {
    let slot: String
    let providerAccount: ProviderAccount?
    let modelID: String
    let source: String

    enum CodingKeys: String, CodingKey {
      case slot
      case providerAccount = "provider_account"
      case modelID = "model_id"
      case source
    }
  }

  struct SlotResolution: Decodable, Equatable {
    let slot: String
    let ok: Bool
    let resolved: ResolvedSlot?
    let reason: String
  }

  struct SlotResolutionResponse: Decodable, Equatable {
    let resolved: ResolvedSlot?
    let resolution: SlotResolution
  }

  struct Policy: Codable {
    let version: Int
    let providerAccounts: [ProviderAccount]
    let modelSlots: [String: ModelSlotTarget]

    enum CodingKeys: String, CodingKey {
      case version
      case providerAccounts = "provider_accounts"
      case modelSlots = "model_slots"
    }
  }

  struct ModelSlotTarget: Codable {
    let providerAccountID: String?
    let modelID: String
    let options: ModelSlotOptions?

    enum CodingKeys: String, CodingKey {
      case providerAccountID = "provider_account_id"
      case modelID = "model_id"
      case options
    }
  }

  static func providerConfig(from response: SlotResolutionResponse) -> HybridLLMClient
    .ProviderConfig?
  {
    guard response.resolution.ok,
      let resolved = response.resolved,
      let account = resolved.providerAccount,
      let baseURL = account.baseURL?.trimmingCharacters(in: .whitespacesAndNewlines),
      !baseURL.isEmpty,
      isOpenAICompatible(kind: account.kind)
    else {
      return nil
    }
    return HybridLLMClient.ProviderConfig(
      baseURL: baseURL,
      model: resolved.modelID,
      apiKey: account.apiKey ?? ""
    )
  }

  static func chatProviderConfig(from response: SlotResolutionResponse) -> HybridChatClient
    .ProviderConfig?
  {
    guard response.resolution.ok,
      let resolved = response.resolved,
      let account = resolved.providerAccount,
      let baseURL = account.baseURL?.trimmingCharacters(in: .whitespacesAndNewlines),
      !baseURL.isEmpty,
      isOpenAICompatible(kind: account.kind)
    else {
      return nil
    }
    return HybridChatClient.ProviderConfig(
      baseURL: baseURL,
      model: resolved.modelID,
      apiKey: account.apiKey ?? "",
      providerAccountID: account.id,
      providerKind: account.kind,
      slotSource: resolved.source,
      resolutionReason: response.resolution.reason
    )
  }

  static func resolveSlotFromSettings(
    _ slot: String,
    settings: [LocalDaemonSetting]
  ) -> SlotResolutionResponse? {
    guard let raw = settings.first(where: { $0.key == "provider_policy" })?.valueJson,
      let data = raw.data(using: .utf8),
      let policy = try? JSONDecoder().decode(Policy.self, from: data),
      let target = policy.modelSlots[slot]
    else {
      return nil
    }
    let account = target.providerAccountID.flatMap { accountID in
      policy.providerAccounts.first(where: { $0.id == accountID })
    }
    let resolved = ResolvedSlot(
      slot: slot,
      providerAccount: account,
      modelID: target.modelID,
      source: "provider_policy"
    )
    let ok = account != nil || slot == "memory_search"
    let reason =
      ok
      ? "\(slot) resolved to \(target.modelID) from provider_policy"
      : "model slot \(slot) selects \(target.modelID) but no provider account is configured"
    let resolution = SlotResolution(slot: slot, ok: ok, resolved: resolved, reason: reason)
    return SlotResolutionResponse(resolved: resolved, resolution: resolution)
  }

  static func isOpenAICompatible(kind: String) -> Bool {
    let normalized = kind.lowercased()
    return normalized == "openai_compatible" || normalized == "openai"
  }

  static func policyFromSettings(_ settings: [LocalDaemonSetting]) -> Policy? {
    guard let raw = settings.first(where: { $0.key == "provider_policy" })?.valueJson,
      let data = raw.data(using: .utf8)
    else {
      return nil
    }
    return try? JSONDecoder().decode(Policy.self, from: data)
  }
}

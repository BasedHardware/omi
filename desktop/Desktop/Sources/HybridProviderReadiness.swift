import Foundation

/// Checklist rows for hybrid local daemon provider setup (Plan & Usage, About).
enum HybridProviderReadiness {

  enum RowStatus: Equatable {
    case configured
    case optionalFallback
    case missing
    case capabilityOff
  }

  struct Row: Identifiable, Equatable {
    let id: String
    let label: String
    let status: RowStatus
    let detail: String
  }

  static func defaultBaseURL() -> String {
    if let raw = getenv("OMI_HYBRID_DEFAULT_CHAT_BASE_URL"),
      let value = String(validatingUTF8: raw),
      !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    {
      return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return "http://127.0.0.1:11434/v1"
  }

  static func defaultModel() -> String {
    if let raw = getenv("OMI_HYBRID_DEFAULT_CHAT_MODEL"),
      let value = String(validatingUTF8: raw),
      !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    {
      return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    return "llama3.2"
  }

  static func defaultSmallModel() -> String {
    "gpt-5.4-mini"
  }

  static func rows(from settings: [LocalDaemonSetting]) -> [Row] {
    var result: [Row] = []
    let policy = HybridProviderPolicy.policyFromSettings(settings)

    let postResolution = HybridProviderPolicy.resolveSlotFromSettings(
      HybridProviderPolicy.postTranscriptSlot,
      settings: settings
    )
    let postConfigured = hasResolvedOpenAICompatibleSlot(postResolution)
    result.append(
      Row(
        id: HybridProviderPolicy.postTranscriptSlot,
        label: "Post-transcript processing",
        status: postConfigured ? .configured : .optionalFallback,
        detail: postConfigured
          ? slotDetail(postResolution)
          : "Defaults to \(defaultSmallModel()); deterministic fallback when no provider account is configured"
      ))

    let proactiveResolution = HybridProviderPolicy.resolveSlotFromSettings(
      HybridProviderPolicy.proactiveSlot,
      settings: settings
    )
    let proactiveConfigured = hasResolvedOpenAICompatibleSlot(proactiveResolution)
    result.append(
      Row(
        id: HybridProviderPolicy.proactiveSlot,
        label: "Proactive assistants",
        status: proactiveConfigured ? .configured : .missing,
        detail: proactiveConfigured
          ? slotDetail(proactiveResolution)
          : "Defaults to \(defaultSmallModel()); configure a provider account to enable proactive AI calls"
      ))

    let chatResolution = HybridProviderPolicy.resolveSlotFromSettings(
      HybridProviderPolicy.chatSlot,
      settings: settings
    )
    let chatResolvable = chatResolution.flatMap(HybridChatClient.resolveEffectiveChatConfig) != nil
    let chatCap = DesktopBackendEnvironment.isCapability(.directChat, availableIn: .localDaemon)
    result.append(
      Row(
        id: HybridProviderPolicy.chatSlot,
        label: "Chat",
        status: chatResolvable && chatCap
          ? .configured
          : (chatCap ? .missing : .capabilityOff),
        detail: chatResolvable
          ? slotDetail(chatResolution)
          : (chatCap
            ? (chatResolution?.resolution.reason ?? "Configure the chat model slot")
            : (DesktopBackendEnvironment.unavailableReason(for: .directChat, in: .localDaemon)
              ?? "Direct chat disabled"))
      ))

    let visionResolution = HybridProviderPolicy.resolveSlotFromSettings(
      HybridProviderPolicy.visionSlot,
      settings: settings
    )
    let visionConfigured = hasResolvedOpenAICompatibleSlot(visionResolution)
    result.append(
      Row(
        id: HybridProviderPolicy.visionSlot,
        label: "Vision, optional",
        status: visionConfigured ? .configured : .optionalFallback,
        detail: visionConfigured
          ? slotDetail(visionResolution)
          : "Optional; screenshot assistants use local OCR text when no vision slot is configured"
      ))

    let sttAvailable = DesktopBackendEnvironment.isCapability(.directSTT, availableIn: .localDaemon)
    let sttModel = policy?.modelSlots[HybridProviderPolicy.sttSlot]?.modelID
    result.append(
      Row(
        id: HybridProviderPolicy.sttSlot,
        label: "STT/local transcription",
        status: sttAvailable ? .configured : .capabilityOff,
        detail: sttAvailable
          ? "On-device Apple Speech\(sttModel.map { " / \($0)" } ?? ""); no daemon provider key required"
          : (DesktopBackendEnvironment.unavailableReason(for: .directSTT, in: .localDaemon)
            ?? "Direct STT unavailable")
      ))

    result.append(
      Row(
        id: HybridProviderPolicy.memorySearchSlot,
        label: "Memory search",
        status: .configured,
        detail: "Local wiki/FTS search using \(policy?.modelSlots[HybridProviderPolicy.memorySearchSlot]?.modelID ?? HybridProviderPolicy.localWikiModel); no embeddings required"
      ))

    return result
  }

  static func hasOpenAICompatibleProvider(
    in settings: [LocalDaemonSetting],
    keys: [String]
  ) -> Bool {
    guard let raw = settings.first(where: { keys.contains($0.key) })?.valueJson,
      let data = raw.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return false
    }
    let kind = ((json["kind"] as? String) ?? "").lowercased()
    guard kind == "openai_compatible" || kind == "openai" else { return false }
    guard let base = json["base_url"] as? String, !base.isEmpty else { return false }
    return true
  }

  private static func hasResolvedOpenAICompatibleSlot(
    _ response: HybridProviderPolicy.SlotResolutionResponse?
  ) -> Bool {
    guard response?.resolution.ok == true,
      let account = response?.resolved?.providerAccount,
      let baseURL = account.baseURL?.trimmingCharacters(in: .whitespacesAndNewlines),
      !baseURL.isEmpty
    else {
      return false
    }
    return HybridProviderPolicy.isOpenAICompatible(kind: account.kind)
  }

  private static func slotDetail(_ response: HybridProviderPolicy.SlotResolutionResponse?) -> String {
    guard let resolved = response?.resolved else {
      return "Slot not configured"
    }
    let account = resolved.providerAccount?.displayName ?? resolved.providerAccount?.id ?? "no provider account"
    return "\(account) / \(resolved.modelID)"
  }
}

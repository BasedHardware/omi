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

  static func rows(from settings: [LocalDaemonSetting]) -> [Row] {
    var result: [Row] = []

    let aiConfigured = hasOpenAICompatibleProvider(
      in: settings, keys: ["ai_provider", "provider"])
    result.append(
      Row(
        id: "ai_provider",
        label: "Processing (ai_provider)",
        status: aiConfigured ? .configured : .optionalFallback,
        detail: aiConfigured
          ? "OpenAI-compatible provider configured"
          : "Optional — deterministic fallback when unset"
      ))

    let sttAvailable = DesktopBackendEnvironment.isCapability(.directSTT, availableIn: .localDaemon)
    result.append(
      Row(
        id: "stt",
        label: "Live transcription",
        status: sttAvailable ? .configured : .capabilityOff,
        detail: sttAvailable
          ? "On-device Apple Speech (no daemon key)"
          : (DesktopBackendEnvironment.unavailableReason(for: .directSTT, in: .localDaemon)
            ?? "Direct STT unavailable")
      ))

    let chatResolvable = HybridChatClient.resolveEffectiveChatConfig(from: settings) != nil
    let chatCap = DesktopBackendEnvironment.isCapability(.directChat, availableIn: .localDaemon)
    result.append(
      Row(
        id: "chat_provider",
        label: "Chat (chat_provider)",
        status: chatResolvable && chatCap
          ? .configured
          : (chatCap ? .missing : .capabilityOff),
        detail: chatResolvable
          ? "Direct chat endpoint configured"
          : (chatCap
            ? "Set chat_provider or ai_provider in hybrid settings"
            : (DesktopBackendEnvironment.unavailableReason(for: .directChat, in: .localDaemon)
              ?? "Direct chat disabled"))
      ))

    let embedConfigured = HybridEmbeddingClient.loadProviderConfig(from: settings) != nil
    let embedCap = DesktopBackendEnvironment.isCapability(
      .directEmbeddings, availableIn: .localDaemon)
    result.append(
      Row(
        id: "embedding_provider",
        label: "Embeddings (embedding_provider)",
        status: embedConfigured && embedCap
          ? .configured
          : (embedCap ? .missing : .capabilityOff),
        detail: embedConfigured
          ? "Embedding provider configured"
          : (embedCap
            ? "Optional for Rewind semantic search"
            : (DesktopBackendEnvironment.unavailableReason(
              for: .directEmbeddings, in: .localDaemon) ?? "Direct embeddings disabled"))
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
}

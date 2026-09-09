import Foundation

/// Describes an AI provider available for desktop chat.
/// Each provider maps to a `BridgeMode` in ChatProvider and drives
/// the Settings UI (picker label, logo, attribution line).
struct AIProvider: Identifiable {
  let id: String
  /// Human-readable name shown in the picker.
  let displayName: String
  /// Short attribution line shown below the picker.
  let tagline: String
  /// Optional URL for the project (opens in browser on click).
  let attributionURL: URL?
  /// SF Symbol name used as inline logo.
  let sfSymbol: String
  /// Optional bundle resource name for a custom logo PNG.
  /// When non-nil, the resource is loaded from `Bundle.resourceBundle`.
  let logoResource: String?
  /// The raw value stored in UserDefaults `chatBridgeMode`.
  let bridgeModeRawValue: String

  // MARK: - Built-in providers

  static let piMono = AIProvider(
    id: "piMono",
    displayName: "Omi AI",
    tagline: "Built-in AI assistant (built with pi.dev)",
    attributionURL: nil,
    sfSymbol: "",
    logoResource: nil,
    bridgeModeRawValue: "piMono"
  )

  static let claude = AIProvider(
    id: "claude",
    displayName: "Claude",
    tagline: "Your Claude Pro/Max subscription",
    attributionURL: URL(string: "https://claude.ai"),
    sfSymbol: "",
    logoResource: nil,
    bridgeModeRawValue: "claudeCode"
  )

  static let hermes = AIProvider(
    id: "hermes",
    displayName: "Hermes",
    tagline: "Local Hermes Agent via ACP",
    attributionURL: nil,
    sfSymbol: "",
    logoResource: "hermes_logo",
    bridgeModeRawValue: "hermes"
  )

  static let openClaw = AIProvider(
    id: "openclaw",
    displayName: "OpenClaw",
    tagline: "Local OpenClaw agent",
    attributionURL: nil,
    sfSymbol: "",
    logoResource: "openclaw_logo",
    bridgeModeRawValue: "openclaw"
  )

  static let local = AIProvider(
    id: "local",
    displayName: "Local",
    tagline: "Your own local model — never leaves your network",
    attributionURL: nil,
    sfSymbol: "",
    logoResource: nil,
    bridgeModeRawValue: "local"
  )

  static let all: [AIProvider] = [.piMono, .claude, .hermes, .openClaw, .local]

  /// Look up a provider by its `chatBridgeMode` raw value.
  static func from(bridgeMode: String) -> AIProvider? {
    all.first { $0.bridgeModeRawValue == bridgeMode }
  }

  // MARK: - Local provider settings (UserDefaults-backed, user-editable in Settings)

  /// UserDefaults key for the local provider's OpenAI-compatible base URL.
  static let localBaseURLKey = "localLLMBaseURL"
  /// UserDefaults key for the local provider's model id.
  static let localModelIDKey = "localLLMModelID"
  /// UserDefaults key for an optional vision-capable local model id, used as
  /// a subagent the main local model can delegate screenshot interpretation
  /// to. No default — empty/unset means the feature is off and behavior is
  /// identical to a single local model handling everything itself.
  static let localVisionModelIDKey = "localLLMVisionModelID"
  /// UserDefaults key for an optional self-hosted backend URL, used in place
  /// of api.omi.me for voice transcription and memory/conversation sync when
  /// the local provider is active. No default — empty/unset means "use the
  /// normal cloud/dev resolution", same opt-in framing as the two keys above.
  static let localBackendURLKey = "localBackendURL"

  /// UserDefaults key for whether background connector synthesis (Apple
  /// Notes, Calendar, and Gmail memory synthesis, plus AI-profile synthesis)
  /// is allowed to call Omi's cloud synthesis endpoint while the Local
  /// provider is active. Only meaningful under Local — every other provider
  /// already synthesizes server-side regardless of this setting.
  static let connectorSynthesisModeKey = "localConnectorSynthesisMode"

  /// Values for `connectorSynthesisModeKey`.
  enum ConnectorSynthesisMode: String {
    /// Default: Notes/Calendar/Gmail memory synthesis and AI-profile
    /// synthesis do not run while Local is active — no formatted note,
    /// event, or email text leaves the machine.
    case off
    /// Opt-in: the same formatted text sent under any other provider is
    /// sent to Omi's servers and processed by a cloud model.
    case cloud
  }

  /// The persisted connector-synthesis choice, defaulting to `.off`.
  static var connectorSynthesisMode: ConnectorSynthesisMode {
    let raw =
      UserDefaults.standard.string(forKey: connectorSynthesisModeKey) ?? ConnectorSynthesisMode.off.rawValue
    return ConnectorSynthesisMode(rawValue: raw) ?? .off
  }

  /// Whether a connector-synthesis call site (Apple Notes, Calendar, Gmail
  /// memory synthesis, or AI-profile synthesis) should skip its network call
  /// entirely. True only when the Local provider is active *and* the user
  /// has not opted into sending that data to Omi's cloud; every other
  /// provider is unaffected.
  static func shouldSkipConnectorSynthesis() -> Bool {
    resolveBridgeMode() == .local && connectorSynthesisMode == .off
  }

  /// Default local endpoint — localhost, matching LM Studio's default port.
  /// Only used as the initial value of an editable Settings field, never
  /// hardcoded into a request path.
  static let defaultLocalBaseURL = "http://localhost:1234/v1"
  /// No default model id: every LM Studio (or other OpenAI-compatible)
  /// server serves a different set of models, so a hardcoded id here would
  /// be a real value on only one machine and a broken one everywhere else.
  /// Empty means "not yet configured"; Settings picks the first id the
  /// server reports at `{baseURL}/models` once the fetch succeeds, and
  /// AgentBridge already refuses to start the local provider while this is
  /// empty rather than silently sending a model id that doesn't exist.
  static let defaultLocalModelID = ""

  /// UserDefaults key for which provider is selected. Mirrors
  /// `ChatProvider.BridgeMode`'s raw-value space (not referenced directly
  /// here to avoid a dependency in the other direction).
  static let selectedProviderRawValueKey = "chatBridgeMode"

  /// The pi provider name ("omi" or "omi-local") the currently-selected AI
  /// provider maps to, read straight from the persisted Settings selection.
  /// This is the single source of truth `AgentRuntimeProcess` consults when
  /// launching the harness process and `AgentBridge`/`ChatRunAccountingPolicy`
  /// consult for quota/billing gating — there is no per-session override.
  static var currentProviderMode: String {
    let raw = UserDefaults.standard.string(forKey: selectedProviderRawValueKey) ?? AIProvider.piMono.bridgeModeRawValue
    return raw == AIProvider.local.bridgeModeRawValue ? "omi-local" : "omi"
  }

  /// Resolves the persisted `chatBridgeMode` UserDefaults value into a
  /// `ChatProvider.BridgeMode`, defaulting to `.piMono` the same way every
  /// call site that reads this key already does. Single source of truth for
  /// what was previously a 3-4 line lookup duplicated across ChatProvider,
  /// TaskChatState, and (as of this fix) every background synthesis caller.
  static func resolveBridgeMode() -> ChatProvider.BridgeMode {
    let modeRaw = UserDefaults.standard.string(forKey: selectedProviderRawValueKey)
      ?? ChatProvider.BridgeMode.piMono.rawValue
    return ChatProvider.BridgeMode(rawValue: modeRaw) ?? .piMono
  }

  /// Resolves the model id to use for an LLM call, given what it would use
  /// on a cloud provider. On the local provider this must be the user's
  /// configured local model — passing a Claude id forces the pi-mono
  /// extension to also register the cloud "omi" provider, which then fails
  /// without an Anthropic key.
  static func resolveModel(cloudDefault: String) -> String {
    guard resolveBridgeMode() == .local else { return cloudDefault }
    return UserDefaults.standard.string(forKey: localModelIDKey) ?? defaultLocalModelID
  }

  /// Resolves the model id for one-off quick-chat calls (floating bar, task
  /// agent pills, memory export) that pick a model from ShortcutSettings
  /// without going through ChatProvider's own bridge.
  @MainActor
  static func resolveQuickChatModel() -> String {
    let cloudDefault = ShortcutSettings.shared.selectedModel.isEmpty
      ? ModelQoS.Claude.defaultSelection
      : ShortcutSettings.shared.selectedModel
    return resolveModel(cloudDefault: cloudDefault)
  }

  /// Decodes the standard OpenAI-compatible `GET /models` response shape.
  struct LocalModelsResponse: Decodable {
    struct Model: Decodable { let id: String }
    let data: [Model]
  }

  /// Fetches the list of model ids an OpenAI-compatible local server (LM
  /// Studio, Ollama, etc.) currently reports at `{baseURL}/models`.
  ///
  /// This is the only reliable source of truth for what's actually being
  /// served — a name saved from a previous session (or copy-pasted from
  /// somewhere else) is not proof a model still exists or is loaded.
  /// Throws on any network, HTTP, or decode failure; callers should fall
  /// back to manual text entry rather than block on this.
  static func fetchLocalModels(baseURL: String) async throws -> [String] {
    let normalized = baseURL.hasSuffix("/") ? String(baseURL.dropLast()) : baseURL
    guard let url = URL(string: "\(normalized)/models") else {
      throw URLError(.badURL)
    }
    var request = URLRequest(url: url)
    request.timeoutInterval = 5
    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
      throw URLError(.badServerResponse)
    }
    let decoded = try JSONDecoder().decode(LocalModelsResponse.self, from: data)
    return decoded.data.map(\.id).sorted()
  }
}

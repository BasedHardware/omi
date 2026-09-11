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
    tagline: "Your own local model, never leaves your network",
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
  /// to. No default: empty/unset means the feature is off and behavior is
  /// identical to a single local model handling everything itself.
  static let localVisionModelIDKey = "localLLMVisionModelID"
  /// UserDefaults key for an optional self-hosted backend URL, used in place
  /// of api.omi.me for voice transcription and memory/conversation sync when
  /// the local provider is active. No default: empty/unset means "use the
  /// normal cloud/dev resolution", same opt-in framing as the two keys above.
  static let localBackendURLKey = "localBackendURL"

  /// UserDefaults key for the Local provider's "Context per turn" setting:
  /// how much of the kernel context snapshot the runtime sends on the first
  /// turn of a chat. Only meaningful under Local: every other provider
  /// always sends the full (100%) context.
  static let contextBudgetPercentKey = "localContextBudgetPercent"

  /// Values for `contextBudgetPercentKey`. The raw value is the percentage
  /// the kernel scales retained journal turns and per-source payload caps
  /// by; 100 is byte-identical to today's behavior. Follow-up turns already
  /// send only what changed, so this only shortens the first turn of a chat.
  enum ContextBudgetPercent: Int, CaseIterable {
    case quarter = 25
    case half = 50
    case threeQuarters = 75
    case full = 100

    var displayName: String {
      switch self {
      case .quarter: return "25%"
      case .half: return "50%"
      case .threeQuarters: return "75%"
      case .full: return "100% (default)"
      }
    }
  }

  /// The persisted context-budget choice, defaulting to `.full` and falling
  /// back to `.full` for any malformed stored value (missing, non-integer,
  /// or an int that isn't one of the four cases) without ever persisting
  /// that fallback.
  static var localContextBudgetPercent: ContextBudgetPercent {
    ContextBudgetPercent(rawValue: UserDefaults.standard.integer(forKey: contextBudgetPercentKey)) ?? .full
  }

  /// Pre-unification key: connector synthesis (Apple Notes/Calendar/Gmail +
  /// AI-profile) used to have its own standalone on/off toggle before it was
  /// folded into `cloudAssistModeKey` below. Read once, by
  /// `localCloudAssistMode`, to migrate an existing explicit choice forward;
  /// never written to again after that.
  static let connectorSynthesisModeKey = "localConnectorSynthesisMode"

  /// UserDefaults key for the single Local-provider "Cloud-assisted
  /// features" setting: whether connector synthesis (Notes/Calendar/Gmail/
  /// AI-profile), proactive assistants and live notes (memory, task,
  /// suggestion, insight extraction from screen and transcripts), dictation
  /// polish, Rewind semantic-search embeddings, and web search are allowed to
  /// send content to Omi's servers and cloud models while the Local provider
  /// is active. Only meaningful under Local: every other provider already
  /// sends this content server-side regardless of this setting.
  static let cloudAssistModeKey = "localCloudAssistMode"

  /// Values for `cloudAssistModeKey`.
  enum CloudAssistMode: String {
    /// Default: none of the covered features run while Local is active, no
    /// screenshot, transcript, note/event/email text, or search query leaves
    /// the machine for any of them.
    case off
    /// Opt-in: the same content sent under any other provider is sent to
    /// Omi's servers and processed by a cloud model, metered like a cloud
    /// user for each feature it touches.
    case cloud
  }

  /// The persisted cloud-assist choice, defaulting to `.off`. Migrates the
  /// pre-unification `connectorSynthesisModeKey` forward exactly once: if the
  /// new key has never been set but the old one was, the old value becomes
  /// the new key's value (an existing explicit Off stays Off, an existing
  /// Cloud opt-in carries forward too) so a user's prior choice is never
  /// silently reset by this rename.
  static var localCloudAssistMode: CloudAssistMode {
    let defaults = UserDefaults.standard
    if let raw = defaults.string(forKey: cloudAssistModeKey) {
      return CloudAssistMode(rawValue: raw) ?? .off
    }
    if let legacyRaw = defaults.string(forKey: connectorSynthesisModeKey),
      let migrated = CloudAssistMode(rawValue: legacyRaw)
    {
      defaults.set(migrated.rawValue, forKey: cloudAssistModeKey)
      return migrated
    }
    return .off
  }

  /// True only when the Local provider is active *and* the user has opted
  /// cloud-assisted features on. Every feature listed on `cloudAssistModeKey`
  /// gates its own network call on this: false under every other provider
  /// (they already send this content server-side unconditionally) and false
  /// under Local until the explicit opt-in.
  static var localCloudAssistEnabled: Bool {
    isLocalProviderActive && localCloudAssistMode == .cloud
  }

  /// True when the Local provider is active *and* the user has not opted
  /// cloud-assisted features on: the fail-closed condition every gated
  /// network call site checks before it may send content off the machine.
  /// Named so the seven call sites that used to spell out
  /// `isLocalProviderActive && !localCloudAssistEnabled` (GeminiClient,
  /// ProactiveLaneClient, EmbeddingService's embed/embedBatch,
  /// ChatToolExecutor's web_search, and AppState+TrialPaywall's screen-capture
  /// exemption/popup gate) share one definition, so a future change to the
  /// condition lands in one place instead of seven.
  static var isLocalProviderFailingClosed: Bool {
    isLocalProviderActive && !localCloudAssistEnabled
  }

  /// Whether a connector-synthesis call site (Apple Notes, Calendar, Gmail
  /// memory synthesis, or AI-profile synthesis) should skip its network call
  /// entirely. True only when the Local provider is active *and* the user
  /// has not opted into cloud-assisted features; every other provider is
  /// unaffected. Thin wrapper over `localCloudAssistEnabled` kept so its four
  /// call sites (AppleNotesReaderService, CalendarReaderService,
  /// GmailReaderService, AIUserProfileService) read naturally at the call site.
  static func shouldSkipConnectorSynthesis() -> Bool {
    isLocalProviderActive && !localCloudAssistEnabled
  }

  /// Default local endpoint: localhost, matching LM Studio's default port.
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
  /// consult for quota/billing gating: there is no per-session override.
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
    let modeRaw =
      UserDefaults.standard.string(forKey: selectedProviderRawValueKey)
      ?? ChatProvider.BridgeMode.piMono.rawValue
    return ChatProvider.BridgeMode(rawValue: modeRaw) ?? .piMono
  }

  /// True when the Local provider is the active chat/agent provider: every
  /// text call already routes to the user's own server (see
  /// `currentProviderMode`), and since the vision-subagent delegation,
  /// screenshot interpretation does too. Free-tier gates that only exist to
  /// meter Omi's cloud model should key off this, combined with the
  /// individual feature's own "does this still call Omi's cloud" check
  /// (e.g. connector synthesis, which stays gated unless the user opts into
  /// `localCloudAssistMode == .cloud`, see `localCloudAssistEnabled`).
  static var isLocalProviderActive: Bool {
    resolveBridgeMode() == .local
  }

  /// The value to pass the runtime as `OMI_CONTEXT_BUDGET_PERCENT`, or nil
  /// when the env var should simply be absent: every provider other than
  /// Local, and Local at the 100% default (byte-identical to today, so
  /// there is nothing to signal). Changing this needs a runtime restart:
  /// the value is baked into the runtime environment at spawn, see
  /// AgentRuntimeProcess.
  static var contextBudgetPercentForRuntime: Int? {
    guard isLocalProviderActive, localContextBudgetPercent != .full else { return nil }
    return localContextBudgetPercent.rawValue
  }

  /// A local model's time to first token is dominated by prompt prefill on
  /// the user's own hardware (measured 20 to 60s on 2026-09-10, longer as
  /// the conversation grows), so the voice domain's 20s provider-response
  /// deadline, sized for a cloud round trip, declares the turn dead while
  /// the reply is still coming. 180s matches the existing `chatLaneTool`
  /// budget.
  static let localVoiceProviderResponseDeadline: TimeInterval = 180

  /// Maps the active provider to the voice provider-response deadline
  /// override: `localVoiceProviderResponseDeadline` under Local, nil (keep
  /// the reducer's 20s default) under every other provider. Pure function
  /// over `isLocalProviderActive` so it is testable without a live
  /// `VoiceTurnCoordinator`.
  static var voiceProviderResponseDeadline: TimeInterval? {
    isLocalProviderActive ? localVoiceProviderResponseDeadline : nil
  }

  /// True when the Local provider is active AND a self-hosted backend URL
  /// (`localBackendURLKey`, Settings' "Local Backend URL") is configured:
  /// the point at which voice transcription and memory/conversation sync
  /// also leave Omi's cloud proxy path (see `DesktopBackendEnvironment`).
  /// Narrower than `isLocalProviderActive`: a user who only pointed chat at
  /// Local still sends audio to Omi's Deepgram proxy until this is also true.
  /// The owner runs Local with this deliberately unset (no self-hosted
  /// backend), which must stay a first-class, fully-supported configuration:
  /// chat/PTT/screen-capture exemptions key off `isLocalProviderActive`
  /// alone, and only transcription needs this narrower check.
  static var isLocalProviderWithSelfHostedBackend: Bool {
    isLocalProviderActive && !(UserDefaults.standard.string(forKey: localBackendURLKey) ?? "").isEmpty
  }

  /// Resolves the model id to use for an LLM call, given what it would use
  /// on a cloud provider. On the local provider this must be the user's
  /// configured local model: passing a Claude id forces the pi-mono
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
    let cloudDefault =
      ShortcutSettings.shared.selectedModel.isEmpty
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
  /// served: a name saved from a previous session (or copy-pasted from
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

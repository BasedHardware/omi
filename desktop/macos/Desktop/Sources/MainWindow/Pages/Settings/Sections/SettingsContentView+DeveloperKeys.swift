import OmiTheme
import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit

/// Users often paste one key and miss the banner saying all four are required
/// at the same time. Non-nil while 1–3 keys (in `BYOKProvider.allCases` order)
/// are entered, listing the ones still missing.
func byokMissingKeysHint(_ keys: [String]) -> String? {
  let missing = zip(BYOKProvider.allCases, keys).filter { $0.1.isEmpty }.map(\.0.displayName)
  guard !missing.isEmpty, missing.count < keys.count else { return nil }
  return
    "Still missing: \(missing.joined(separator: ", ")). All 4 keys must be entered at the same time to activate the free plan."
}

/// What a settled BYOK key set owes the backend.
///
/// The four fields are `SecureField`s bound straight to `@AppStorage`, so the
/// binding is written on *every character*. Reconciling on each of those writes
/// pinged four provider auth endpoints with a half-typed key and flapped the
/// backend free-plan flag once per keystroke. Deciding the action from the
/// settled key set — separately from performing it — is what makes that policy
/// testable without a network.
enum BYOKReconciliation {
  enum Action: Equatable {
    /// Every key is present: prove them against the providers, then flip the
    /// free plan on (or back off if a provider rejects one).
    case validateAndActivate
    /// The free plan cannot be active with a partial key set.
    case deactivate
    /// Nothing was ever entered and nothing was ever reconciled — opening the
    /// pane is not a reason to touch the network.
    case none
  }

  static func action(
    forKeys keys: [String],
    hasCheckedStatuses: Bool,
    hasActivationError: Bool
  ) -> Action {
    let entered = keys.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    if entered.count == keys.count, !keys.isEmpty { return .validateAndActivate }
    if entered.isEmpty, !hasCheckedStatuses, !hasActivationError { return .none }
    return .deactivate
  }
}

extension SettingsContentView {
  var developerKeysSubsection: some View {
    VStack(spacing: OmiSpacing.xl) {
      byokStatusBanner

      settingsCard(settingId: "advanced.devkeys.llm") {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          Text("Language model")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
          Text("Choose the provider that powers chat, memory, and insights. OpenRouter is selected by default.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
          Picker("LLM provider", selection: $devBYOKLLMProvider) {
            ForEach(BYOKLLMProvider.allCases) { provider in
              Text(provider.displayName).tag(provider.rawValue)
            }
          }
          .pickerStyle(.menu)
        }
      }

      if let provider = selectedBYOKLLMProvider.provider, let key = selectedBYOKLLMKey {
        developerKeyField(
          provider: provider,
          title: "\(selectedBYOKLLMProvider.displayName) API Key",
          subtitle: selectedBYOKLLMSubtitle,
          settingId: "advanced.devkeys.llm-key",
          value: key
        )
      } else if let provider = selectedBYOKLLMProvider.oauthProvider {
        llmOAuthCard(provider)
      }

      developerKeyField(
        provider: .deepgram,
        title: "Deepgram API Key",
        subtitle: "For live transcription.",
        settingId: "advanced.devkeys.deepgram",
        value: $devDeepgramKey
      )

      if let byokActivationError {
        byokWarningCard(byokActivationError, settingId: "advanced.devkeys.error")
      }

      if hasAnyBYOKKey {
        settingsCard(settingId: "advanced.devkeys.clear") {
          HStack {
            Spacer()
            Button(action: clearAllBYOKKeys) {
              Text("Clear All Custom Keys")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(Ink.errorRed)
            }
            .buttonStyle(.plain)
            Spacer()
          }
        }
      }
    }
    // One reconcile per settled key set, not one per keystroke. `.task(id:)`
    // cancels the superseded run, so a key typed by hand reaches the providers
    // once — and opening the pane with four saved keys finally fills in the
    // per-provider badges instead of leaving them blank until the next edit.
    .task(id: byokKeySetFingerprint) {
      migrateLegacyBYOKSelection()
      await refreshBYOKActivation()
    }
    .task {
      await refreshLLMOAuthStatus()
    }
  }

  /// Identity of the current key set for `.task(id:)` — a SHA-256 over the four
  /// values, never the values themselves, so the view can compare key sets
  /// without a secret sitting in a view-diff identity.
  var byokKeySetFingerprint: String {
    APIKeyService.byokFingerprint(
      [devBYOKLLMProvider, selectedBYOKLLMKey?.wrappedValue ?? "", devDeepgramKey].joined(separator: "\u{1}"))
  }

  var selectedBYOKLLMProvider: BYOKLLMProvider {
    BYOKLLMProvider(rawValue: devBYOKLLMProvider)
      ?? APIKeyService.selectedBYOKLLMProvider.flatMap { BYOKLLMProvider(rawValue: $0.rawValue) }
      ?? .openrouter
  }

  func migrateLegacyBYOKSelection() {
    guard BYOKLLMProvider(rawValue: devBYOKLLMProvider) == nil else { return }
    devBYOKLLMProvider = selectedBYOKLLMProvider.rawValue
  }

  var selectedBYOKLLMKey: Binding<String>? {
    switch selectedBYOKLLMProvider {
    case .openrouter: return $devOpenRouterKey
    case .openai: return $devOpenAIKey
    case .gemini: return $devGeminiKey
    case .anthropic: return $devAnthropicKey
    case .chatgpt, .grok: return nil
    }
  }

  var selectedBYOKLLMSubtitle: String {
    switch selectedBYOKLLMProvider {
    case .openrouter: return "Routes supported models through your OpenRouter account."
    case .openai: return "Uses your OpenAI API key directly."
    case .gemini: return "Uses Gemini 2.5 Flash Lite directly."
    case .anthropic: return "Uses your Anthropic API key directly."
    case .chatgpt: return "Uses your ChatGPT plan through OAuth."
    case .grok: return "Uses your Grok account through OAuth."
    }
  }

  func llmOAuthCard(_ provider: LLMOAuthProvider) -> some View {
    settingsCard(settingId: "advanced.devkeys.\(provider.rawValue)-oauth") {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack {
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("\(selectedBYOKLLMProvider.displayName) account")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)
            Text(selectedBYOKLLMSubtitle)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
          Spacer()
          if isLLMOAuthConnected(provider) {
            Text("Connected")
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(Ink.listeningGreen)
          }
        }
        if let llmOAuthError {
          Text(llmOAuthError)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(SettingsInk.notice)
        }
        HStack {
          Button(isLLMOAuthConnected(provider) ? "Disconnect" : "Connect \(selectedBYOKLLMProvider.displayName)") {
            Task { await toggleLLMOAuth(provider) }
          }
          .buttonStyle(.bordered)
          .disabled(isConnectingLLMOAuth)
          if isConnectingLLMOAuth {
            ProgressView().controlSize(.small)
          }
        }
      }
    }
  }

  func isLLMOAuthConnected(_ provider: LLMOAuthProvider) -> Bool {
    switch provider {
    case .chatgpt: return chatGPTLLMOAuthConnected
    case .grok: return grokLLMOAuthConnected
    }
  }

  func setLLMOAuthConnected(_ connected: Bool, provider: LLMOAuthProvider) {
    switch provider {
    case .chatgpt: chatGPTLLMOAuthConnected = connected
    case .grok: grokLLMOAuthConnected = connected
    }
  }

  @MainActor
  func refreshLLMOAuthStatus() async {
    do {
      let status = try await APIClient.shared.llmOAuthStatus()
      for provider in LLMOAuthProvider.allCases {
        setLLMOAuthConnected(status.connected.contains(provider), provider: provider)
      }
    } catch {
      return
    }
  }

  @MainActor
  func toggleLLMOAuth(_ provider: LLMOAuthProvider) async {
    isConnectingLLMOAuth = true
    llmOAuthError = nil
    defer { isConnectingLLMOAuth = false }
    do {
      if isLLMOAuthConnected(provider) {
        try await APIClient.shared.disconnectLLMOAuth(provider)
        setLLMOAuthConnected(false, provider: provider)
      } else {
        try await LLMOAuthConnector.shared.connect(provider)
        setLLMOAuthConnected(true, provider: provider)
      }
      await FloatingBarUsageLimiter.shared.fetchPlan()
      loadSubscriptionInfo()
    } catch {
      llmOAuthError = error.localizedDescription
    }
  }

  func byokWarningCard(_ text: String, settingId: String) -> some View {
    settingsCard(settingId: settingId) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "exclamationmark.triangle.fill")
          .foregroundColor(SettingsInk.notice)
        Text(text)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(SettingsInk.notice)
      }
    }
  }

  var hasAnyBYOKKey: Bool {
    !devOpenRouterKey.isEmpty || !devOpenAIKey.isEmpty || !devAnthropicKey.isEmpty || !devGeminiKey.isEmpty
      || !devDeepgramKey.isEmpty || chatGPTLLMOAuthConnected || grokLLMOAuthConnected
  }

  var hasAllBYOKKeys: Bool {
    APIKeyService.isByokActive
  }

  @ViewBuilder
  var byokStatusBanner: some View {
    settingsCard(settingId: "advanced.devkeys.info") {
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        Image(systemName: hasAllBYOKKeys ? "checkmark.seal.fill" : "key.fill")
          .foregroundColor(hasAllBYOKKeys ? Ink.listeningGreen : Ink.secondary)
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(hasAllBYOKKeys ? "Free plan active" : "Use Omi free forever")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.primary)
          Text(
            hasAllBYOKKeys
              ? "You're paying your own providers. Omi skips the subscription charge. Keys stay on this Mac."
              : "Choose a language model provider, then add its key. Deepgram is optional and only powers transcription. Keys stay on this Mac — we never store them on our servers."
          )
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        }
        Spacer()
      }
    }
  }

  func clearAllBYOKKeys() {
    devOpenAIKey = ""
    devOpenRouterKey = ""
    devAnthropicKey = ""
    devGeminiKey = ""
    devDeepgramKey = ""
    byokKeyStatuses = [:]
    byokActivationError = nil
    chatGPTLLMOAuthConnected = false
    grokLLMOAuthConnected = false
    // Clearing the fields is an explicit "take me off the free plan", so say so
    // now rather than leaving it to the debounced reconcile. Cleared within the
    // debounce window the reconcile sees an untouched-looking form and — quite
    // correctly — decides there is nothing to do, which would have left the
    // backend believing BYOK was still active with no keys behind it. Both
    // paths only ever deactivate, so the duplicate call is harmless.
    Task {
      for provider in LLMOAuthProvider.allCases {
        try? await APIClient.shared.disconnectLLMOAuth(provider)
      }
      try? await APIClient.shared.deactivateBYOK()
      await FloatingBarUsageLimiter.shared.fetchPlan()
    }
  }

  /// Debounce before a settled key set is spent on the network. Long enough to
  /// swallow hand-typing, short enough that a paste feels immediate.
  static let byokReconcileDebounce: Duration = .milliseconds(600)

  @MainActor
  func refreshBYOKActivation() async {
    guard let selectedKey = selectedBYOKLLMKey else {
      return
    }
    guard !selectedKey.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      byokKeyStatuses = [:]
      byokActivationError = nil
      if !chatGPTLLMOAuthConnected && !grokLLMOAuthConnected && hasAnyBYOKKey {
        try? await APIClient.shared.deactivateBYOK()
        await FloatingBarUsageLimiter.shared.fetchPlan()
      }
      return
    }
    let action = BYOKReconciliation.action(
      forKeys: [selectedKey.wrappedValue],
      hasCheckedStatuses: !byokKeyStatuses.isEmpty,
      hasActivationError: byokActivationError != nil
    )
    guard action != .none else { return }

    do {
      try await Task.sleep(for: Self.byokReconcileDebounce)
    } catch {
      return  // superseded by a newer key set
    }

    switch action {
    case .none:
      return

    case .validateAndActivate:
      // The badge state the UI has always been able to draw but never reached:
      // say a provider is being checked while it is being checked.
      var checking: [BYOKProvider: BYOKValidator.Status] = [:]
      for provider in APIKeyService.activeBYOKSnapshot.keys { checking[provider] = .checking }
      byokKeyStatuses = checking

      // Validate before flipping the backend flag — otherwise we'd put the
      // user on the free plan with dead keys and every chat would 401.
      let snapshot = APIKeyService.activeBYOKSnapshot.reduce(into: [BYOKProvider: String]()) {
        acc, entry in acc[entry.key] = entry.value.key
      }
      let results = await BYOKValidator.validateAll(snapshot)
      guard !Task.isCancelled else { return }
      let selectedLLMValid =
        selectedBYOKLLMProvider.provider.flatMap { results[$0] }.map {
          if case .ok = $0 { return true }
          return false
        } ?? false
      if selectedLLMValid {
        let fingerprints = APIKeyService.activeBYOKSnapshot.reduce(into: [String: String]()) { acc, entry in
          if let status = results[entry.key], case .ok = status {
            acc[entry.key.rawValue] = entry.value.fingerprint
          }
        }
        try? await APIClient.shared.activateBYOK(fingerprints: fingerprints)
        await FloatingBarUsageLimiter.shared.fetchPlan()
        await MainActor.run {
          // Clear any sticky paywall flag from a prior `freemium_threshold_reached`
          // event — once all 4 BYOK keys validate, the user is on the free BYOK
          // plan and shouldn't be locked out of capture/transcription anymore.
          AppState.current?.isPaywalled = false
          byokKeyStatuses = results
          byokActivationError = nil
        }
      } else {
        let failed = results.filter {
          if case .ok = $0.value { return false }
          return true
        }
        let names = failed.keys.map(\.displayName).sorted().joined(separator: ", ")
        try? await APIClient.shared.deactivateBYOK()
        await FloatingBarUsageLimiter.shared.fetchPlan()
        await MainActor.run {
          byokKeyStatuses = results
          byokActivationError =
            "Rejected by provider: \(names). Free plan stays off until the selected language model authenticates."
        }
      }

    case .deactivate:
      try? await APIClient.shared.deactivateBYOK()
      await FloatingBarUsageLimiter.shared.fetchPlan()
      await MainActor.run {
        byokKeyStatuses = [:]
        byokActivationError = nil
      }
    }

    await MainActor.run { loadSubscriptionInfo() }
  }

  func developerKeyField(
    provider: BYOKProvider? = nil,
    title: String, subtitle: String, settingId: String, value: Binding<String>
  ) -> some View {
    settingsCard(settingId: settingId) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack {
          Text(title)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
          Spacer()
          if let provider, let status = byokKeyStatuses[provider] {
            byokStatusBadge(status)
          }
        }
        Text(subtitle)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        SecureField("Leave blank for default", text: value)
          .textFieldStyle(.roundedBorder)
          .scaledFont(size: OmiType.body)
        if let provider, case .failed(let msg) = byokKeyStatuses[provider] ?? .notChecked {
          Text(msg)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(SettingsInk.notice)
        }
      }
    }
  }

  @ViewBuilder
  func byokStatusBadge(_ status: BYOKValidator.Status) -> some View {
    switch status {
    case .notChecked:
      EmptyView()
    case .checking:
      HStack(spacing: OmiSpacing.xxs) {
        ProgressView().controlSize(.mini)
        Text("Checking…").scaledFont(size: OmiType.caption).foregroundColor(Ink.secondary)
      }
    case .ok:
      Text("Valid").scaledFont(size: OmiType.caption, weight: .semibold).foregroundColor(Ink.listeningGreen)
    case .failed:
      Text("Invalid").scaledFont(size: OmiType.caption, weight: .semibold).foregroundColor(SettingsInk.notice)
    }
  }

}

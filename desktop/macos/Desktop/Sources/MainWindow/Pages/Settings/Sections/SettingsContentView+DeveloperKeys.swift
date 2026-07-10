import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var developerKeysSubsection: some View {
    VStack(spacing: 20) {
      byokStatusBanner

      developerKeyField(
        provider: .openai,
        title: "OpenAI API Key",
        subtitle: "For GPT calls.",
        settingId: "advanced.devkeys.openai",
        value: $devOpenAIKey
      )

      developerKeyField(
        provider: .anthropic,
        title: "Anthropic API Key",
        subtitle: "For chat (Claude).",
        settingId: "advanced.devkeys.anthropic",
        value: $devAnthropicKey
      )

      developerKeyField(
        provider: .gemini,
        title: "Gemini API Key",
        subtitle: "For proactive AI (memory, tasks, insights, focus).",
        settingId: "advanced.devkeys.gemini",
        value: $devGeminiKey
      )

      developerKeyField(
        provider: .deepgram,
        title: "Deepgram API Key",
        subtitle: "For live transcription.",
        settingId: "advanced.devkeys.deepgram",
        value: $devDeepgramKey
      )

      if let byokActivationError {
        settingsCard(settingId: "advanced.devkeys.error") {
          HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
              .foregroundColor(OmiColors.warning)
            Text(byokActivationError)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.warning)
          }
        }
      }

      if hasAnyBYOKKey {
        settingsCard(settingId: "advanced.devkeys.clear") {
          HStack {
            Spacer()
            Button(action: clearAllBYOKKeys) {
              Text("Clear All Custom Keys")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(.red)
            }
            .buttonStyle(.plain)
            Spacer()
          }
        }
      }
    }
    .onChange(of: devOpenAIKey) { _, _ in refreshBYOKActivation() }
    .onChange(of: devAnthropicKey) { _, _ in refreshBYOKActivation() }
    .onChange(of: devGeminiKey) { _, _ in refreshBYOKActivation() }
    .onChange(of: devDeepgramKey) { _, _ in refreshBYOKActivation() }
  }

  var hasAnyBYOKKey: Bool {
    !devOpenAIKey.isEmpty || !devAnthropicKey.isEmpty || !devGeminiKey.isEmpty
      || !devDeepgramKey.isEmpty
  }

  var hasAllBYOKKeys: Bool {
    !devOpenAIKey.isEmpty && !devAnthropicKey.isEmpty && !devGeminiKey.isEmpty
      && !devDeepgramKey.isEmpty
  }

  @ViewBuilder
  var byokStatusBanner: some View {
    settingsCard(settingId: "advanced.devkeys.info") {
      HStack(alignment: .top, spacing: 12) {
        Image(systemName: hasAllBYOKKeys ? "checkmark.seal.fill" : "key.fill")
          .foregroundColor(hasAllBYOKKeys ? OmiColors.success : OmiColors.textTertiary)
        VStack(alignment: .leading, spacing: 4) {
          Text(hasAllBYOKKeys ? "Free plan active" : "Use Omi free forever")
            .scaledFont(size: 14, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(
            hasAllBYOKKeys
              ? "You're paying your own providers. Omi skips the subscription charge. Keys stay on this Mac."
              : "Provide all four keys (OpenAI, Anthropic, Gemini, Deepgram) to switch to the free plan. Keys stay on this Mac — we never store them on our servers."
          )
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
        }
        Spacer()
      }
    }
  }

  func clearAllBYOKKeys() {
    devOpenAIKey = ""
    devAnthropicKey = ""
    devGeminiKey = ""
    devDeepgramKey = ""
    Task {
      try? await APIClient.shared.deactivateBYOK()
    }
  }

  func refreshBYOKActivation() {
    Task {
      if APIKeyService.isByokActive {
        // Validate before flipping the backend flag — otherwise we'd put the
        // user on the free plan with dead keys and every chat would 401.
        let snapshot = APIKeyService.byokSnapshot.reduce(into: [BYOKProvider: String]()) {
          acc, entry in acc[entry.key] = entry.value.key
        }
        let results = await BYOKValidator.validateAll(snapshot)
        let allOk = results.allSatisfy {
          if case .ok = $0.value { return true }
          return false
        }
        if allOk {
          let fingerprints = APIKeyService.byokSnapshot.reduce(into: [String: String]()) {
            acc, entry in acc[entry.key.rawValue] = entry.value.fingerprint
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
              "Rejected by provider: \(names). Free plan stays off until all 4 keys authenticate."
          }
        }
      } else {
        try? await APIClient.shared.deactivateBYOK()
        await FloatingBarUsageLimiter.shared.fetchPlan()
        await MainActor.run {
          byokKeyStatuses = [:]
          byokActivationError = nil
        }
      }
      await MainActor.run { loadSubscriptionInfo() }
    }
  }

  func developerKeyField(
    provider: BYOKProvider? = nil,
    title: String, subtitle: String, settingId: String, value: Binding<String>
  ) -> some View {
    settingsCard(settingId: settingId) {
      VStack(alignment: .leading, spacing: 8) {
        HStack {
          Text(title)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
          Spacer()
          if let provider, let status = byokKeyStatuses[provider] {
            byokStatusBadge(status)
          }
        }
        Text(subtitle)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
        SecureField("Leave blank for default", text: value)
          .textFieldStyle(.roundedBorder)
          .scaledFont(size: 13)
        if let provider, case .failed(let msg) = byokKeyStatuses[provider] ?? .notChecked {
          Text(msg)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.warning)
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
      HStack(spacing: 4) {
        ProgressView().controlSize(.mini)
        Text("Checking…").scaledFont(size: 11).foregroundColor(OmiColors.textTertiary)
      }
    case .ok:
      Text("Valid").scaledFont(size: 11, weight: .semibold).foregroundColor(OmiColors.success)
    case .failed:
      Text("Invalid").scaledFont(size: 11, weight: .semibold).foregroundColor(OmiColors.warning)
    }
  }

}

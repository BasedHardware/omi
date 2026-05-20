import SwiftUI

/// Final step before Tasks: offer a free-forever plan if the user supplies their
/// own API keys. Keys live on the device (UserDefaults); the backend receives
/// only SHA-256 fingerprints.
struct OnboardingBYOKStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  @AppStorage(BYOKProvider.openai.storageKey) private var openaiKey: String = ""
  @AppStorage(BYOKProvider.anthropic.storageKey) private var anthropicKey: String = ""
  @AppStorage(BYOKProvider.gemini.storageKey) private var geminiKey: String = ""
  @AppStorage(BYOKProvider.deepgram.storageKey) private var deepgramKey: String = ""

  @State private var isActivating = false
  @State private var activationError: String?
  @State private var keyStatuses: [BYOKProvider: BYOKValidator.Status] = [:]
  @State private var localCapabilities = OnboardingBYOKStepView.detectLocalCapabilities()
  @State private var providerSelection = TranscriptionProviderSelection.default

  private var recommendation: TranscriptionProviderOnboardingRecommendation {
    TranscriptionProviderOnboardingAdvisor().recommendation(capabilities: localCapabilities)
  }

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Free forever",
      title: "Choose transcription.",
      description:
        "Use local Whisper for continuous background transcription when this Mac can support it, or keep the existing cloud transcription path. Push-to-Talk may still use cloud. API keys are optional unless you want the free-forever plan.",
      showsSkip: true,
      onSkip: {
        AnalyticsManager.shared.onboardingStepCompleted(step: stepIndex, stepName: "BYOK_Skipped")
        onSkip()
      },
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: 18) {
        transcriptionChoice

        Divider()
          .background(Color.white.opacity(0.08))
          .frame(maxWidth: 560)

        VStack(alignment: .leading, spacing: 6) {
          Text("Bring your own keys")
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(OmiColors.textPrimary)

          Text(
            "Add OpenAI, Anthropic, Gemini, and Deepgram keys to activate the free plan. Local background Whisper does not require a Deepgram key."
          )
          .font(.system(size: 12))
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: 560, alignment: .leading)

        keyField(provider: .openai, binding: $openaiKey, help: "Used for GPT calls.")
        keyField(provider: .anthropic, binding: $anthropicKey, help: "Used for Claude chat.")
        keyField(provider: .gemini, binding: $geminiKey, help: "Used for proactive AI.")
        keyField(provider: .deepgram, binding: $deepgramKey, help: "Used for cloud transcription.")

        if let activationError {
          Text(activationError)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.warning)
        }

        HStack(spacing: 12) {
          Button(isActivating ? "Activating…" : "Activate free plan") {
            Task { await activate() }
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
          .disabled(!allKeysProvided || isActivating)

          if !allKeysProvided {
            Text("Fill all four to activate.")
              .font(.system(size: 12))
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .onAppear {
      localCapabilities = OnboardingBYOKStepView.detectLocalCapabilities()
      providerSelection = AssistantSettings.shared.transcriptionProviderSelection
    }
  }

  private var transcriptionChoice: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(alignment: .top, spacing: 12) {
        Image(systemName: recommendation.canRecommendLocal ? "desktopcomputer" : "cloud.fill")
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 24)

        VStack(alignment: .leading, spacing: 5) {
          Text(recommendation.title)
            .font(.system(size: 15, weight: .semibold))
            .foregroundColor(OmiColors.textPrimary)

          Text(recommendation.detail)
            .font(.system(size: 12))
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)

          Text(recommendation.status)
            .font(.system(size: 11, weight: .medium))
            .foregroundColor(
              recommendation.canRecommendLocal ? OmiColors.success : OmiColors.warning
            )
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      .frame(maxWidth: 560, alignment: .leading)
      .padding(14)
      .background(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
              .stroke(Color.white.opacity(0.08), lineWidth: 1)
          )
      )

      HStack(spacing: 12) {
        Button(recommendation.canRecommendLocal ? "Use Local Whisper" : "Use Cloud Transcription") {
          saveProviderSelection(recommendation.recommendedSelection)
          AnalyticsManager.shared.onboardingStepCompleted(
            step: stepIndex,
            stepName: recommendation.canRecommendLocal
              ? "Transcription_Local" : "Transcription_Cloud"
          )
          onContinue()
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))

        Button("Transcribe in the Cloud") {
          saveProviderSelection(TranscriptionProviderSelection(mode: .cloud, quality: .auto))
          AnalyticsManager.shared.onboardingStepCompleted(
            step: stepIndex,
            stepName: "Transcription_Cloud"
          )
          onContinue()
        }
        .buttonStyle(OnboardingCloudChoiceButtonStyle())
      }
      .frame(maxWidth: 560, alignment: .leading)
    }
  }

  private static func detectLocalCapabilities() -> LocalTranscriptionCapabilities {
    LocalTranscriptionCapabilityDetector(
      availableEngines: { LocalASRHelperLocator.detectedEngines() }
    ).detect()
  }

  private func saveProviderSelection(_ selection: TranscriptionProviderSelection) {
    providerSelection = selection
    AssistantSettings.shared.transcriptionProviderSelection = selection
  }

  private var allKeysProvided: Bool {
    [openaiKey, anthropicKey, geminiKey, deepgramKey].allSatisfy {
      !$0.trimmingCharacters(in: .whitespaces).isEmpty
    }
  }

  private func keyField(provider: BYOKProvider, binding: Binding<String>, help: String)
    -> some View
  {
    VStack(alignment: .leading, spacing: 6) {
      HStack {
        Text(provider.displayName)
          .font(.system(size: 14, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        statusBadge(for: keyStatuses[provider] ?? .notChecked)
        Text(help)
          .font(.system(size: 12))
          .foregroundColor(OmiColors.textTertiary)
      }
      SecureField("Paste \(provider.displayName) API key", text: binding)
        .textFieldStyle(.plain)
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .fill(OmiColors.backgroundSecondary)
            .overlay(
              RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
        )
        .foregroundColor(OmiColors.textPrimary)
      if case .failed(let msg) = keyStatuses[provider] ?? .notChecked {
        Text(msg)
          .font(.system(size: 11))
          .foregroundColor(OmiColors.warning)
      }
    }
    .frame(maxWidth: 560)
  }

  @ViewBuilder
  private func statusBadge(for status: BYOKValidator.Status) -> some View {
    switch status {
    case .notChecked:
      EmptyView()
    case .checking:
      HStack(spacing: 4) {
        ProgressView().controlSize(.mini)
        Text("Checking…").font(.system(size: 11)).foregroundColor(OmiColors.textTertiary)
      }
    case .ok:
      Text("Valid").font(.system(size: 11, weight: .semibold)).foregroundColor(OmiColors.success)
    case .failed:
      Text("Invalid").font(.system(size: 11, weight: .semibold)).foregroundColor(OmiColors.warning)
    }
  }

  private func activate() async {
    activationError = nil
    isActivating = true
    defer { isActivating = false }

    // Step 1: ping each provider. Refuse activation if any key is rejected —
    // otherwise the user pays a subscription they shouldn't and nothing works.
    let keysToCheck: [BYOKProvider: String] = [
      .openai: openaiKey,
      .anthropic: anthropicKey,
      .gemini: geminiKey,
      .deepgram: deepgramKey,
    ]
    for provider in BYOKProvider.allCases {
      keyStatuses[provider] = .checking
    }
    let results = await BYOKValidator.validateAll(keysToCheck)
    keyStatuses = results

    let failed = results.filter {
      if case .ok = $0.value { return false }
      return true
    }
    if !failed.isEmpty {
      let names = failed.keys.map(\.displayName).sorted().joined(separator: ", ")
      activationError =
        "These keys were rejected by their provider: \(names). Fix them to continue."
      return
    }

    // Step 2: all four authenticate — flip the backend flag.
    do {
      try await APIClient.shared.activateBYOK(
        fingerprints: BYOKProvider.allCases.reduce(into: [:]) {
          acc, provider in
          if let key = APIKeyService.byokKey(provider) {
            acc[provider.rawValue] = APIKeyService.byokFingerprint(key)
          }
        })
      // Refresh the in-memory quota snapshot — otherwise the client keeps
      // blocking chat against the stale basic-tier 30-message cap.
      await FloatingBarUsageLimiter.shared.fetchPlan()
      AnalyticsManager.shared.onboardingStepCompleted(step: stepIndex, stepName: "BYOK_Activated")
      onContinue()
    } catch {
      activationError =
        "Could not activate free plan: \(error.localizedDescription). Your keys are saved on this Mac; you can try again from Settings → Advanced."
    }
  }
}

private struct OnboardingCloudChoiceButtonStyle: ButtonStyle {
  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .font(.system(size: 12, weight: .semibold))
      .foregroundColor(OmiColors.textTertiary)
      .padding(.horizontal, 10)
      .padding(.vertical, 8)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(Color.white.opacity(configuration.isPressed ? 0.08 : 0.04))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .stroke(Color.white.opacity(0.06), lineWidth: 1)
      )
  }
}

import SwiftUI

/// Final step before Tasks: offer a free-forever plan if the user supplies their
/// own API keys for OpenAI, Anthropic, Gemini, and Deepgram. Keys live on the
/// device (UserDefaults); the backend receives only SHA-256 fingerprints.
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

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Free forever",
      title: "Bring your own keys.",
      description:
        "Paste your own API keys for OpenAI, Anthropic, Gemini, and Deepgram and Omi is free forever. Keys stay on this Mac — we never store them on our servers.",
      showsSkip: true,
      onSkip: {
        AnalyticsManager.shared.onboardingStepCompleted(step: stepIndex, stepName: "BYOK_Skipped")
        onSkip()
      },
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: 18) {
        keyField(provider: .openai, binding: $openaiKey, help: "Used for GPT calls.")
        keyField(provider: .anthropic, binding: $anthropicKey, help: "Used for Claude chat.")
        keyField(provider: .gemini, binding: $geminiKey, help: "Used for proactive AI.")
        keyField(provider: .deepgram, binding: $deepgramKey, help: "Used for transcription.")

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
    }
    .frame(maxWidth: 560)
  }

  private func activate() async {
    activationError = nil
    isActivating = true
    defer { isActivating = false }

    do {
      try await APIClient.shared.activateBYOK(fingerprints: BYOKProvider.allCases.reduce(into: [:]) {
        acc, provider in
        if let key = APIKeyService.byokKey(provider) {
          acc[provider.rawValue] = APIKeyService.byokFingerprint(key)
        }
      })
      AnalyticsManager.shared.onboardingStepCompleted(step: stepIndex, stepName: "BYOK_Activated")
      onContinue()
    } catch {
      activationError =
        "Could not activate free plan: \(error.localizedDescription). Your keys are saved on this Mac; you can try again from Settings → Advanced."
    }
  }
}

import SwiftUI

// MARK: - Step 17 · Bring your own keys

struct RedesignBYOKStepView: View {
  let stepIndex: Int
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

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: "Optional",
      title: "Bring your own keys.",
      subtitle:
        "omi is free to use — just continue. Prefer to run on your own API usage? Paste your keys and hit Save. They stay on this Mac; we only ever store a fingerprint.",
      centeredText: false,
      onForceComplete: onForceComplete,
      maxWidth: 560
    ) {
      VStack(alignment: .leading, spacing: 16) {
        keyField(provider: .openai, binding: $openaiKey, help: "Used for GPT calls.")
        keyField(provider: .anthropic, binding: $anthropicKey, help: "Used for Claude chat.")
        keyField(provider: .gemini, binding: $geminiKey, help: "Used for proactive AI.")
        keyField(provider: .deepgram, binding: $deepgramKey, help: "Used for transcription.")

        if let activationError { RedesignOnboardingError(message: activationError) }

        HStack(spacing: 12) {
          InkButton(title: "Skip for now", kind: .primary, size: .lg) {
            AnalyticsManager.shared.onboardingStepCompleted(step: stepIndex, stepName: "BYOK_Skipped")
            onSkip()
          }
          .disabled(isActivating)

          InkButton(title: isActivating ? "Saving…" : "Save keys", kind: .plain, size: .lg) {
            Task { await activate() }
          }
          .disabled(!allKeysProvided || isActivating)
        }

        Text("Adding keys is optional — fill all four to run on your own API usage.")
          .font(InkFont.sans(12)).foregroundColor(Ink.faint)
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
        Text(provider.displayName).font(InkFont.sans(14, .semibold)).foregroundColor(Ink.ink)
        Spacer()
        statusBadge(for: keyStatuses[provider] ?? .notChecked)
        Text(help).font(InkFont.sans(12)).foregroundColor(Ink.faint)
      }
      RedesignOnboardingField(
        placeholder: "Paste \(provider.displayName) API key", text: binding, secure: true,
        maxWidth: nil)
      if case .failed(let msg) = keyStatuses[provider] ?? .notChecked {
        Text(msg).font(InkFont.sans(11)).foregroundColor(Ink.warnText)
      }
    }
  }

  @ViewBuilder
  private func statusBadge(for status: BYOKValidator.Status) -> some View {
    switch status {
    case .notChecked:
      EmptyView()
    case .checking:
      HStack(spacing: 4) {
        ProgressView().controlSize(.mini)
        Text("Checking…").font(InkFont.sans(11)).foregroundColor(Ink.faint)
      }
    case .ok:
      Text("Valid").font(InkFont.sans(11, .semibold)).foregroundColor(Ink.sentText)
    case .failed:
      Text("Invalid").font(InkFont.sans(11, .semibold)).foregroundColor(Ink.warnText)
    }
  }

  private func activate() async {
    activationError = nil
    isActivating = true
    defer { isActivating = false }

    let keysToCheck: [BYOKProvider: String] = [
      .openai: openaiKey, .anthropic: anthropicKey, .gemini: geminiKey, .deepgram: deepgramKey,
    ]
    for provider in BYOKProvider.allCases { keyStatuses[provider] = .checking }
    let results = await BYOKValidator.validateAll(keysToCheck)
    keyStatuses = results

    let failed = results.filter {
      if case .ok = $0.value { return false }
      return true
    }
    if !failed.isEmpty {
      let names = failed.keys.map(\.displayName).sorted().joined(separator: ", ")
      activationError = "These keys were rejected by their provider: \(names). Fix them to continue."
      return
    }

    do {
      try await APIClient.shared.activateBYOK(
        fingerprints: BYOKProvider.allCases.reduce(into: [:]) { acc, provider in
          if let key = APIKeyService.byokKey(provider) {
            acc[provider.rawValue] = APIKeyService.byokFingerprint(key)
          }
        })
      await FloatingBarUsageLimiter.shared.fetchPlan()
      AnalyticsManager.shared.onboardingStepCompleted(step: stepIndex, stepName: "BYOK_Activated")
      onContinue()
    } catch {
      activationError =
        "Could not activate free plan: \(error.localizedDescription). Your keys are saved on this Mac; you can try again from Settings → Advanced."
    }
  }
}

// MARK: - Step 18 · You're set (mockup: ob-ping / final)

struct RedesignTasksStepView: View {
  let stepIndex: Int
  var onComplete: () -> Void
  var onSkip: (() -> Void)? = nil
  var onForceComplete: (() -> Void)?

  var body: some View {
    VStack(spacing: 0) {
      RedesignOnboardingChrome(
        beat: RedesignOnboarding.beat(forStep: stepIndex), onForceComplete: onForceComplete)

      Spacer()

      VStack(spacing: 26) {
        BuddyRing(diameter: 64, dot: 8, color: Ink.ink)

        VStack(spacing: 12) {
          Text("You're set.\nI'll take it from here.")
            .inkDisplay(32).multilineTextAlignment(.center)
          Text("I'll catch things like this all day — you won't have to ask.")
            .inkBody().multilineTextAlignment(.center).frame(maxWidth: 420)
        }

        // A sample proactive ping (mockup ob-ping toast), decorative.
        pingToast
          .frame(maxWidth: 420)
      }
      .padding(.horizontal, 40)

      Spacer()

      InkButton(title: "Take me to omi", kind: .primary, size: .lg, action: onComplete)
        .padding(.bottom, 36)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  private var pingToast: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack(spacing: 8) {
        LiveDot(color: Ink.warn, size: 7)
        Text("omi").font(InkFont.serif(14)).foregroundColor(Ink.ink)
        Spacer()
        Text("now").inkCaption()
      }
      Text("Reply to Sarah before 3pm — you promised her the deck.")
        .font(InkFont.sans(14.5, .medium)).foregroundColor(Ink.ink)
        .fixedSize(horizontal: false, vertical: true)
      Text("I already drafted it from your thread.")
        .font(InkFont.sans(13)).foregroundColor(Ink.muted)
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface)
        .overlay(alignment: .leading) {
          Rectangle().fill(Ink.accent).frame(width: 3)
            .clipShape(RoundedRectangle(cornerRadius: 2))
        }
        .overlay(
          RoundedRectangle(cornerRadius: 14).strokeBorder(Ink.hair, lineWidth: 1))
    )
  }
}

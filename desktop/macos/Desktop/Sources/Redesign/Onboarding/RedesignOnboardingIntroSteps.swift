import AppKit
import SwiftUI

// MARK: - Step 0 · Name  (mockup: ob-welcome)

/// Two-column welcome: left copy + name field, right second-brain node graph.
/// Wiring preserved: `coordinator.draftName` / `confirmPreferredName()`.
struct RedesignNameStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  let stepIndex: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  var body: some View {
    VStack(spacing: 0) {
      RedesignOnboardingChrome(
        beat: RedesignOnboarding.beat(forStep: stepIndex), onForceComplete: onForceComplete)

      GeometryReader { geo in
        HStack(spacing: 0) {
          leftPane
            .frame(width: max(360, geo.size.width * 0.5))

          Rectangle().fill(Ink.hair).frame(width: 1)

          RedesignLiveBrainGraph()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear {
      coordinator.clearLastActionError()
      coordinator.draftName = coordinator.preferredName
    }
  }

  private var leftPane: some View {
    VStack(alignment: .leading, spacing: 0) {
      Spacer(minLength: 0)

      Text("Step 1").inkEyebrow()

      Text("This is your\nsecond brain.")
        .inkDisplay(38)
        .padding(.top, 14)

      Text(
        "It starts empty. In a minute it'll know more about your week than you remember. First — who am I working for?"
      )
      .inkBody()
      .frame(maxWidth: 380, alignment: .leading)
      .fixedSize(horizontal: false, vertical: true)
      .padding(.top, 16)

      VStack(alignment: .leading, spacing: 8) {
        Text("What should I call you?").inkCaption()
        RedesignOnboardingField(placeholder: "Your name", text: $coordinator.draftName)
          .onSubmit(confirm)
      }
      .padding(.top, 28)

      if let error = coordinator.lastActionError {
        RedesignOnboardingError(message: error).padding(.top, 12)
      }

      HStack(spacing: 12) {
        InkButton(title: "Continue", kind: .primary, size: .lg, action: confirm)

        if AnalyticsManager.isDevBuild {
          Button("Skip onboarding") { onForceComplete?() }
            .buttonStyle(.plain)
            .font(InkFont.sans(12, .medium))
            .foregroundColor(Ink.faint)
        }
      }
      .padding(.top, 28)

      Spacer(minLength: 0)
    }
    .padding(.horizontal, 56)
    .frame(maxHeight: .infinity)
  }

  private func confirm() {
    Task {
      await coordinator.confirmPreferredName()
      if coordinator.lastActionError == nil { onContinue() }
    }
  }
}

// MARK: - Step 1 · Language

struct RedesignLanguageStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  let stepIndex: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var showingCustom = false

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: "Language",
      title: "What language should I think in?",
      subtitle: "I'll use it for prompts and transcripts.",
      centeredText: false,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: 16) {
        HStack(spacing: 12) {
          RedesignOnboardingChip(
            title: "English", selected: coordinator.selectedLanguageCode == "en"
          ) {
            showingCustom = false
            Task {
              await coordinator.selectEnglish()
              if coordinator.lastActionError == nil { onContinue() }
            }
          }
          RedesignOnboardingChip(
            title: "Other", selected: showingCustom && coordinator.selectedLanguageCode != "en"
          ) {
            showingCustom = true
          }
        }

        if showingCustom {
          VStack(alignment: .leading, spacing: 12) {
            RedesignOnboardingField(
              placeholder: "Spanish, Portuguese, Japanese…",
              text: $coordinator.customLanguage, maxWidth: 360)
            InkButton(title: "Save language", kind: .primary, size: .md) {
              Task {
                await coordinator.setCustomLanguage()
                if coordinator.lastActionError == nil { onContinue() }
              }
            }
          }
        }

        if let error = coordinator.lastActionError {
          RedesignOnboardingError(message: error)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }
}

// MARK: - Step 2 · How did you hear

struct RedesignHowDidYouHearStepView: View {
  let stepIndex: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var selectedSource: String?
  @State private var shuffledSources: [String] = []

  private static let sources = [
    "Social media", "YouTube", "Newsletter", "AI chat", "Search engine", "Event",
    "Friend", "Colleague", "Podcast", "Article", "Product Hunt", "Other",
  ]

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: "Quick question",
      title: "How did you find me?",
      centeredText: false,
      onForceComplete: onForceComplete
    ) {
      FlowLayout(spacing: 10) {
        ForEach(shuffledSources, id: \.self) { source in
          RedesignOnboardingChip(title: source, selected: selectedSource == source) {
            selectedSource = source
            AnalyticsManager.shared.onboardingHowDidYouHear(source: source)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { onContinue() }
          }
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        if shuffledSources.isEmpty { shuffledSources = Self.sources.shuffled() }
      }
    }
  }
}

// MARK: - Step 3 · Trust  (mockup: ob-promise)

struct RedesignTrustStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  let stepIndex: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      title: "From now on, nothing\ngets past you.",
      subtitle: "I watch your back all day. You stay in flow. Open source, private by design.",
      titleSize: 40,
      onForceComplete: onForceComplete
    ) {
      VStack(spacing: 24) {
        // Ghosted "Ask omi anything" spotlight bar (mockup ghost-bar).
        HStack(spacing: 12) {
          Image(systemName: "sparkles").font(.system(size: 16)).foregroundColor(Ink.faint)
          Text("Ask omi anything").font(InkFont.sans(16)).foregroundColor(Ink.faint)
          Spacer()
          Text("⌘⇧Space")
            .font(InkFont.mono(12))
            .foregroundColor(Ink.muted)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(
              RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(Ink.surface2).overlay(
                  RoundedRectangle(cornerRadius: 6).strokeBorder(Ink.hair, lineWidth: 1)))
        }
        .padding(.horizontal, 20).padding(.vertical, 18)
        .frame(maxWidth: 460)
        .background(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(Ink.surface).overlay(
              RoundedRectangle(cornerRadius: 14).strokeBorder(Ink.hair, lineWidth: 1)))
        .opacity(0.55)

        HStack(spacing: 12) {
          InkButton(title: "I'm in", kind: .primary, size: .lg) {
            coordinator.clearLastActionError()
            onContinue()
          }
          Button("Read the source code") {
            guard let url = URL(string: "https://github.com/BasedHardware/omi") else { return }
            NSWorkspace.shared.open(url)
          }
          .buttonStyle(.plain)
          .font(InkFont.sans(13, .medium))
          .foregroundColor(Ink.muted)
        }
      }
      .frame(maxWidth: .infinity, alignment: .center)
      .onAppear { coordinator.clearLastActionError() }
    }
  }
}

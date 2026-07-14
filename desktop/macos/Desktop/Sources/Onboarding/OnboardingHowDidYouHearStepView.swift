import SwiftUI
import OmiTheme

struct OnboardingHowDidYouHearStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @AppStorage("onboardingHowDidYouHearSource") private var selectedSource: String = ""
  @State private var shuffledSources: [String] = []

  private static let sources = [
    "Social media",
    "YouTube",
    "Newsletter",
    "AI chat",
    "Search engine",
    "Event",
    "Friend",
    "Colleague",
    "Podcast",
    "Article",
    "Product Hunt",
    "Other",
  ]

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Quick question",
      title: "How did you hear\nabout Omi?",
      description: "",
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        FlowLayout(spacing: OmiSpacing.sm) {
          ForEach(shuffledSources, id: \.self) { source in
            OnboardingSelectableChip(
              title: source,
              isSelected: selectedSource == source
            ) {
              selectedSource = source
              AnalyticsManager.shared.onboardingHowDidYouHear(source: source)
              // Answering auto-advances; the saved selection is restored (and
              // shown pre-selected) if the user comes back to this step.
              DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                onContinue()
              }
            }
          }
        }

        OnboardingBackButton()
          .padding(.top, OmiSpacing.sm)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        if shuffledSources.isEmpty {
          shuffledSources = Self.sources.shuffled()
        }
      }
    }
  }
}

// Uses FlowLayout from AppsPage.swift

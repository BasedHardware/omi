import SwiftUI

struct OnboardingHowDidYouHearStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var selectedSource: String?
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
      VStack(alignment: .leading, spacing: 12) {
        FlowLayout(spacing: 10) {
          ForEach(shuffledSources, id: \.self) { source in
            OnboardingSelectableChip(
              title: source,
              isSelected: selectedSource == source
            ) {
              selectedSource = source
              AnalyticsManager.shared.onboardingHowDidYouHear(source: source)
              DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                onContinue()
              }
            }
          }
        }
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

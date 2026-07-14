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
  /// True when the step appeared with an answer already saved (a revisit).
  /// Only the first-ever selection auto-advances; revisits use Continue so
  /// changing your saved answer doesn't yank you forward.
  @State private var hadSelectionOnAppear = false

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
              // First-ever answer auto-advances; on a revisit the user changes
              // the saved selection and moves on with the Continue button.
              if !hadSelectionOnAppear {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                  onContinue()
                }
              }
            }
          }
        }

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if hadSelectionOnAppear {
            Button("Continue", action: onContinue)
              .buttonStyle(OmiButtonStyle(.primary))
              .keyboardShortcut(.defaultAction)
          }
        }
        .padding(.top, OmiSpacing.sm)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        hadSelectionOnAppear = !selectedSource.isEmpty
        if shuffledSources.isEmpty {
          shuffledSources = Self.sources.shuffled()
        }
      }
    }
  }
}

// Uses FlowLayout from AppsPage.swift

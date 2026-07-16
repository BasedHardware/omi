import SwiftUI
import OmiTheme

struct OnboardingHowDidYouHearStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @AppStorage("onboardingHowDidYouHearSource") private var selectedSource: String = ""
  /// True when the step appeared with an answer already saved (a revisit).
  /// Only the first-ever selection auto-advances; revisits use Continue so
  /// changing your saved answer doesn't yank you forward.
  @State private var hadSelectionOnAppear = false
  @State private var advanceTask: Task<Void, Never>?

  static let sources: [(name: String, icon: String)] = [
    ("Social media", "bubble.left.and.bubble.right.fill"),
    ("YouTube", "play.rectangle.fill"),
    ("Friend", "person.fill"),
    ("Search engine", "magnifyingglass"),
    ("AI chat", "sparkles"),
    ("Podcast", "waveform"),
    ("Colleague", "person.2.fill"),
    ("Article", "newspaper.fill"),
    ("Product Hunt", "arrowtriangle.up.circle.fill"),
    ("Newsletter", "envelope.fill"),
    ("Event", "calendar"),
    ("Other", "ellipsis"),
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
          ForEach(Self.sources, id: \.name) { source in
            OnboardingSelectableChip(
              title: source.name,
              icon: source.icon,
              isSelected: selectedSource == source.name
            ) {
              selectedSource = source.name
              AnalyticsManager.shared.onboardingHowDidYouHear(source: source.name)
              // First-ever answer auto-advances; on a revisit the user changes
              // the saved selection and moves on with the Continue button.
              if !hadSelectionOnAppear {
                advanceTask?.cancel()
                advanceTask = Task {
                  try? await Task.sleep(nanoseconds: 250_000_000)
                  guard !Task.isCancelled else { return }
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
      }
      .onDisappear {
        advanceTask?.cancel()
      }
    }
  }
}

// Uses FlowLayout from AppsPage.swift

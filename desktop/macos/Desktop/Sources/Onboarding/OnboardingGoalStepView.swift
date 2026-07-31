import OmiTheme
import SwiftUI

struct OnboardingGoalStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var customGoalSelected = false
  @State private var saveTask: Task<Void, Never>?

  private static let customGoalOption = "Type my own"

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Goal",
      title: "Pick one goal.",
      description:
        "Selecting a correct and detailed goal is very important - Omi will optimize all advice to achieve that goal. Make sure your goal contains a number to measure progress.",
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        GoalChipGrid(
          items: suggestionItems,
          selectedItem: selectedSuggestion,
          onSelect: { suggestion in
            if suggestion == Self.customGoalOption {
              customGoalSelected = true
              coordinator.goalDraft = ""
            } else {
              customGoalSelected = false
              coordinator.goalDraft = suggestion
              coordinator.clearLastActionError()
            }
          }
        )
        .frame(maxWidth: 560, alignment: .leading)

        if customGoalSelected {
          TextField("Type your goal", text: $coordinator.goalDraft)
            .textFieldStyle(.plain)
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.vertical, OmiSpacing.md)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                .fill(OmiColors.backgroundSecondary)
                .overlay(
                  RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
            )
            .foregroundColor(OmiColors.textPrimary)
            .frame(maxWidth: 560)
            .onSubmit(saveGoalAndContinue)
        }

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.warning)
        }

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if shouldShowContinue {
            Button(coordinator.isSavingGoal ? "Saving…" : "Continue") {
              saveGoalAndContinue()
            }
            .buttonStyle(OmiButtonStyle(.primary))
            .keyboardShortcut(.defaultAction)
            .disabled(coordinator.isSavingGoal)
          }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        customGoalSelected =
          !coordinator.goalDraft.isEmpty && !baseSuggestions.contains(coordinator.goalDraft)
      }
      .onDisappear {
        saveTask?.cancel()
      }
    }
  }

  private var baseSuggestions: [String] {
    coordinator.goalSuggestionCards().filter { $0 != "I’ll type my own" }
  }

  private var suggestionItems: [String] {
    Array(baseSuggestions.prefix(4)) + [Self.customGoalOption]
  }

  private var selectedSuggestion: String? {
    if customGoalSelected {
      return Self.customGoalOption
    }
    return suggestionItems.contains(coordinator.goalDraft) ? coordinator.goalDraft : nil
  }

  private var trimmedGoal: String {
    coordinator.goalDraft.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private var shouldShowContinue: Bool {
    !trimmedGoal.isEmpty
  }

  private func saveGoalAndContinue() {
    guard shouldShowContinue, !coordinator.isSavingGoal else { return }
    saveTask?.cancel()
    saveTask = Task {
      // Do not reset goalSaved here: saveGoalIfNeeded's `guard !goalSaved`
      // is the only dedup protection, and createGoal has no idempotency key.
      // Resetting it meant a retry after a completeIntro failure created a
      // second backend goal.
      // Run the save in an unstructured child task so navigating away (which
      // cancels saveTask in .onDisappear) never aborts the in-flight write —
      // only the navigation side effects below are dropped.
      await Task { await coordinator.saveGoalIfNeeded() }.value
      guard coordinator.goalSaved, !Task.isCancelled else { return }
      let completed = await coordinator.completeIntro(appState: appState)
      guard completed, !Task.isCancelled else { return }
      onContinue()
    }
  }
}

private struct GoalChipGrid: View {
  let items: [String]
  let selectedItem: String?
  let onSelect: (String) -> Void

  var body: some View {
    LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: OmiSpacing.sm)], spacing: OmiSpacing.sm) {
      ForEach(items, id: \.self) { item in
        let isSelected = selectedItem == item

        Button(action: { onSelect(item) }) {
          Text(item)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(isSelected ? .black : OmiColors.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.md)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                .fill(isSelected ? Color.white : Color.white.opacity(0.05))
                .overlay(
                  RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
                    .stroke(Color.white.opacity(isSelected ? 0 : 0.08), lineWidth: 1)
                )
            )
        }
        .buttonStyle(.plain)
      }
    }
  }
}

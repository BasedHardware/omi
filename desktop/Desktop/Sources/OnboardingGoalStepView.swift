import SwiftUI

struct OnboardingGoalStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void

  @State private var customGoalSelected = false

  private static let customGoalOption = "Type my own"

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Goal",
      title: "Pick one goal.",
      description: "Omi will optimize for this first."
    ) {
      VStack(alignment: .leading, spacing: 18) {
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
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(
              RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(OmiColors.backgroundSecondary)
                .overlay(
                  RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
            )
            .foregroundColor(OmiColors.textPrimary)
            .frame(maxWidth: 560)
        }

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.warning)
        }

        Button(coordinator.isSavingGoal ? "Saving…" : "Continue") {
          Task {
            coordinator.goalSaved = false
            await coordinator.saveGoalIfNeeded()
            guard coordinator.goalSaved else { return }
            let completed = await coordinator.completeIntro(appState: appState)
            if completed {
              onContinue()
            }
          }
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        .disabled(coordinator.isSavingGoal || trimmedGoal.isEmpty)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        customGoalSelected =
          !coordinator.goalDraft.isEmpty && !baseSuggestions.contains(coordinator.goalDraft)
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
}

private struct GoalChipGrid: View {
  let items: [String]
  let selectedItem: String?
  let onSelect: (String) -> Void

  var body: some View {
    LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 10)], spacing: 10) {
      ForEach(items, id: \.self) { item in
        let isSelected = selectedItem == item

        Button(action: { onSelect(item) }) {
          Text(item)
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(isSelected ? .white : OmiColors.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(
              RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(isSelected ? OmiColors.purplePrimary : Color.white.opacity(0.05))
                .overlay(
                  RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(Color.white.opacity(isSelected ? 0 : 0.08), lineWidth: 1)
                )
            )
        }
        .buttonStyle(.plain)
      }
    }
  }
}

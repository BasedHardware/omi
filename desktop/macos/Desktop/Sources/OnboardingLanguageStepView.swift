import SwiftUI

struct OnboardingLanguageStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var showingCustomLanguage = false

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Language",
      title: "Pick your language.",
      description: "Omi will use it for prompts and transcripts.",
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: 18) {
        HStack(spacing: 12) {
          OnboardingSelectableChip(
            title: "English",
            isSelected: coordinator.selectedLanguageCode == "en"
          ) {
            showingCustomLanguage = false
            Task {
              await coordinator.selectEnglish()
              if coordinator.lastActionError == nil {
                onContinue()
              }
            }
          }

          OnboardingSelectableChip(
            title: "Other",
            isSelected: showingCustomLanguage && coordinator.selectedLanguageCode != "en"
          ) {
            showingCustomLanguage = true
          }
        }

        if showingCustomLanguage {
          VStack(alignment: .leading, spacing: 12) {
            TextField("Spanish, Portuguese, Japanese…", text: $coordinator.customLanguage)
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
              .onSubmit(saveCustomLanguage)

            Button("Save language") {
              saveCustomLanguage()
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
            .keyboardShortcut(.defaultAction)
          }
        }

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.warning)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private func saveCustomLanguage() {
    Task {
      await coordinator.setCustomLanguage()
      if coordinator.lastActionError == nil {
        onContinue()
      }
    }
  }
}

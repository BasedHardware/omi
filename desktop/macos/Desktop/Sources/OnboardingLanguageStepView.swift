import SwiftUI

struct OnboardingLanguageStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var showingCustomLanguage = false
  @State private var saving = false

  /// The chip row: common languages plus any custom-added codes outside that set.
  private var chipOptions: [(code: String, name: String)] {
    let common = OnboardingPagedIntroCoordinator.commonLanguages
    let extra = coordinator.selectedLanguageCodes
      .filter { code in !common.contains(where: { $0.code == code }) }
      .map { (code: $0, name: Self.displayName($0)) }
    return common + extra
  }

  private var primaryName: String? {
    coordinator.selectedLanguageCodes.first.map(Self.displayName)
  }

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Languages",
      title: "Pick every language you speak.",
      description: "Omi listens in all of them — your first pick is the primary, used for prompts and summaries.",
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: 18) {
        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 108), spacing: 8)],
          alignment: .leading, spacing: 8
        ) {
          ForEach(chipOptions, id: \.code) { option in
            OnboardingSelectableChip(
              title: chipTitle(option),
              isSelected: coordinator.selectedLanguageCodes.contains(option.code)
            ) {
              coordinator.toggleLanguage(code: option.code)
            }
          }
          OnboardingSelectableChip(
            title: "Other…",
            isSelected: showingCustomLanguage
          ) {
            showingCustomLanguage.toggle()
          }
        }

        if showingCustomLanguage {
          HStack(spacing: 10) {
            TextField("Ukrainian, Korean, Turkish…", text: $coordinator.customLanguage)
              .textFieldStyle(.plain)
              .padding(.horizontal, 16)
              .padding(.vertical, 12)
              .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                  .fill(OmiColors.backgroundSecondary)
                  .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                      .stroke(Color.white.opacity(0.08), lineWidth: 1)
                  )
              )
              .foregroundColor(OmiColors.textPrimary)
              .onSubmit { coordinator.addCustomLanguage() }

            Button("Add") {
              coordinator.addCustomLanguage()
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
          }
        }

        if let primaryName {
          Text("Primary: \(primaryName)")
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.textTertiary)
        }

        Button(saving ? "Saving…" : "Continue") {
          saveAndContinue()
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        .keyboardShortcut(.defaultAction)
        .disabled(coordinator.selectedLanguageCodes.isEmpty || saving)

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.warning)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private func chipTitle(_ option: (code: String, name: String)) -> String {
    option.code == coordinator.selectedLanguageCodes.first ? "\(option.name) ✓" : option.name
  }

  private func saveAndContinue() {
    saving = true
    Task {
      await coordinator.confirmLanguages()
      saving = false
      if coordinator.lastActionError == nil {
        onContinue()
      }
    }
  }

  private static func displayName(_ code: String) -> String {
    AssistantSettings.supportedLanguages.first(where: { $0.code == code })?.name
      ?? Locale(identifier: "en").localizedString(forLanguageCode: code)
      ?? code
  }
}

import OmiTheme
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

  /// Flag shown before each language chip; custom/other languages get a globe.
  private static let flags: [String: String] = [
    "en": "🇺🇸", "es": "🇪🇸", "fr": "🇫🇷", "de": "🇩🇪", "pt": "🇵🇹",
    "ru": "🇷🇺", "hi": "🇮🇳", "ja": "🇯🇵", "it": "🇮🇹", "nl": "🇳🇱",
  ]

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Languages",
      title: "Pick every language you speak.",
      description: "Omi listens to all of them. Your first pick is the primary.",
      layoutMode: .centered,
      onForceComplete: onForceComplete
    ) {
      VStack(spacing: OmiSpacing.lg) {
        FlowLayout(spacing: OmiSpacing.sm) {
          ForEach(chipOptions, id: \.code) { option in
            OnboardingSelectableChip(
              title: chipTitle(option),
              leading: AnyView(Text(Self.flags[option.code] ?? "🌐").font(.system(size: 13))),
              isSelected: coordinator.selectedLanguageCodes.contains(option.code)
            ) {
              coordinator.toggleLanguage(code: option.code)
            }
          }
          OnboardingSelectableChip(
            title: "Other",
            leading: AnyView(Text("🌐").font(.system(size: 13))),
            isSelected: showingCustomLanguage
          ) {
            showingCustomLanguage.toggle()
          }
        }

        if showingCustomLanguage {
          HStack(spacing: OmiSpacing.sm) {
            TextField("Ukrainian, Korean, Turkish…", text: $coordinator.customLanguage)
              .textFieldStyle(.plain)
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.md)
              .glassField()
              .foregroundColor(Ink.primary)
              .onSubmit { coordinator.addCustomLanguage() }

            Button("Add") {
              coordinator.addCustomLanguage()
            }
            .buttonStyle(InkButtonStyle(kind: .secondary))
          }
        }

        if let primaryName {
          Text("Primary: \(primaryName)")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          Button(saving ? "Saving…" : "Continue") {
            saveAndContinue()
          }
          .buttonStyle(InkButtonStyle(kind: .primary))
          .keyboardShortcut(.defaultAction)
          .disabled(coordinator.selectedLanguageCodes.isEmpty || saving)
        }

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(PageGlass.warning)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      .frame(maxWidth: .infinity, alignment: .center)
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

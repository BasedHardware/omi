import OmiTheme
import SwiftUI

struct OnboardingWelcomeStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onForceComplete: (() -> Void)?

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Name",
      title: "What should Omi call you?",
      description: "",
      layoutMode: .centered,
      onForceComplete: onForceComplete
    ) {
      VStack(spacing: OmiSpacing.lg) {
        TextField("Your name", text: $coordinator.draftName)
          .textFieldStyle(.plain)
          .padding(.horizontal, OmiSpacing.lg)
          .padding(.vertical, OmiSpacing.md)
          .glassField()
          .foregroundColor(Ink.primary)
          .frame(maxWidth: 320)
          .onSubmit(confirmName)

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(PageGlass.warning)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
        }

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          Button("Continue") {
            confirmName()
          }
          .buttonStyle(InkButtonStyle(kind: .primary))
          .keyboardShortcut(.defaultAction)
        }

        // Dev-only shortcut to skip the whole onboarding flow — same as the
        // hidden logo long-press. Never shown on production builds.
        if AnalyticsManager.isDevBuild {
          Button("Skip onboarding") {
            onForceComplete?()
          }
          .buttonStyle(.plain)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
      }
      .frame(maxWidth: .infinity, alignment: .center)
      .onAppear {
        coordinator.clearLastActionError()
        coordinator.draftName = OnboardingFlow.nameFieldPrefill(coordinator.preferredName)
      }
    }
  }

  private func confirmName() {
    Task {
      await coordinator.confirmPreferredName()
      if coordinator.lastActionError == nil {
        onContinue()
      }
    }
  }
}

import AppKit
import SwiftUI

struct OnboardingTrustStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "",
      title: "Trust",
      description:
        "In onboarding, Omi needs to learn about you and access a few permissions to be useful. Without them, Omi cannot help much. Can we proceed?",
      layoutMode: .centered
    ) {
      VStack(spacing: 18) {
        HStack(spacing: 12) {
          Button("Yes, let's go") {
            coordinator.clearLastActionError()
            onContinue()
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))

          Button("No, show the source code") {
            guard let url = URL(string: "https://github.com/BasedHardware/omi") else { return }
            NSWorkspace.shared.open(url)
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: false))
        }
      }
      .frame(maxWidth: .infinity, alignment: .center)
      .onAppear {
        coordinator.clearLastActionError()
      }
    }
  }
}

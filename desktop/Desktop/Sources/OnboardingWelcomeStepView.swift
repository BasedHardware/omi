import SwiftUI

struct OnboardingWelcomeStepView: View {
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
      eyebrow: "Name",
      title: "What should Omi call you?",
      description: "",
      layoutMode: .centered
    ) {
      VStack(spacing: 18) {
        TextField("Your name", text: $coordinator.draftName)
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
          .frame(maxWidth: 320)

        if let error = coordinator.lastActionError {
          Text(error)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(OmiColors.warning)
            .multilineTextAlignment(.center)
        }

        Button("Continue") {
          Task {
            await coordinator.confirmPreferredName()
            if coordinator.lastActionError == nil {
              onContinue()
            }
          }
        }
        .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
      }
      .frame(maxWidth: .infinity, alignment: .center)
      .onAppear {
        coordinator.clearLastActionError()
        coordinator.draftName = coordinator.preferredName
      }
    }
  }
}

import AppKit
import SwiftUI
import OmiTheme

struct OnboardingTrustStepView: View {
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
      eyebrow: "Before we continue",
      title: "I’m going to ask for a few permissions.",
      description:
        "Omi is open source and private by design. During setup, we’ll ask for these permissions to understand your work and help in the right places:",
      layoutMode: .centered,
      onForceComplete: onForceComplete
    ) {
      VStack(spacing: OmiSpacing.lg) {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          permissionRow(
            icon: "display", title: "Screen + files",
            detail: "Build context from what you’re working on.")
          permissionRow(
            icon: "mic.fill", title: "Microphone",
            detail: "Capture voice notes and meeting context.")
          permissionRow(
            icon: "sparkles", title: "Accessibility + automation",
            detail: "Know the active app and act when you ask.")
        }
        .frame(maxWidth: 560, alignment: .leading)

        HStack(spacing: OmiSpacing.md) {
          Button("Continue") {
            coordinator.clearLastActionError()
            onContinue()
          }
          .buttonStyle(OmiButtonStyle(.primary))
          .keyboardShortcut(.defaultAction)

          Button("Read the source code") {
            guard let url = URL(string: "https://github.com/BasedHardware/omi") else { return }
            NSWorkspace.shared.open(url)
          }
          .buttonStyle(.plain)
          .foregroundColor(OmiColors.textSecondary)
          .font(.system(size: 13, weight: .medium))
        }
      }
      .frame(maxWidth: .infinity, alignment: .center)
      .onAppear {
        coordinator.clearLastActionError()
      }
    }
  }

  private func permissionRow(icon: String, title: String, detail: String) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      Image(systemName: icon)
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(.white.opacity(0.85))
        .frame(width: 28, height: 28)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
            .fill(OmiColors.backgroundSecondary)
        )

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(title)
          .font(.system(size: 14, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
        Text(detail)
          .font(.system(size: 13))
          .foregroundColor(OmiColors.textSecondary)
      }

      Spacer()
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
        .fill(OmiColors.backgroundTertiary.opacity(0.55))
    )
  }
}

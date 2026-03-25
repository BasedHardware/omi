import SwiftUI

struct OnboardingFileScanStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onSkip: () -> Void

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Discovery",
      title: "Map your work once.",
      description: "Omi scans projects and recent files.",
      showsSkip: true,
      onSkip: onSkip
    ) {
      VStack(alignment: .leading, spacing: 24) {
        ZStack {
          RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(OmiColors.backgroundSecondary)
            .overlay(
              RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )

          VStack(spacing: 20) {
            OnboardingLoadingAnimation(progress: scanProgress)
              .frame(height: 160)

            Text(coordinator.scanStatusText)
              .font(.system(size: 18, weight: .semibold))
              .foregroundColor(OmiColors.textPrimary)

            if let snapshot = coordinator.scanSnapshot {
              Text("\(snapshot.fileCount.formatted()) files indexed")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(OmiColors.textTertiary)
                .monospacedDigit()
            } else {
              Text("Your graph and suggestions will build from this scan.")
                .font(.system(size: 13))
                .foregroundColor(OmiColors.textTertiary)
            }
          }
          .padding(28)
        }
        .frame(maxWidth: 560, maxHeight: 280)

        if let snapshot = coordinator.scanSnapshot {
          OnboardingInsightCard(
            icon: "shippingbox.fill",
            title: "Mapped",
            detail: [
              snapshot.projectNames.prefix(3).joined(separator: ", "),
              snapshot.technologies.prefix(3).joined(separator: ", "),
            ]
            .filter { !$0.isEmpty }
            .joined(separator: "  •  ")
          )
          .frame(maxWidth: 560)
        }

        if coordinator.scanSnapshot != nil {
          Button("Continue") {
            onContinue()
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
        } else {
          Text("Scanning your workspace…")
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textTertiary)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await coordinator.startFileScanIfNeeded(appState: appState)
        await graphViewModel.addGraphFromStorage()
      }
    }
  }

  private var scanProgress: Double {
    switch coordinator.scanState {
    case .idle:
      return 0.12
    case .scanning:
      return coordinator.scanSnapshot == nil ? 0.55 : 0.82
    case .complete:
      return 1
    case .failed:
      return 0.2
    }
  }
}

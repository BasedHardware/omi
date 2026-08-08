import OmiTheme
import SwiftUI

struct OnboardingFileScanStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let totalSteps: Int
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: "Discovery",
      title: "Start building your profile.",
      description: "Omi scans projects and recent files.",
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        VStack(spacing: OmiSpacing.xl) {
          OnboardingLoadingAnimation(progress: scanProgress)
            .frame(height: 160)

          Text(coordinator.scanStatusText)
            .font(.system(size: 18, weight: .semibold))
            .foregroundColor(Ink.primary)
            .fixedSize(horizontal: false, vertical: true)

          if let snapshot = coordinator.scanSnapshot {
            Text("\(snapshot.fileCount.formatted()) files indexed")
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
              .monospacedDigit()
          } else {
            Text("Your graph and suggestions will build from this scan.")
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
        .padding(OmiSpacing.xxl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // The card's own recipe, not a second opinion about it: a wash plus a hairline at the one
        // 22 pt corner the panel itself is cut to.
        .glassCard()
        .frame(maxWidth: 560, maxHeight: 280)

        // Gate Continue on the scan reaching a terminal state, not on a non-empty
        // snapshot — a failed scan or a scan that indexed zero files (e.g. Full
        // Disk Access was skipped) leaves `scanSnapshot` nil while `scanState`
        // becomes `.failed`/`.complete`, and gating on the snapshot would trap
        // the user on a perpetual "Scanning…" screen with no way forward.
        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if OnboardingPagedIntroCoordinator.fileScanReachedTerminalState(coordinator.scanState) {
            VStack(alignment: .leading, spacing: OmiSpacing.md) {
              // The consequence copy for a scan that indexed nothing — kept visible, because
              // Continue below is the escape and the user has to know what it costs.
              if let error = coordinator.lastActionError {
                Text(error)
                  .inkStyle(InkType.statusLabel, color: Ink.secondary)
                  .fixedSize(horizontal: false, vertical: true)
              }
              Button("Continue") {
                onContinue()
              }
              .buttonStyle(InkButtonStyle(kind: .primary))
              .keyboardShortcut(.defaultAction)
            }
          } else {
            Text("Scanning your workspace…")
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
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

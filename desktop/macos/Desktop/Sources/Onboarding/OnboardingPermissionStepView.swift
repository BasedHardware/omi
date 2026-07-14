import SwiftUI
import OmiTheme

struct OnboardingPermissionStepView: View {
  @Environment(\.scenePhase) private var scenePhase

  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel

  let stepIndex: Int
  let totalSteps: Int
  let eyebrow: String
  let title: String
  let description: String
  let permissionType: String
  let icon: String
  let reasonTitle: String
  let reasonDetail: String
  let primaryActionLabel: String
  let requiresRestart: Bool
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var isRequesting = false
  @State private var screenRecordingRefreshTask: Task<Void, Never>?
  private let timer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

  var body: some View {
    OnboardingStepScaffold(
      graphViewModel: graphViewModel,
      stepIndex: stepIndex,
      totalSteps: totalSteps,
      eyebrow: eyebrow,
      title: title,
      description: description,
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete
    ) {
      VStack(alignment: .leading, spacing: OmiSpacing.xl) {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          HStack(spacing: OmiSpacing.md) {
            ZStack {
              RoundedRectangle(cornerRadius: OmiChrome.sectionRadius, style: .continuous)
                .fill(OmiColors.backgroundSecondary)
                .frame(width: 58, height: 58)

              Image(systemName: icon)
                .font(.system(size: 24, weight: .semibold))
                .foregroundColor(OmiColors.textSecondary)
            }

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text(reasonTitle)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(OmiColors.textPrimary)

              Text(statusText)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(isGranted ? OmiColors.success : OmiColors.textTertiary)
            }

            Spacer()
          }

          Text(reasonDetail)
            .font(.system(size: 14))
            .foregroundColor(OmiColors.textSecondary)
            .lineSpacing(4)

          if permissionType == "screen_recording", appState.isScreenRecordingStale {
            Text("macOS still isn’t granting screen capture to this build. In Screen & System Audio Recording, toggle Omi Dev off, then on again, then quit and reopen the app.")
              .font(.system(size: 13, weight: .medium))
              .foregroundColor(OmiColors.warning)
              .fixedSize(horizontal: false, vertical: true)
          }

          if permissionType == "full_disk_access", let email = coordinator.userEmail() {
            Text(email)
              .font(.system(size: 13, weight: .medium))
              .foregroundColor(OmiColors.textTertiary)
          }


          if let error = coordinator.lastActionError, !isGranted {
            Text(error)
              .font(.system(size: 12, weight: .medium))
              .foregroundColor(OmiColors.warning)
          }
        }
        .frame(maxWidth: 540, alignment: .leading)

        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if isGranted {
            Button("Continue", action: onContinue)
              .buttonStyle(OmiButtonStyle(.primary))
              .keyboardShortcut(.defaultAction)
          } else {
            Button(isRequesting ? "Waiting for macOS…" : primaryActionLabel) {
              Task {
                isRequesting = true
                _ = await coordinator.requestPermission(permissionType, appState: appState)
                isRequesting = false
                refreshPermissionState()
              }
            }
            .buttonStyle(OmiButtonStyle(.primary))
            .disabled(isRequesting)
          }
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onReceive(timer) { _ in
        refreshPermissionState()
      }
      .onChange(of: scenePhase) { _, newPhase in
        guard newPhase == .active else { return }
        refreshPermissionState()
      }
      .onDisappear {
        screenRecordingRefreshTask?.cancel()
      }
      .onAppear {
        screenRecordingRefreshTask?.cancel()
        coordinator.clearLastActionError()
        refreshPermissionState()
      }
    }
  }

  private var isGranted: Bool {
    coordinator.isPermissionGranted(permissionType, appState: appState)
  }

  private var statusText: String {
    if isGranted {
      return "Granted"
    }
    if isRequesting {
      return "Waiting for macOS..."
    }
    return "Not granted yet"
  }

  private func refreshPermissionState() {
    coordinator.refreshPermissions(appState: appState)

    guard permissionType == "screen_recording", !appState.hasScreenRecordingPermission else {
      return
    }
    guard screenRecordingRefreshTask == nil else { return }

    screenRecordingRefreshTask = Task {
      let granted = await Task.detached(priority: .utility) {
        ScreenCaptureService.checkPermission(forceActualTestIfPreflightDenied: true)
      }.value

      guard !Task.isCancelled else { return }

      appState.hasScreenRecordingPermission = granted
      if granted {
        appState.isScreenRecordingStale = false
        appState.isScreenCaptureKitBroken = false
        appState.screenRecordingGrantAttempts = 0
      }
      screenRecordingRefreshTask = nil
    }
  }
}

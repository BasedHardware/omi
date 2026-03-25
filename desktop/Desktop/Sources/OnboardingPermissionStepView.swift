import SwiftUI

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

  @State private var isRequesting = false
  @State private var hasAutoAdvanced = false
  @State private var advanceTask: Task<Void, Never>?
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
      onSkip: onSkip
    ) {
      VStack(alignment: .leading, spacing: 20) {
        VStack(alignment: .leading, spacing: 18) {
          HStack(spacing: 14) {
            ZStack {
              RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(OmiColors.backgroundSecondary)
                .frame(width: 58, height: 58)

              Image(systemName: icon)
                .font(.system(size: 24, weight: .semibold))
                .foregroundColor(OmiColors.purplePrimary)
            }

            VStack(alignment: .leading, spacing: 4) {
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

          if permissionType == "full_disk_access", let email = coordinator.userEmail() {
            Text(email)
              .font(.system(size: 13, weight: .medium))
              .foregroundColor(OmiColors.textTertiary)
          }

          if requiresRestart {
            Text("macOS may relaunch Omi here. This flow will resume on the same step.")
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

        if isGranted {
          Text("Permission granted. Continuing…")
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(OmiColors.textTertiary)
        } else {
          Button(isRequesting ? "Waiting for macOS…" : primaryActionLabel) {
            Task {
              isRequesting = true
              _ = await coordinator.requestPermission(permissionType, appState: appState)
              isRequesting = false
              refreshPermissionState()
              if isGranted {
                scheduleAutoAdvance()
              }
            }
          }
          .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
          .disabled(isRequesting)

          Text("This page advances automatically as soon as macOS confirms the change.")
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textTertiary)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onReceive(timer) { _ in
        refreshPermissionState()
        if isGranted {
          scheduleAutoAdvance()
        }
      }
      .onChange(of: scenePhase) { _, newPhase in
        guard newPhase == .active else { return }
        refreshPermissionState()
      }
      .onChange(of: isGranted) { _, granted in
        if granted {
          scheduleAutoAdvance()
        }
      }
      .onDisappear {
        advanceTask?.cancel()
        screenRecordingRefreshTask?.cancel()
      }
      .onAppear {
        hasAutoAdvanced = false
        advanceTask?.cancel()
        screenRecordingRefreshTask?.cancel()
        coordinator.clearLastActionError()
        refreshPermissionState()
        if isGranted {
          scheduleAutoAdvance()
        }
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

  private func scheduleAutoAdvance() {
    guard !hasAutoAdvanced else { return }
    hasAutoAdvanced = true
    advanceTask?.cancel()
    advanceTask = Task {
      try? await Task.sleep(nanoseconds: 350_000_000)
      guard !Task.isCancelled else { return }
      await MainActor.run {
        onContinue()
      }
    }
  }

  private func refreshPermissionState() {
    coordinator.refreshPermissions(appState: appState)

    guard permissionType == "screen_recording", !appState.hasScreenRecordingPermission else {
      return
    }
    guard screenRecordingRefreshTask == nil else { return }

    screenRecordingRefreshTask = Task {
      let granted = await Task.detached(priority: .utility) {
        ScreenCaptureService.checkPermission()
      }.value

      guard !Task.isCancelled else { return }

      appState.hasScreenRecordingPermission = granted
      if granted {
        appState.isScreenRecordingStale = false
        appState.isScreenCaptureKitBroken = false
        appState.screenRecordingGrantAttempts = 0
        scheduleAutoAdvance()
      }
      screenRecordingRefreshTask = nil
    }
  }
}

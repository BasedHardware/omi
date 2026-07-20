import Combine
import OmiTheme
import SwiftUI

/// Decides what a permission step does once its permission reads granted.
///
/// A restart-carrying step must only offer "Reopen Omi" for a grant that
/// happened during this app run. When the permission was already granted the
/// moment the step appeared, the restart it needed has already happened (macOS
/// "Quit & Reopen", or our own relaunch) — prompting again would loop the user
/// through endless restarts.
enum OnboardingRestartAdvancePolicy {
  enum Action: Equatable {
    case advance
    case promptRestart
  }

  static func action(requiresRestart: Bool, grantedWhenStepAppeared: Bool) -> Action {
    guard requiresRestart, !grantedWhenStepAppeared else { return .advance }
    return .promptRestart
  }
}

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
  @State private var showReopenPrompt = false
  @State private var hasAutoAdvanced = false
  @State private var grantedWhenStepAppeared = false
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
      onSkip: {
        // Skipping a permission step should also clear the floating drag card.
        PermissionDragGuidance.dismiss()
        onSkip()
      },
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
            Text(
              "macOS still isn’t granting screen capture to this build. In Screen & System Audio Recording, toggle Omi Dev off, then on again, then quit and reopen the app."
            )
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
          .buttonStyle(OmiButtonStyle(.primary))
          .disabled(isRequesting)

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
      .alert("Reopen Omi to finish", isPresented: $showReopenPrompt) {
        Button("Reopen Omi") {
          // Persist the step advance before relaunching, so the app resumes on
          // the next step instead of re-entering this one and prompting again.
          onContinue()
          appState.restartApp()
        }
        Button("Later", role: .cancel) { onContinue() }
      } message: {
        Text("Omi needs to reopen to apply the permissions you just granted.")
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
        grantedWhenStepAppeared = isGranted
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
        // The restart-carrying step (the last drag permission) offers the re-open
        // once granted, instead of silently advancing — one restart applies every
        // deferred grant. Other steps, and a step whose permission was already
        // granted when it appeared (the restart already happened), just continue.
        switch OnboardingRestartAdvancePolicy.action(
          requiresRestart: requiresRestart, grantedWhenStepAppeared: grantedWhenStepAppeared)
        {
        case .promptRestart:
          PermissionDragGuidance.dismiss()
          showReopenPrompt = true
        case .advance:
          if requiresRestart {
            PermissionDragGuidance.dismiss()
          }
          onContinue()
        }
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
        ScreenCaptureService.checkPermission(forceActualTestIfPreflightDenied: true)
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

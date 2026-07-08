import SwiftUI

// MARK: - Permission step (mockup: ob-permissions)  · steps 4,5,7,8,9

/// Benefit-led single-permission screen. All permission wiring, polling, and
/// auto-advance behavior is preserved verbatim from `OnboardingPermissionStepView`.
struct RedesignPermissionStepView: View {
  @Environment(\.scenePhase) private var scenePhase

  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator

  let stepIndex: Int
  let eyebrow: String
  let title: String
  let description: String
  let benefitName: String
  let benefitPayoff: String
  let permissionType: String
  let icon: String
  let primaryActionLabel: String
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var isRequesting = false
  @State private var hasAutoAdvanced = false
  @State private var advanceTask: Task<Void, Never>?
  @State private var screenRecordingRefreshTask: Task<Void, Never>?
  private let timer = Timer.publish(every: 1.0, on: .main, in: .common).autoconnect()

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: eyebrow,
      title: title,
      subtitle: description,
      centeredText: false,
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete,
      maxWidth: 560
    ) {
      VStack(alignment: .leading, spacing: 16) {
        RedesignPermissionCard(
          icon: icon,
          name: benefitName,
          payoff: benefitPayoff,
          granted: isGranted,
          isBusy: isRequesting,
          grantTitle: "Grant"
        ) {
          Task {
            isRequesting = true
            _ = await coordinator.requestPermission(permissionType, appState: appState)
            isRequesting = false
            refreshPermissionState()
            if isGranted { scheduleAutoAdvance() }
          }
        }

        if permissionType == "screen_recording", appState.isScreenRecordingStale {
          Text(
            "macOS still isn't granting screen capture to this build. In Screen & System Audio Recording, toggle Omi Dev off, then on again, then quit and reopen the app."
          )
          .font(InkFont.sans(13, .medium))
          .foregroundColor(Ink.warnText)
          .fixedSize(horizontal: false, vertical: true)
        }

        if permissionType == "full_disk_access", let email = coordinator.userEmail() {
          Text(email).font(InkFont.sans(13, .medium)).foregroundColor(Ink.faint)
        }

        if let error = coordinator.lastActionError, !isGranted {
          RedesignOnboardingError(message: error)
        }

        if isGranted {
          Text("Granted. Continuing…").font(InkFont.sans(13, .medium)).foregroundColor(Ink.muted)
        } else {
          HStack(spacing: 7) {
            Image(systemName: "hand.raised").font(.system(size: 11)).foregroundColor(Ink.faint)
            Text("I ask for this once. You can revoke it anytime.")
              .font(InkFont.sans(12)).foregroundColor(Ink.faint)
          }
          .padding(.top, 2)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onReceive(timer) { _ in
        refreshPermissionState()
        if isGranted { scheduleAutoAdvance() }
      }
      .onChange(of: scenePhase) { _, newPhase in
        guard newPhase == .active else { return }
        refreshPermissionState()
      }
      .onChange(of: isGranted) { _, granted in
        if granted { scheduleAutoAdvance() }
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
        if isGranted { scheduleAutoAdvance() }
      }
    }
  }

  private var isGranted: Bool {
    coordinator.isPermissionGranted(permissionType, appState: appState)
  }

  private func scheduleAutoAdvance() {
    guard !hasAutoAdvanced else { return }
    hasAutoAdvanced = true
    advanceTask?.cancel()
    advanceTask = Task {
      try? await Task.sleep(nanoseconds: 350_000_000)
      guard !Task.isCancelled else { return }
      await MainActor.run { onContinue() }
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

// MARK: - File scan (mockup: ob-import intro)  · step 6

struct RedesignFileScanStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: "Reading your last 30 days",
      title: "Let me get to know\nyour work.",
      subtitle: "I'm scanning your projects and recent files to build your second brain.",
      showsBuddy: true,
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete
    ) {
      VStack(spacing: 22) {
        InkCard(padding: 28, radius: 18) {
          VStack(spacing: 18) {
            OnboardingLoadingAnimation(progress: scanProgress)
              .frame(height: 130)

            Text(coordinator.scanStatusText)
              .font(InkFont.sans(16, .semibold))
              .foregroundColor(Ink.ink)
              .multilineTextAlignment(.center)

            if let snapshot = coordinator.scanSnapshot {
              Text("\(snapshot.fileCount.formatted()) files indexed")
                .font(InkFont.mono(13))
                .foregroundColor(Ink.faint)
            } else {
              Text("Your graph and suggestions build from this scan.")
                .font(InkFont.sans(13))
                .foregroundColor(Ink.faint)
            }
          }
          .frame(maxWidth: .infinity)
        }
        .frame(maxWidth: 460)

        if coordinator.scanSnapshot != nil {
          InkButton(title: "This is wild — keep going", kind: .primary, size: .lg) { onContinue() }
        } else {
          HStack(spacing: 8) {
            ProgressView().controlSize(.small).tint(Ink.faint)
            Text("Scanning your workspace…").font(InkFont.sans(13)).foregroundColor(Ink.faint)
          }
        }
      }
      .frame(maxWidth: .infinity, alignment: .center)
      .task {
        await coordinator.startFileScanIfNeeded(appState: appState)
        await graphViewModel.addGraphFromStorage()
      }
    }
  }

  private var scanProgress: Double {
    switch coordinator.scanState {
    case .idle: return 0.12
    case .scanning: return coordinator.scanSnapshot == nil ? 0.55 : 0.82
    case .complete: return 1
    case .failed: return 0.2
    }
  }
}

import OmiTheme
import SwiftUI

/// Persistent Capture + Listening status controls for the shell top bar, shown
/// on every non-home page (the home screen renders its own column-aligned copy
/// via `DashboardPage.homeHeader`). Hovering Capture reveals a Rewind shortcut
/// beneath it.
///
/// The toggle logic mirrors `DashboardPage`'s and drives the same shared
/// singletons (`AssistantSettings`, `ProactiveAssistantsPlugin`, `AppState`), so
/// both surfaces stay consistent. Keep the two copies in sync until they are
/// unified behind one controller.
struct CaptureListeningControls: View {
  @ObservedObject var appState: AppState
  var onRewind: () -> Void

  @State private var isCaptureMonitoring = false
  @State private var isTogglingCapture = false
  @State private var isTogglingListening = false
  @State private var hoverCapture = false
  @State private var hoverRewind = false

  @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
  @AppStorage("transcriptionEnabled") private var transcriptionEnabled = true
  @AppStorage("systemAudioCaptureMode") private var systemAudioCaptureModeRaw =
    AssistantSettings.SystemAudioCaptureMode.onlyDuringMeetings.rawValue

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      captureButton

      HomeListeningStatusButton(
        title: transcriptionUnavailable ? "Transcription unavailable" : "Listening",
        systemImage: transcriptionUnavailable
          ? "exclamationmark.triangle.fill"
          : (appState.isTranscribing ? "waveform.circle.fill" : "mic.circle"),
        status: transcriptionUnavailable ? .blocked : (appState.isTranscribing ? .active : .inactive),
        modeTitle: listeningModeTitle,
        isMeetingsOnly: listeningCaptureMode == .onlyDuringMeetings,
        isToggling: isTogglingListening,
        action: toggleListening,
        modeAction: toggleListeningMode
      )
    }
    .onAppear(perform: syncCaptureState)
    .onReceive(NotificationCenter.default.publisher(for: .screenCapturePermissionLost)) { _ in
      syncCaptureState()
    }
    .onReceive(NotificationCenter.default.publisher(for: .screenCaptureKitBroken)) { _ in
      syncCaptureState()
    }
  }

  private var transcriptionUnavailable: Bool { appState.transcriptionServiceError != nil }

  // MARK: Capture button + hover Rewind affordance

  private var captureButton: some View {
    HomeStatusButton(
      title: "Capture",
      systemImage: "viewfinder",
      status: captureStatus,
      isToggling: isTogglingCapture,
      action: toggleCapture
    )
    .onHover { hoverCapture = $0 }
    .overlay(alignment: .top) {
      if hoverCapture || hoverRewind {
        rewindChip
          .offset(y: 34)
          .transition(.opacity)
      }
    }
    .omiAnimation(.easeOut(duration: 0.12), value: hoverCapture || hoverRewind)
  }

  private var rewindChip: some View {
    // A small transparent bridge on top keeps the chip open while the cursor
    // travels down from the Capture pill into it.
    VStack(spacing: 0) {
      Color.clear.frame(height: 6)
      Button(action: onRewind) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "clock.arrow.circlepath")
            .scaledFont(size: OmiType.caption, weight: .semibold)
          Text("Rewind")
            .scaledFont(size: OmiType.caption, weight: .semibold)
        }
        .foregroundStyle(OmiColors.textPrimary)
        .padding(.horizontal, OmiSpacing.md)
        .frame(height: 30)
        .background(Capsule(style: .continuous).fill(OmiColors.backgroundTertiary))
        .overlay(Capsule(style: .continuous).stroke(OmiColors.textPrimary.opacity(0.12), lineWidth: 1))
        .contentShape(Capsule())
      }
      .buttonStyle(.plain)
      .help("Open Rewind")
      .accessibilityLabel("Open Rewind")
    }
    .onHover { hoverRewind = $0 }
    .fixedSize()
  }

  // MARK: Derived state (mirrors DashboardPage)

  private var captureStatus: HomeStatusState {
    CaptureListeningLogic.captureStatus(appState: appState, isCaptureMonitoring: isCaptureMonitoring)
  }

  private var isCaptureLive: Bool {
    CaptureListeningLogic.isCaptureLive(isCaptureMonitoring: isCaptureMonitoring)
  }

  private var listeningCaptureMode: AssistantSettings.SystemAudioCaptureMode {
    CaptureListeningLogic.listeningCaptureMode(raw: systemAudioCaptureModeRaw)
  }

  private var listeningModeTitle: String {
    CaptureListeningLogic.listeningModeTitle(appState: appState, raw: systemAudioCaptureModeRaw)
  }

  // MARK: Actions (shared with DashboardPage via CaptureListeningLogic)

  private func toggleListening() {
    CaptureListeningLogic.toggleListening(
      appState: appState, transcriptionEnabled: $transcriptionEnabled, isTogglingListening: $isTogglingListening)
  }

  private func toggleListeningMode() {
    CaptureListeningLogic.toggleListeningMode(raw: $systemAudioCaptureModeRaw)
  }

  private func toggleCapture() {
    CaptureListeningLogic.toggleCapture(
      appState: appState, screenAnalysisEnabled: $screenAnalysisEnabled,
      isCaptureMonitoring: $isCaptureMonitoring, isTogglingCapture: $isTogglingCapture)
  }

  private func syncCaptureState() {
    CaptureListeningLogic.syncCaptureState(
      screenAnalysisEnabled: $screenAnalysisEnabled, isCaptureMonitoring: $isCaptureMonitoring)
  }
}

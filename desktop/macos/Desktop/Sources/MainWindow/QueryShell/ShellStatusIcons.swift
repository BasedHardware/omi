//
//  ShellStatusIcons.swift — the top bar's right cluster: microphone, screen capture, settings.
//
//  **Icons only, no words.** The old cluster spelled out `Listening` and `Capture` as filled pills,
//  which is two paragraphs of chrome permanently occupying the corner of a window whose whole point is
//  the search field in the middle of it. The two things a label was carrying are carried instead by
//  the two cues an icon can hold without spending any width: a **state dot**, which says on / off /
//  needs-attention at a glance, and a **tooltip**, which says the whole sentence to anyone who asks.
//
//  A wordless control has to be legible without its label, so the dot is not optional and it is not
//  decorative. Every button here is on when its dot is green, off when the dot is faint, and blocked
//  when the dot is the error colour — one vocabulary across all of them, which is what makes the
//  cluster readable at all.
//
//  It drives `CaptureListeningLogic` — the same functions the old pills and Home's header call — so
//  this is a second *rendering* of the capture state and never a second copy of the behaviour.
//
//  Brand: `Ink` semantics and system colours only (INV-UI-1).
//

import OmiTheme
import SwiftUI

// MARK: - The dot

/// The live-state dot on a wordless control.
///
/// Sized and ringed so it stays readable where it actually lands: over a glyph, on translucent glass,
/// at the corner of a 32 pt target. The ring is the panel's own ground rather than a grey, so the dot
/// separates from whatever the icon is drawn on without introducing a colour.
struct ShellStatusDot: View {
  let state: HomeStatusState

  /// The whole vocabulary of a wordless control, as a function rather than a `switch` inside a
  /// `body`: three states must land on three *distinguishable* fills, and "off" must never resolve
  /// to something a glance reads as "on". That is a claim a test can hold only if it can call this.
  static func fill(for state: HomeStatusState) -> Color {
    switch state {
    case .active: return Ink.listeningGreen
    case .inactive: return Ink.primary.opacity(0.28)
    case .blocked: return Ink.errorRed
    }
  }

  var body: some View {
    Circle()
      .fill(Self.fill(for: state))
      .frame(width: 6.5, height: 6.5)
      .overlay(Circle().strokeBorder(Ink.surface.opacity(0.9), lineWidth: 1.5))
      .frame(width: 9.5, height: 9.5)
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: state)
  }
}

// MARK: - The button

/// One wordless control: a glyph, its state dot, and the sentence the dot is short for.
struct ShellStatusIconButton: View {
  let systemImage: String
  /// The whole sentence, shown on hover and read by VoiceOver. Never abbreviated — this is the only
  /// place the removed label still exists.
  let tooltip: String
  let state: HomeStatusState
  var isBusy: Bool = false
  /// Settings has no live state of its own; passing `false` drops the dot entirely rather than
  /// drawing a permanently faint one, which would read as "off".
  var showsDot: Bool = true
  var isSelected: Bool = false
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Group {
        if isBusy {
          ProgressView().controlSize(.small)
        } else {
          Image(systemName: systemImage)
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
      }
      .overlay(alignment: .topTrailing) {
        if showsDot {
          ShellStatusDot(state: state).offset(x: 6, y: -5)
        }
      }
    }
    .buttonStyle(GlassIconButtonStyle(isActive: isSelected || state == .active))
    .help(tooltip)
    .accessibilityLabel(Text(tooltip))
    .accessibilityAddTraits(state == .active ? .isSelected : [])
  }
}

// MARK: - The cluster

/// Microphone and screen capture — the two live-state controls of the top bar's right cluster.
///
/// The settings gear sits beside them but is deliberately *not* in here: it is navigation, not
/// capture, and `TopNavigationBarLayout` pins it to the lane's trailing edge as its own slot so the
/// two capture icons can shrink and reflow without the way out of the page moving.
struct ShellStatusIcons: View {
  @ObservedObject var appState: AppState

  @State private var isCaptureMonitoring = false
  @State private var isTogglingCapture = false
  @State private var isTogglingListening = false

  @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true
  @AppStorage("transcriptionEnabled") private var transcriptionEnabled = true
  @AppStorage("systemAudioCaptureMode") private var systemAudioCaptureModeRaw =
    AssistantSettings.SystemAudioCaptureMode.onlyDuringMeetings.rawValue

  var body: some View {
    HStack(spacing: 2) {
      ShellStatusIconButton(
        systemImage: listeningGlyph,
        tooltip: listeningTooltip,
        state: listeningState,
        isBusy: isTogglingListening,
        action: toggleListening
      )
      .accessibilityIdentifier("shell-status-listening")

      ShellStatusIconButton(
        systemImage: "rectangle.inset.filled.and.person.filled",
        tooltip: captureTooltip,
        state: captureState,
        isBusy: isTogglingCapture,
        action: toggleCapture
      )
      .accessibilityIdentifier("shell-status-capture")
    }
    .onAppear(perform: syncCaptureState)
    .onReceive(NotificationCenter.default.publisher(for: .screenCapturePermissionLost)) { _ in
      syncCaptureState()
    }
    .onReceive(NotificationCenter.default.publisher(for: .screenCaptureKitBroken)) { _ in
      syncCaptureState()
    }
  }

  // MARK: Derived state

  private var transcriptionUnavailable: Bool { appState.transcriptionServiceError != nil }

  private var listeningState: HomeStatusState {
    if transcriptionUnavailable { return .blocked }
    return appState.isTranscribing ? .active : .inactive
  }

  private var listeningGlyph: String {
    if transcriptionUnavailable { return "mic.slash" }
    return appState.isTranscribing ? "waveform" : "mic"
  }

  /// The sentence the dot is short for. It names the *mode* as well as the state, because "listening"
  /// with no qualifier is the claim the meetings-only mode does not actually make.
  private var listeningTooltip: String {
    if transcriptionUnavailable {
      return "Transcription unavailable — open Settings to reconnect"
    }
    let mode = CaptureListeningLogic.listeningModeTitle(
      appState: appState, raw: systemAudioCaptureModeRaw)
    return appState.isTranscribing
      ? "Listening — \(mode). Click to stop."
      : "Not listening. Click to start."
  }

  private var captureState: HomeStatusState {
    CaptureListeningLogic.captureStatus(appState: appState, isCaptureMonitoring: isCaptureMonitoring)
  }

  private var captureTooltip: String {
    switch captureState {
    case .blocked:
      return "Screen capture needs permission — click to grant it"
    case .active:
      return "Capturing your screen — Rewind is recording. Click to stop."
    case .inactive:
      return "Screen capture is off — nothing is being recorded. Click to start."
    }
  }

  // MARK: Actions — the shared logic, never a second copy

  private func toggleListening() {
    OmiUISound.play(appState.isTranscribing ? .captureEnd : .captureStart)
    CaptureListeningLogic.toggleListening(
      appState: appState,
      transcriptionEnabled: $transcriptionEnabled,
      isTogglingListening: $isTogglingListening)
  }

  private func toggleCapture() {
    OmiUISound.play(captureState == .active ? .captureEnd : .captureStart)
    CaptureListeningLogic.toggleCapture(
      appState: appState, screenAnalysisEnabled: $screenAnalysisEnabled,
      isCaptureMonitoring: $isCaptureMonitoring, isTogglingCapture: $isTogglingCapture)
  }

  private func syncCaptureState() {
    CaptureListeningLogic.syncCaptureState(
      screenAnalysisEnabled: $screenAnalysisEnabled, isCaptureMonitoring: $isCaptureMonitoring)
  }
}

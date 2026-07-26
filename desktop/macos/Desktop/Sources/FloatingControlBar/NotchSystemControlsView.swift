import AppKit
import OmiTheme
import SwiftUI

/// The control cluster revealed on the trailing side of the notch hover surface.
///
/// Shows what Omi is looking at right now and lets the user cut its two inputs — screen
/// and audio — without going to the menu bar. Those are the same two toggles the status
/// item owns; both surfaces route through `SystemCaptureControls` so the paywall and
/// permission gates cannot drift between them.
struct NotchSystemControlsView: View {
  let progress: CGFloat

  @ObservedObject private var focusStorage = FocusStorage.shared
  /// Toggle state lives in UserDefaults and plugin state rather than in an observable, so
  /// it is sampled when the surface opens and after each toggle instead of being bound.
  @State private var screenCaptureOn = false
  @State private var audioRecordingOn = false

  private var currentAppName: String? {
    let name = focusStorage.detectedAppName ?? focusStorage.currentApp
    guard let name, !name.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
    return name
  }

  var body: some View {
    VStack(alignment: .trailing, spacing: OmiSpacing.xs) {
      if let currentAppName {
        currentAppRow(currentAppName)
      }

      HStack(spacing: OmiSpacing.xs) {
        controlButton(
          icon: "rectangle.dashed.badge.record",
          label: "Screen",
          isOn: screenCaptureOn,
          action: toggleScreenCapture
        )
        controlButton(
          icon: "mic.fill",
          label: "Audio",
          isOn: audioRecordingOn,
          action: toggleAudioRecording
        )
      }
    }
    .opacity(progress)
    .allowsHitTesting(progress > 0.6)
    .onAppear(perform: refresh)
    .onChange(of: progress) { _, newValue in
      // Re-sample when the surface opens: the menu bar or Settings may have changed
      // either toggle while the notch was collapsed.
      if newValue > 0.6 { refresh() }
    }
  }

  /// What Omi is currently looking at. This is the same frontmost-app signal the capture
  /// loop uses, so the notch and the assistants can never disagree about the active app.
  private func currentAppRow(_ name: String) -> some View {
    HStack(spacing: OmiSpacing.xxs) {
      Circle()
        .fill(screenCaptureOn ? Color.white.opacity(0.55) : Color.white.opacity(0.22))
        .frame(width: 5, height: 5)
      Text(name)
        .scaledFont(size: OmiType.micro, weight: .medium)
        .foregroundColor(.white.opacity(0.62))
        .lineLimit(1)
        .truncationMode(.tail)
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel(screenCaptureOn ? "Omi is watching \(name)" : "Omi is not watching \(name)")
  }

  private func controlButton(icon: String, label: String, isOn: Bool, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: icon)
          .font(.system(size: 9, weight: .semibold))
        Text(label)
          .scaledFont(size: OmiType.micro, weight: .semibold)
      }
      .foregroundColor(isOn ? .white : .white.opacity(0.45))
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xxs)
      .background(
        Capsule().fill(isOn ? Color.white.opacity(0.18) : Color.white.opacity(0.08))
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .accessibilityLabel("\(label) capture")
    .accessibilityValue(isOn ? "On" : "Off")
    .accessibilityHint("Toggles whether Omi captures \(label.lowercased())")
    .help("\(label) capture is \(isOn ? "on" : "off")")
  }

  // MARK: - Actions

  private func refresh() {
    screenCaptureOn = SystemCaptureControls.isScreenCaptureOn
    audioRecordingOn = SystemCaptureControls.isAudioRecordingOn
  }

  private func toggleScreenCapture() {
    // Reflect the outcome, not the request: a refused enable (paywall, missing Screen
    // Recording permission) must leave the control reading OFF.
    let outcome = SystemCaptureControls.setScreenCapture(!screenCaptureOn) { started in
      screenCaptureOn = started && SystemCaptureControls.isScreenCaptureOn
    }
    screenCaptureOn = outcome.resultingIsOn
  }

  private func toggleAudioRecording() {
    let outcome = SystemCaptureControls.setAudioRecording(!audioRecordingOn)
    audioRecordingOn = outcome.resultingIsOn
  }
}

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
  @ObservedObject private var shortcuts = ShortcutSettings.shared
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

      shortcutLegend

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
        .fill(screenCaptureOn ? NotchGlass.ink(.w55) : NotchGlass.ink(.w25))
        .frame(width: 5, height: 5)
      Text(name)
        .scaledFont(size: OmiType.micro, weight: .medium)
        .foregroundColor(NotchGlass.secondary)
        .lineLimit(1)
        .truncationMode(.tail)
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel(screenCaptureOn ? "Omi is watching \(name)" : "Omi is not watching \(name)")
  }

  // MARK: - Shortcut legend

  /// What you can say/press and the keys that do it. Read-only by design: this is a
  /// legend, not a second route into chat or settings — the duplicate entry points that
  /// used to live here were removed for exactly that reason (FC-split-mutation-authority).
  private var shortcutLegend: some View {
    // One row per configurable shortcut, named the way Settings advertises it
    // ("Open Omi Shortcut"). The fixed window-summon chord is deliberately not
    // listed: two near-identical "open" rows read as a bug, not a feature.
    VStack(alignment: .trailing, spacing: 3) {
      if shortcuts.pttEnabled {
        shortcutRow("Talk", keys: shortcuts.pttShortcut.displayTokens)
      }
      if shortcuts.askOmiEnabled {
        shortcutRow("Open", keys: shortcuts.askOmiShortcut.displayTokens)
      }
    }
    .accessibilityElement(children: .contain)
    .accessibilityLabel("Keyboard shortcuts")
  }

  private func shortcutRow(_ title: String, keys: [String]) -> some View {
    HStack(spacing: 3) {
      Text(title)
        .scaledFont(size: 8, weight: .semibold)
        .foregroundStyle(NotchGlass.ink(.w55))
      shortcutKeys(keys)
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel("\(title): \(keys.joined(separator: " "))")
  }

  private func shortcutKeys(_ keys: [String]) -> some View {
    ForEach(ShortcutHintLayout.visibleTokens(for: keys), id: \.self) { key in
      Text(key)
        .scaledFont(size: 8, weight: .medium)
        .foregroundStyle(NotchGlass.ink(.w75))
        .lineLimit(1)
        .minimumScaleFactor(0.7)
        .padding(.horizontal, key.count > 1 ? 3 : 0)
        .frame(minWidth: 12, minHeight: 12)
        .background(NotchGlass.fillHover)
        .cornerRadius(OmiChrome.stripRadius)
    }
    .fixedSize(horizontal: true, vertical: false)
  }

  private func controlButton(icon: String, label: String, isOn: Bool, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: icon)
          .font(.system(size: 9, weight: .semibold))
        Text(label)
          .scaledFont(size: OmiType.micro, weight: .semibold)
      }
      .foregroundColor(NotchGlass.controlLabel(isActive: isOn))
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xxs)
      .background(
        Capsule().fill(NotchGlass.controlFill(isActive: isOn, isHovering: false))
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

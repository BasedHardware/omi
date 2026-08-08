import OmiTheme
import SwiftUI

/// Onboarding step: configure and test the floating bar shortcut.
/// Only detects the keypress and does not open the floating bar.
struct OnboardingFloatingBarShortcutStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var stepIndex: Int
  var totalSteps: Int
  var onComplete: () -> Void
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?

  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var shortcutDetected = false
  @State private var showContinue = false
  @State private var isRecordingCustomShortcut = false
  @State private var captureError: String?
  @State private var localKeyMonitor: Any?
  @State private var globalKeyMonitor: Any?
  /// Shortcut tokens (e.g. "⌘", "O") currently held down, so their keycaps
  /// light up while pressed and turn off on release.
  @State private var pressedTokens: Set<String> = []
  @State private var mainKeyDown = false

  /// Stashed main menu so we can restore it when leaving this step.
  static var savedMenu: NSMenu?

  var body: some View {
    VStack(spacing: 0) {
      HStack {
        OnboardingLogoMark(onForceComplete: onForceComplete)

        Spacer()

        Button(action: onSkip) {
          Text("Skip")
            .font(.system(size: 13))
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.vertical, OmiSpacing.lg)

      GlassSeparator()

      OnboardingProgressBar(stepIndex: stepIndex, totalSteps: totalSteps)
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.top, OmiSpacing.xl)

      OnboardingContentWithPinnedActions {
        VStack(spacing: OmiSpacing.xxl) {
          Text("Let's set the \"Open Omi\" shortcut.\nPress this shortcut. Do the buttons light up?")
            .inkStyle(InkType.stepHeadline, color: Ink.primary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)

          shortcutKeyPreview
            .frame(height: 152)
            .frame(maxWidth: 480)
            .glassCard()

          VStack(spacing: OmiSpacing.md) {
            Text("Choose a different shortcut:")
              .font(.system(size: 14, weight: .medium))
              .foregroundColor(Ink.secondary)

            LazyVGrid(
              columns: [GridItem(.adaptive(minimum: 92), spacing: OmiSpacing.sm)],
              alignment: .center,
              spacing: OmiSpacing.sm
            ) {
              ForEach(ShortcutSettings.askOmiPresets, id: \.self) { shortcut in
                shortcutChoiceButton(shortcut)
              }
              customShortcutButton
            }

            if isRecordingCustomShortcut || shortcutSettings.askOmiUsesCustomShortcut || captureError != nil {
              customShortcutRecorder
            }
          }

        }
        .frame(maxWidth: 480)
      } actions: {
        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if showContinue {
            Button(action: onComplete) {
              Text("Continue")
            }
            .buttonStyle(InkButtonStyle(kind: .primary))
            .keyboardShortcut(.defaultAction)
            .transition(.move(edge: .bottom).combined(with: .opacity))
          }
        }
        .frame(maxWidth: 480)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      GlobalShortcutManager.shared.setRegistrationSuspended(true)
      installKeyMonitor()
    }
    .onDisappear {
      removeKeyMonitors()
      GlobalShortcutManager.shared.setRegistrationSuspended(false)
    }
  }

  private var shortcutKeyPreview: some View {
    VStack(spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.sm) {
        ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { _, symbol in
          OnboardingKeyCapView(
            token: symbol,
            isActive: shortcutDetected || pressedTokens.contains(symbol)
          )
        }
      }

      Text(shortcutDetected ? "Shortcut detected" : "Press to test")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
    }
  }

  private var customShortcutButton: some View {
    let isSelected = shortcutSettings.askOmiUsesCustomShortcut || isRecordingCustomShortcut
    return Button(action: beginCustomShortcutCapture) {
      Text("Custom")
        .font(.system(size: 14, weight: .medium))
        .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.md)
        .glassChip(isActive: isSelected)
    }
    .buttonStyle(.plain)
  }

  private var customShortcutRecorder: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(isRecordingCustomShortcut ? "Press your custom shortcut now" : "Custom shortcut")
        .font(.system(size: 13, weight: .semibold))
        .foregroundColor(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      HStack(spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.xs) {
          ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
            smallKeyCap(token, active: true)
          }
        }

        Spacer()

        Button(action: handleCustomShortcutSaveButton) {
          Text(isRecordingCustomShortcut ? "Listening..." : "Save")
        }
        .buttonStyle(InkButtonStyle(kind: .secondary))
        .disabled(isRecordingCustomShortcut)
      }

      Text("Use at least one non-modifier key, like J or Return.")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)

      if let captureError {
        Text(captureError)
          .inkStyle(InkType.statusLabel, color: Ink.errorRed)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: 420)
    .glassCard()
  }

  /// A keycap on glass: a wash with a hairline outline, inverting to an `Ink.primary` fill with an
  /// `Ink.surface` glyph while the key is held.
  private func smallKeyCap(_ label: String, active: Bool) -> some View {
    RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
      .fill(active ? Ink.primary : Ink.rowFill)
      .frame(minWidth: 36, minHeight: 32)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
          .strokeBorder(active ? Color.clear : Ink.hairline, lineWidth: 1)
      )
      .overlay {
        Text(label)
          .font(.system(size: 13, weight: .semibold))
          .foregroundColor(active ? Ink.surface : Ink.primary)
          .padding(.horizontal, label.count > 2 ? 10 : 8)
      }
      .fixedSize()
  }

  private func shortcutChoiceButton(_ shortcut: ShortcutSettings.KeyboardShortcut) -> some View {
    let isSelected = shortcutSettings.askOmiShortcut == shortcut && !shortcutSettings.askOmiUsesCustomShortcut
    return Button {
      Self.selectPreset(shortcut, settings: shortcutSettings)
      isRecordingCustomShortcut = false
      captureError = nil
      resetDetectionState()
    } label: {
      HStack(spacing: OmiSpacing.xxs) {
        ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, symbol in
          Text(symbol)
            .font(.system(size: 13, weight: .medium))
        }
      }
      .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .glassChip(isActive: isSelected)
    }
    .buttonStyle(.plain)
  }

  static func selectPreset(_ shortcut: ShortcutSettings.KeyboardShortcut, settings: ShortcutSettings) {
    settings.askOmiShortcut = shortcut
  }

  private func beginCustomShortcutCapture() {
    isRecordingCustomShortcut = true
    captureError = nil
    resetDetectionState()
  }

  private func handleCustomShortcutSaveButton() {
    guard shortcutSettings.askOmiUsesCustomShortcut else {
      beginCustomShortcutCapture()
      return
    }
    confirmShortcutAndContinue()
  }

  private func resetDetectionState() {
    shortcutDetected = false
    showContinue = false
    pressedTokens = []
    mainKeyDown = false
  }

  private func confirmShortcutAndContinue() {
    captureError = nil
    shortcutDetected = true
    OmiMotion.withGated(.easeInOut(duration: 0.3)) {
      showContinue = true
    }
  }

  private func installKeyMonitor() {
    // .keyUp included so held keycaps can turn back off.
    let mask: NSEvent.EventTypeMask = [.keyDown, .keyUp, .flagsChanged]
    localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { event in
      updatePressedTokens(from: event)
      return handleShortcutEvent(event) ? nil : event
    }
    globalKeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { event in
      updatePressedTokens(from: event)
      _ = handleShortcutEvent(event)
    }

    // Strip the main menu immediately so the first keypress can't be swallowed
    // by NSMenu key equivalents before our monitor sees it.
    if Self.savedMenu == nil {
      Self.savedMenu = NSApp.mainMenu
    }
    NSApp.mainMenu = nil
  }

  private func removeKeyMonitors() {
    if let monitor = localKeyMonitor {
      NSEvent.removeMonitor(monitor)
      localKeyMonitor = nil
    }
    if let monitor = globalKeyMonitor {
      NSEvent.removeMonitor(monitor)
      globalKeyMonitor = nil
    }
    if let menu = Self.savedMenu {
      NSApp.mainMenu = menu
      Self.savedMenu = nil
    }
    pressedTokens = []
    mainKeyDown = false
  }

  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    if isRecordingCustomShortcut {
      return captureCustomShortcut(from: event)
    }

    guard !shortcutDetected else { return false }
    guard shortcutSettings.askOmiShortcut.matchesKeyDown(event) else { return false }

    DispatchQueue.main.async {
      confirmShortcutAndContinue()
    }
    return true
  }

  private func captureCustomShortcut(from event: NSEvent) -> Bool {
    if event.type == .flagsChanged {
      captureError = "Open Omi needs a non-modifier key."
      return true
    }

    guard let shortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(event, allowModifierOnly: false) else {
      return false
    }

    shortcutSettings.askOmiShortcut = shortcut
    isRecordingCustomShortcut = false
    captureError = nil
    return true
  }

  /// Watches modifier + key events so the on-screen keycaps light up while the
  /// matching key is physically held and turn off on release. Mirrors the
  /// floating-bar demo step.
  private func updatePressedTokens(from event: NSEvent) {
    let shortcut = shortcutSettings.askOmiShortcut
    // Held modifiers, derived live from the event's flags.
    let liveFlags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
    var tokens = Set(ShortcutSettings.KeyboardShortcut.modifierTokens(for: liveFlags))

    // The non-modifier key (e.g. "O", "↩"): track its own down/up.
    if let keyCode = shortcut.keyCode, let keyDisplay = shortcut.keyDisplay {
      switch event.type {
      case .keyDown where event.keyCode == keyCode:
        mainKeyDown = true
      case .keyUp where event.keyCode == keyCode:
        mainKeyDown = false
      default:
        break
      }
      if mainKeyDown {
        tokens.insert(keyDisplay)
      }
    }

    // Only light caps that belong to this shortcut.
    pressedTokens = tokens.intersection(Set(shortcut.displayTokens))
  }
}

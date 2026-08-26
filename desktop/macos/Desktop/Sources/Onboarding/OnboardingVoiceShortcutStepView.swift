import OmiTheme
import SwiftUI

/// Onboarding step: verify the push-to-talk shortcut without opening the voice bar.
struct OnboardingVoiceShortcutStepView: View {
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
  @State private var pendingModifierOnlyShortcut: ShortcutSettings.KeyboardShortcut?
  @State private var localKeyMonitor: Any?
  @State private var globalKeyMonitor: Any?

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
          Text("Let's set \"Audio ask a question\" shortcut.\nPress and hold to test. Does the button light up?")
            .inkStyle(InkType.stepHeadline, color: Ink.primary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)

          shortcutKeyPreview
            .frame(height: 128)
            .frame(maxWidth: 420)
            .glassCard()

          VStack(spacing: OmiSpacing.md) {
            Text("Try another shortcut if it doesn't react:")
              .font(.system(size: 14, weight: .medium))
              .foregroundColor(Ink.secondary)

            LazyVGrid(
              columns: [GridItem(.adaptive(minimum: 92), spacing: OmiSpacing.sm)],
              alignment: .center,
              spacing: OmiSpacing.sm
            ) {
              ForEach(ShortcutSettings.pttPresets, id: \.self) { shortcut in
                shortcutChoiceButton(shortcut)
              }
              customShortcutButton
            }

            if isRecordingCustomShortcut || shortcutSettings.pttUsesCustomShortcut || captureError != nil {
              customShortcutRecorder
            }
          }

        }
        .frame(maxWidth: 420)
      } actions: {
        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if showContinue {
            Button(action: onComplete) {
              Text("Continue")
            }
            .buttonStyle(InkButtonStyle(kind: .primary))
            .keyboardShortcut(.defaultAction)
            .transition(.move(edge: .trailing).combined(with: .opacity))
          }
        }
        .frame(maxWidth: 420)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      FloatingControlBarManager.shared.barState?.switchAIDraft(to: .onboardingFloating)
      resetFloatingBarConversation()
      FloatingControlBarManager.shared.hideForOnboardingDemo()
      PushToTalkManager.shared.cleanup()
      installKeyMonitor()
    }
    .onDisappear {
      removeKeyMonitors()
    }
  }

  private func resetFloatingBarConversation() {
    guard let barState = FloatingControlBarManager.shared.barState else { return }
    barState.showingAIConversation = false
    barState.showingAIResponse = false
    barState.aiInputText = ""
    barState.clearViewport()
  }

  private var shortcutKeyPreview: some View {
    VStack(spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.sm) {
        ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
          keyCap(token)
        }
      }

      Text(shortcutDetected ? "Shortcut detected" : "Press and hold to test")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
    }
  }

  private var customShortcutButton: some View {
    let isSelected = shortcutSettings.pttUsesCustomShortcut || isRecordingCustomShortcut
    return Button(action: beginCustomShortcutCapture) {
      Text("Custom")
        .font(.system(size: 13, weight: .medium))
        .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .glassChip(isActive: isSelected)
    }
    .buttonStyle(.plain)
  }

  private var customShortcutRecorder: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(isRecordingCustomShortcut ? "Press and hold your custom shortcut now" : "Custom shortcut")
        .font(.system(size: 13, weight: .semibold))
        .foregroundColor(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      HStack(spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.xs) {
          ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
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

      Text("Use a modifier key or a combination like ⌘ J.")
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
  /// `Ink.surface` glyph once the shortcut lands.
  private func keyCap(_ label: String) -> some View {
    RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
      .fill(shortcutDetected ? Ink.primary : Ink.rowFill)
      .frame(minWidth: 48, minHeight: 48)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
          .strokeBorder(shortcutDetected ? Color.clear : Ink.hairline, lineWidth: 1)
      )
      .overlay {
        Text(label)
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(shortcutDetected ? Ink.surface : Ink.primary)
          .padding(.horizontal, label.count > 2 ? 14 : 10)
      }
      .fixedSize()
  }

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
    let isSelected = shortcutSettings.pttShortcut == shortcut && !shortcutSettings.pttUsesCustomShortcut
    return Button {
      Self.selectPreset(shortcut, settings: shortcutSettings)
      isRecordingCustomShortcut = false
      captureError = nil
      resetDetectionState()
    } label: {
      HStack(spacing: OmiSpacing.xs) {
        ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, token in
          Text(token)
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
    settings.pttShortcut = shortcut
  }

  private func beginCustomShortcutCapture() {
    isRecordingCustomShortcut = true
    captureError = nil
    pendingModifierOnlyShortcut = nil
    resetDetectionState()
  }

  private func handleCustomShortcutSaveButton() {
    guard shortcutSettings.pttUsesCustomShortcut else {
      beginCustomShortcutCapture()
      return
    }
    confirmShortcutAndContinue()
  }

  private func resetDetectionState() {
    shortcutDetected = false
    showContinue = false
  }

  private func confirmShortcutAndContinue() {
    captureError = nil
    shortcutDetected = true
    OmiMotion.withGated(.easeInOut(duration: 0.3)) {
      showContinue = true
    }
  }

  private func installKeyMonitor() {
    let mask: NSEvent.EventTypeMask = [.flagsChanged, .keyDown, .keyUp]
    localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { event in
      handleShortcutEvent(event) ? nil : event
    }
    globalKeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { event in
      _ = handleShortcutEvent(event)
    }

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
    pendingModifierOnlyShortcut = nil
  }

  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    if isRecordingCustomShortcut {
      return captureCustomShortcut(from: event)
    }

    guard !shortcutDetected else { return false }

    let shortcut = shortcutSettings.pttShortcut
    let detected: Bool
    switch event.type {
    case .flagsChanged:
      detected = shortcut.matchesFlagsChanged(event)
    case .keyDown:
      detected = !event.isARepeat && shortcut.matchesKeyDown(event)
    default:
      detected = false
    }

    guard detected else { return false }

    confirmShortcutAndContinue()
    return true
  }

  private func captureCustomShortcut(from event: NSEvent) -> Bool {
    if event.type == .flagsChanged {
      let activeModifiers = ShortcutSettings.KeyboardShortcut.normalizedModifiers(event.modifierFlags)
      if activeModifiers.isEmpty {
        guard let shortcut = pendingModifierOnlyShortcut else { return true }
        shortcutSettings.pttShortcut = shortcut
        isRecordingCustomShortcut = false
        captureError = nil
        return true
      }
      pendingModifierOnlyShortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(
        event,
        allowModifierOnly: true
      )
      return true
    }
    guard let shortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(event, allowModifierOnly: true) else {
      captureError = "Press the key combination you want to use."
      return false
    }

    guard ShortcutSettings.isSafePushToTalkShortcut(shortcut) else {
      captureError = "Push-to-talk needs a modifier so regular typing won't start a voice turn."
      return true
    }

    pendingModifierOnlyShortcut = nil
    shortcutSettings.pttShortcut = shortcut
    isRecordingCustomShortcut = false
    captureError = nil
    return true
  }
}

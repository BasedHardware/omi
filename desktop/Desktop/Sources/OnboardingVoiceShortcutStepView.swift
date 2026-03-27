import SwiftUI

/// Onboarding step: verify the push-to-talk shortcut key without opening the voice bar.
struct OnboardingVoiceShortcutStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var onComplete: () -> Void
  var onSkip: () -> Void

  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var shortcutDetected = false
  @State private var showContinue = false
  @State private var keyMonitor: Any?

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text("Set your voice shortcut")
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button(action: onSkip) {
          Text("Skip")
            .font(.system(size: 13))
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, 24)
      .padding(.vertical, 16)

      Divider()
        .background(OmiColors.backgroundTertiary)

      Spacer()

      // Content
      VStack(spacing: 24) {
        Text("Press and hold to test.\nDoes the button light up?")
          .font(.system(size: 22, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)
          .multilineTextAlignment(.center)

        RoundedRectangle(cornerRadius: 16, style: .continuous)
          .fill(OmiColors.backgroundSecondary)
          .frame(height: 128)
          .frame(maxWidth: 400)
          .overlay {
            shortcutKeyPreview
          }

        VStack(spacing: 12) {
          Text("Try another key if it doesn't react:")
            .font(.system(size: 14, weight: .medium))
            .foregroundColor(OmiColors.textSecondary)

          HStack(spacing: 10) {
            ForEach(ShortcutSettings.PTTKey.allCases, id: \.self) { key in
              shortcutChoiceButton(key)
            }
          }
        }

        HStack(spacing: 14) {
          Button(action: cycleShortcut) {
            Text("Change shortcut")
              .font(.system(size: 15, weight: .semibold))
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, 18)
              .padding(.vertical, 12)
              .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                  .fill(OmiColors.backgroundSecondary)
              )
          }
          .buttonStyle(.plain)

          if showContinue {
            Button(action: onComplete) {
              Text("Continue")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(.black)
                .padding(.horizontal, 28)
                .padding(.vertical, 12)
                .background(
                  RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.white)
                )
            }
            .buttonStyle(.plain)
            .transition(.move(edge: .trailing).combined(with: .opacity))
          }
        }
      }

      Spacer()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
    .onAppear {
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      resetFloatingBarConversation()
      FloatingControlBarManager.shared.hide()
      PushToTalkManager.shared.cleanup()
      installKeyMonitor()
    }
    .onDisappear {
      if let monitor = keyMonitor {
        NSEvent.removeMonitor(monitor)
        keyMonitor = nil
      }
    }
  }

  private func resetFloatingBarConversation() {
    guard let barState = FloatingControlBarManager.shared.barState else { return }
    barState.showingAIConversation = false
    barState.showingAIResponse = false
    barState.aiInputText = ""
    barState.currentAIMessage = nil
    barState.chatHistory = []
    barState.isVoiceFollowUp = false
    barState.voiceFollowUpTranscript = ""
  }

  private var shortcutKeyPreview: some View {
    VStack(spacing: 12) {
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(shortcutDetected ? Color.white : OmiColors.backgroundTertiary)
        .frame(width: 64, height: 64)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(
              shortcutDetected ? Color.white : OmiColors.textTertiary.opacity(0.3),
              lineWidth: 2)
        )
        .overlay {
          VStack(spacing: 6) {
            Text(shortcutLabelTop)
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(shortcutDetected ? .black : OmiColors.textPrimary)

            Text(shortcutLabelBottom)
              .font(.system(size: 14, weight: .medium))
              .foregroundColor(shortcutDetected ? .black.opacity(0.7) : OmiColors.textSecondary)
          }
        }

      Text(shortcutDetected ? "Shortcut detected" : "Press and hold to test")
        .font(.system(size: 13, weight: .medium))
        .foregroundColor(OmiColors.textTertiary)
    }
  }

  private func shortcutChoiceButton(_ key: ShortcutSettings.PTTKey) -> some View {
    let isSelected = shortcutSettings.pttKey == key
    return Button {
      shortcutSettings.pttKey = key
      shortcutDetected = false
      showContinue = false
    } label: {
      HStack(spacing: 6) {
        Text(key.symbol)
          .font(.system(size: 14, weight: .medium))
        Text(pttChoiceTitle(for: key))
          .font(.system(size: 13, weight: .semibold))
      }
      .foregroundColor(isSelected ? .black : OmiColors.textSecondary)
      .padding(.horizontal, 14)
      .padding(.vertical, 10)
      .background(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(isSelected ? Color.white : OmiColors.backgroundSecondary)
      )
    }
    .buttonStyle(.plain)
  }

  private var shortcutLabelTop: String {
    switch shortcutSettings.pttKey {
    case .option:
      return "option"
    case .rightCommand:
      return "right cmd"
    case .fn:
      return "fn"
    }
  }

  private var shortcutLabelBottom: String {
    shortcutSettings.pttKey.symbol
  }

  private func pttChoiceTitle(for key: ShortcutSettings.PTTKey) -> String {
    switch key {
    case .option:
      return "Option"
    case .rightCommand:
      return "Right Cmd"
    case .fn:
      return "Fn"
    }
  }

  private func installKeyMonitor() {
    keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { event in
      guard !shortcutDetected else { return event }
      guard matchesCurrentPTTShortcut(event) else { return event }

      shortcutDetected = true
      withAnimation(.easeInOut(duration: 0.3)) {
        showContinue = true
      }
      return nil
    }
  }

  private func matchesCurrentPTTShortcut(_ event: NSEvent) -> Bool {
    switch shortcutSettings.pttKey {
    case .option:
      let otherModifiers: NSEvent.ModifierFlags = [.command, .control, .shift]
      return event.modifierFlags.intersection(otherModifiers) == []
        && event.modifierFlags.contains(.option)
    case .rightCommand:
      return event.keyCode == 54 && event.modifierFlags.contains(.command)
    case .fn:
      return event.modifierFlags.contains(.function)
    }
  }

  private func cycleShortcut() {
    let allKeys = ShortcutSettings.PTTKey.allCases
    guard let currentIndex = allKeys.firstIndex(of: shortcutSettings.pttKey) else { return }
    let nextIndex = allKeys.index(after: currentIndex)
    shortcutSettings.pttKey =
      nextIndex == allKeys.endIndex ? allKeys[allKeys.startIndex] : allKeys[nextIndex]
    shortcutDetected = false
    showContinue = false
  }
}

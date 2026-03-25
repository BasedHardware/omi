import SwiftUI

/// Onboarding step: verify the push-to-talk shortcut and complete one voice query
/// without pre-showing the floating bar.
struct OnboardingVoiceShortcutStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var onComplete: () -> Void
  var onSkip: () -> Void

  @ObservedObject private var pttManager = PushToTalkManager.shared
  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var observedShortcutPress = false
  @State private var showContinue = false

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
                .foregroundColor(.white)
                .padding(.horizontal, 28)
                .padding(.vertical, 12)
                .background(
                  RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(OmiColors.purplePrimary)
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

      if let barState = FloatingControlBarManager.shared.barState {
        PushToTalkManager.shared.setup(barState: barState)
      }
    }
    .onDisappear {
      if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
        FloatingControlBarManager.shared.toggleAIInput()
      }
    }
    .onChange(of: pttManager.state) { _, newState in
      if newState != .idle {
        observedShortcutPress = true
      }
      if OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: observedShortcutPress,
        pttState: newState
      ) {
        withAnimation(.easeInOut(duration: 0.3)) {
          showContinue = true
        }
      }
    }
  }

  private var shortcutKeyPreview: some View {
    VStack(spacing: 12) {
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(isShortcutActive ? OmiColors.purplePrimary : OmiColors.backgroundTertiary)
        .frame(width: 64, height: 64)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(
              isShortcutActive ? OmiColors.purplePrimary : OmiColors.textTertiary.opacity(0.3),
              lineWidth: 2)
        )
        .overlay {
          VStack(spacing: 6) {
            Text(shortcutLabelTop)
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(isShortcutActive ? .white : OmiColors.textPrimary)

            Text(shortcutLabelBottom)
              .font(.system(size: 14, weight: .medium))
              .foregroundColor(isShortcutActive ? .white.opacity(0.95) : OmiColors.textSecondary)
          }
        }

      Text(isShortcutActive ? "Shortcut detected" : "Press and hold to test")
        .font(.system(size: 13, weight: .medium))
        .foregroundColor(OmiColors.textTertiary)
    }
  }

  private func shortcutChoiceButton(_ key: ShortcutSettings.PTTKey) -> some View {
    let isSelected = shortcutSettings.pttKey == key
    return Button {
      shortcutSettings.pttKey = key
      observedShortcutPress = false
      showContinue = false
    } label: {
      HStack(spacing: 6) {
        Text(key.symbol)
          .font(.system(size: 14, weight: .medium))
        Text(pttChoiceTitle(for: key))
          .font(.system(size: 13, weight: .semibold))
      }
      .foregroundColor(isSelected ? .white : OmiColors.textSecondary)
      .padding(.horizontal, 14)
      .padding(.vertical, 10)
      .background(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(isSelected ? OmiColors.purplePrimary : OmiColors.backgroundSecondary)
      )
    }
    .buttonStyle(.plain)
  }

  private var isShortcutActive: Bool {
    switch pttManager.state {
    case .idle:
      return false
    case .listening, .lockedListening, .finalizing:
      return true
    }
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

  private func cycleShortcut() {
    let allKeys = ShortcutSettings.PTTKey.allCases
    guard let currentIndex = allKeys.firstIndex(of: shortcutSettings.pttKey) else { return }
    let nextIndex = allKeys.index(after: currentIndex)
    shortcutSettings.pttKey =
      nextIndex == allKeys.endIndex ? allKeys[allKeys.startIndex] : allKeys[nextIndex]
    observedShortcutPress = false
    showContinue = false
  }
}

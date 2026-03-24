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
    HStack(spacing: 0) {
      leftPane

      Divider()
        .background(OmiColors.backgroundTertiary)

      rightPane
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

  private var leftPane: some View {
    VStack(alignment: .leading, spacing: 0) {
      Spacer()
        .frame(height: 18)

      VStack(alignment: .leading, spacing: 18) {
        Text("Hold the shortcut\nand ask a question")
          .font(.system(size: 40, weight: .bold))
          .foregroundColor(OmiColors.textPrimary)
          .lineSpacing(2)

        Text(
          "Hold the key you want to use for voice questions, then release to send. Try asking \"What's on my screen?\" If the preview reacts on the right, you're set. If not, switch to another key."
        )
        .font(.system(size: 16))
        .foregroundColor(OmiColors.textSecondary)
        .lineSpacing(4)
        .frame(maxWidth: 420, alignment: .leading)
      }

      Spacer()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(.horizontal, 50)
  }

  private var rightPane: some View {
    ZStack {
      LinearGradient(
        colors: [
          Color(red: 0.17, green: 0.16, blue: 0.08).opacity(0.12),
          Color(red: 0.57, green: 0.48, blue: 0.08).opacity(0.08),
          Color.clear,
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
      )
      .ignoresSafeArea()

      VStack(spacing: 28) {
        HStack {
          Spacer()
          Button(action: onSkip) {
            Text("Skip")
              .font(.system(size: 13))
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }
        .padding(.bottom, -16)

        VStack(alignment: .leading, spacing: 18) {
          Text("Hold the key, then ask omi something")
            .font(.system(size: 22, weight: .semibold))
            .foregroundColor(Color.black.opacity(0.86))
            .frame(maxWidth: .infinity, alignment: .leading)

          RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(Color(red: 0.95, green: 0.94, blue: 0.92))
            .frame(height: 128)
            .overlay {
              shortcutKeyPreview
            }

          VStack(alignment: .leading, spacing: 12) {
            Text("Try another key if it doesn't react:")
              .font(.system(size: 14, weight: .medium))
              .foregroundColor(Color.black.opacity(0.68))

            HStack(spacing: 10) {
              ForEach(ShortcutSettings.PTTKey.allCases, id: \.self) { key in
                shortcutChoiceButton(key)
              }
            }
          }
        }
        .padding(32)
        .background(
          RoundedRectangle(cornerRadius: 24, style: .continuous)
            .fill(Color.white.opacity(0.97))
            .shadow(color: .black.opacity(0.08), radius: 26, x: 0, y: 14)
        )
        .frame(maxWidth: 520)

        if !showContinue {
          Text("Try asking: \"What's on my screen?\"")
            .font(.system(size: 13))
            .foregroundColor(Color.black.opacity(0.55))
            .italic()
        }

        HStack(spacing: 14) {
          Button(action: cycleShortcut) {
            Text("Change shortcut")
              .font(.system(size: 15, weight: .semibold))
              .foregroundColor(Color.black.opacity(0.72))
              .padding(.horizontal, 18)
              .padding(.vertical, 12)
              .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                  .fill(Color.white.opacity(0.82))
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
      .padding(.horizontal, 40)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var shortcutKeyPreview: some View {
    VStack(spacing: 12) {
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(isShortcutActive ? OmiColors.purplePrimary : Color.white)
        .frame(width: 64, height: 64)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(
              isShortcutActive ? OmiColors.purplePrimary : Color.black.opacity(0.12), lineWidth: 2)
        )
        .shadow(color: .black.opacity(0.12), radius: 10, x: 0, y: 6)
        .overlay {
          VStack(spacing: 6) {
            Text(shortcutLabelTop)
              .font(.system(size: 13, weight: .semibold))
              .foregroundColor(isShortcutActive ? .white : Color.black.opacity(0.7))

            Text(shortcutLabelBottom)
              .font(.system(size: 14, weight: .medium))
              .foregroundColor(isShortcutActive ? .white.opacity(0.95) : Color.black.opacity(0.65))
          }
        }

      Text(isShortcutActive ? "Shortcut detected" : "Press and hold to test")
        .font(.system(size: 13, weight: .medium))
        .foregroundColor(Color.black.opacity(0.55))
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
      .foregroundColor(isSelected ? .white : Color.black.opacity(0.7))
      .padding(.horizontal, 14)
      .padding(.vertical, 10)
      .background(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(isSelected ? OmiColors.purplePrimary : Color.white)
      )
      .overlay(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .stroke(isSelected ? OmiColors.purplePrimary : Color.black.opacity(0.08), lineWidth: 1)
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

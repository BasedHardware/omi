import Combine
import SwiftUI

/// Onboarding step: configure and test the floating bar shortcut (Cmd+Enter by default).
struct OnboardingFloatingBarShortcutStepView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @ObservedObject private var shortcutSettings = ShortcutSettings.shared

    @State private var shortcutDetected = false
    @State private var showContinue = false
    @State private var pollCancellable: AnyCancellable?

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
            GlobalShortcutManager.shared.registerShortcuts()
            startPolling()
        }
        .onDisappear {
            pollCancellable?.cancel()
            pollCancellable = nil
            if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
                FloatingControlBarManager.shared.toggleAIInput()
            }
        }
    }

    // MARK: - Left Pane

    private var leftPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            Spacer()
                .frame(height: 18)

            VStack(alignment: .leading, spacing: 18) {
                Text("Open the floating bar\nwith a shortcut")
                    .font(.system(size: 40, weight: .bold))
                    .foregroundColor(OmiColors.textPrimary)
                    .lineSpacing(2)

                Text(
                    "Use this keyboard shortcut to open the floating bar anytime. Type a question, hit Enter, and get an answer right where you're working."
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

    // MARK: - Right Pane

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
                    Text("Press the shortcut to open the floating bar")
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
                        Text("Choose a different shortcut:")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(Color.black.opacity(0.68))

                        HStack(spacing: 10) {
                            ForEach(ShortcutSettings.AskOmiKey.allCases, id: \.self) { key in
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
                    Text("Try pressing the shortcut now")
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

    // MARK: - Shortcut Key Preview

    private var shortcutKeyPreview: some View {
        VStack(spacing: 12) {
            HStack(spacing: 8) {
                ForEach(Array(shortcutSettings.askOmiKey.hintKeys.enumerated()), id: \.offset) { _, symbol in
                    keyCap(symbol)
                }
            }

            Text(shortcutDetected ? "Shortcut detected" : "Press to test")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(Color.black.opacity(0.55))
        }
    }

    private func keyCap(_ label: String) -> some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(shortcutDetected ? OmiColors.purplePrimary : Color.white)
            .frame(width: 48, height: 48)
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(
                        shortcutDetected ? OmiColors.purplePrimary : Color.black.opacity(0.12),
                        lineWidth: 2
                    )
            )
            .shadow(color: .black.opacity(0.12), radius: 10, x: 0, y: 6)
            .overlay {
                Text(label)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(shortcutDetected ? .white : Color.black.opacity(0.7))
            }
    }

    // MARK: - Shortcut Choice Buttons

    private func shortcutChoiceButton(_ key: ShortcutSettings.AskOmiKey) -> some View {
        let isSelected = shortcutSettings.askOmiKey == key
        return Button {
            shortcutSettings.askOmiKey = key
            GlobalShortcutManager.shared.registerShortcuts()
            shortcutDetected = false
            showContinue = false
        } label: {
            HStack(spacing: 4) {
                ForEach(Array(key.hintKeys.enumerated()), id: \.offset) { _, symbol in
                    Text(symbol)
                        .font(.system(size: 13, weight: .medium))
                }
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

    // MARK: - Polling

    private func startPolling() {
        pollCancellable = Timer.publish(every: 0.25, on: .main, in: .common)
            .autoconnect()
            .sink { _ in
                guard !shortcutDetected else { return }
                if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
                    shortcutDetected = true
                    // Close the AI conversation panel so it does not stay open
                    FloatingControlBarManager.shared.toggleAIInput()
                    withAnimation(.easeInOut(duration: 0.3)) {
                        showContinue = true
                    }
                }
            }
    }

    // MARK: - Cycle Shortcut

    private func cycleShortcut() {
        let allKeys = ShortcutSettings.AskOmiKey.allCases
        guard let currentIndex = allKeys.firstIndex(of: shortcutSettings.askOmiKey) else { return }
        let nextIndex = allKeys.index(after: currentIndex)
        shortcutSettings.askOmiKey =
            nextIndex == allKeys.endIndex ? allKeys[allKeys.startIndex] : allKeys[nextIndex]
        GlobalShortcutManager.shared.registerShortcuts()
        shortcutDetected = false
        showContinue = false
    }
}

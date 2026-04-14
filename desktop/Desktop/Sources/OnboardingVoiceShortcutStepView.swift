import SwiftUI

/// Onboarding step: verify the push-to-talk shortcut without opening the voice bar.
struct OnboardingVoiceShortcutStepView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
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

    static var savedMenu: NSMenu?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                OnboardingLogoMark(onForceComplete: onForceComplete)

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

            VStack(spacing: 24) {
                Text("Let's set \"Audio ask a question\" shortcut.\nPress and hold to test. Does the button light up?")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)
                    .multilineTextAlignment(.center)

                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(OmiColors.backgroundSecondary)
                    .frame(height: 128)
                    .frame(maxWidth: 420)
                    .overlay {
                        shortcutKeyPreview
                    }

                VStack(spacing: 12) {
                    Text("Try another shortcut if it doesn't react:")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)

                    HStack(spacing: 10) {
                        ForEach(ShortcutSettings.pttPresets, id: \.self) { shortcut in
                            shortcutChoiceButton(shortcut)
                        }
                        customShortcutButton
                    }

                    if isRecordingCustomShortcut || shortcutSettings.pttUsesCustomShortcut || captureError != nil {
                        customShortcutRecorder
                    }
                }

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
            removeKeyMonitors()
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
            HStack(spacing: 8) {
                ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                    keyCap(token)
                }
            }

            Text(shortcutDetected ? "Shortcut detected" : "Press and hold to test")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private var customShortcutButton: some View {
        let isSelected = shortcutSettings.pttUsesCustomShortcut || isRecordingCustomShortcut
        return Button(action: beginCustomShortcutCapture) {
            Text("Custom")
                .font(.system(size: 13, weight: .medium))
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

    private var customShortcutRecorder: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(isRecordingCustomShortcut ? "Press and hold your custom shortcut now" : "Custom shortcut")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(OmiColors.textPrimary)

            HStack(spacing: 10) {
                HStack(spacing: 6) {
                    ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                        smallKeyCap(token, active: true)
                    }
                }

                Spacer()

                Button(action: handleCustomShortcutSaveButton) {
                    Text(isRecordingCustomShortcut ? "Listening..." : "Save")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(OmiColors.backgroundPrimary)
                        )
                }
                .buttonStyle(.plain)
                .disabled(isRecordingCustomShortcut)
            }

            Text("You can use one key or a combination like ⌘ J.")
                .font(.system(size: 12))
                .foregroundColor(OmiColors.textTertiary)

            if let captureError {
                Text(captureError)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.red.opacity(0.9))
            }
        }
        .padding(14)
        .frame(maxWidth: 420)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(OmiColors.backgroundSecondary)
        )
    }

    private func keyCap(_ label: String) -> some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(shortcutDetected ? Color.white : OmiColors.backgroundTertiary)
            .frame(minWidth: 48, minHeight: 48)
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(
                        shortcutDetected ? Color.white : OmiColors.textTertiary.opacity(0.3),
                        lineWidth: 2
                    )
            )
            .overlay {
                Text(label)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(shortcutDetected ? .black : OmiColors.textPrimary)
                    .padding(.horizontal, label.count > 2 ? 14 : 10)
            }
            .fixedSize()
    }

    private func smallKeyCap(_ label: String, active: Bool) -> some View {
        RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(active ? Color.white : OmiColors.backgroundTertiary)
            .frame(minWidth: 36, minHeight: 32)
            .overlay {
                Text(label)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(active ? .black : OmiColors.textPrimary)
                    .padding(.horizontal, label.count > 2 ? 10 : 8)
            }
            .fixedSize()
    }

    private func shortcutChoiceButton(_ shortcut: ShortcutSettings.KeyboardShortcut) -> some View {
        let isSelected = shortcutSettings.pttShortcut == shortcut && !shortcutSettings.pttUsesCustomShortcut
        return Button {
            shortcutSettings.pttShortcut = shortcut
            isRecordingCustomShortcut = false
            captureError = nil
            resetDetectionState()
        } label: {
            HStack(spacing: 6) {
                ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                    Text(token)
                        .font(.system(size: 13, weight: .medium))
                }
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

    private func beginCustomShortcutCapture() {
        isRecordingCustomShortcut = true
        captureError = nil
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
        withAnimation(.easeInOut(duration: 0.3)) {
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
        guard let shortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(event, allowModifierOnly: true) else {
            if event.type == .flagsChanged, event.modifierFlags.intersection(.deviceIndependentFlagsMask).isEmpty {
                return false
            }
            captureError = "Press the key combination you want to use."
            return false
        }

        shortcutSettings.pttShortcut = shortcut
        isRecordingCustomShortcut = false
        captureError = nil
        return true
    }
}

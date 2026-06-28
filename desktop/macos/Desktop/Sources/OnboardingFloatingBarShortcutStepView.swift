import SwiftUI

/// Onboarding step: configure and test the floating bar shortcut.
/// Only detects the keypress and does not open the floating bar.
struct OnboardingFloatingBarShortcutStepView: View {
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
                Text("Let's set \"Ask a question\" shortcut.\nPress this shortcut. Do the buttons light up?")
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
                    Text("Choose a different shortcut:")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)

                    HStack(spacing: 10) {
                        ForEach(ShortcutSettings.askOmiPresets, id: \.self) { shortcut in
                            shortcutChoiceButton(shortcut)
                        }
                        customShortcutButton
                    }

                    if isRecordingCustomShortcut || shortcutSettings.askOmiUsesCustomShortcut || captureError != nil {
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
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
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
        VStack(spacing: 12) {
            HStack(spacing: 8) {
                ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { _, symbol in
                    keyCap(symbol)
                }
            }

            Text(shortcutDetected ? "Shortcut detected" : "Press to test")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private var customShortcutButton: some View {
        let isSelected = shortcutSettings.askOmiUsesCustomShortcut || isRecordingCustomShortcut
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
            Text(isRecordingCustomShortcut ? "Press your custom shortcut now" : "Custom shortcut")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(OmiColors.textPrimary)

            HStack(spacing: 10) {
                HStack(spacing: 6) {
                    ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
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

            Text("Use at least one non-modifier key, like J or Return.")
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
        let isSelected = shortcutSettings.askOmiShortcut == shortcut && !shortcutSettings.askOmiUsesCustomShortcut
        return Button {
            shortcutSettings.askOmiShortcut = shortcut
            isRecordingCustomShortcut = false
            captureError = nil
            resetDetectionState()
        } label: {
            HStack(spacing: 4) {
                ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, symbol in
                    Text(symbol)
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
        guard shortcutSettings.askOmiUsesCustomShortcut else {
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
        let mask: NSEvent.EventTypeMask = [.keyDown, .flagsChanged]
        localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { event in
            handleShortcutEvent(event) ? nil : event
        }
        globalKeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { event in
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
            captureError = "Ask omi needs a non-modifier key."
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
}

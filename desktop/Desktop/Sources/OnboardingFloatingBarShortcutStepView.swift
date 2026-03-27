import Combine
import SwiftUI

/// Onboarding step: configure and test the floating bar shortcut (Cmd+Enter by default).
/// Only detects the keypress — does NOT open the floating bar, to avoid confusing the user.
struct OnboardingFloatingBarShortcutStepView: View {
    @ObservedObject var appState: AppState
    @ObservedObject var chatProvider: ChatProvider
    var onComplete: () -> Void
    var onSkip: () -> Void

    @ObservedObject private var shortcutSettings = ShortcutSettings.shared

    @State private var shortcutDetected = false
    @State private var showContinue = false
    @State private var localKeyMonitor: Any?
    @State private var globalKeyMonitor: Any?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Set your keyboard shortcut")
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
                Text("Press this shortcut.\nDo the buttons light up?")
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
                    Text("Choose a different shortcut:")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)

                    HStack(spacing: 10) {
                        ForEach(ShortcutSettings.AskOmiKey.allCases, id: \.self) { key in
                            shortcutChoiceButton(key)
                        }
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
            // Unregister the global hotkey so the floating bar does NOT open.
            // We detect the keypress ourselves via a local NSEvent monitor.
            GlobalShortcutManager.shared.unregisterShortcuts()
            installKeyMonitor()
        }
        .onDisappear {
            if let monitor = localKeyMonitor {
                NSEvent.removeMonitor(monitor)
                localKeyMonitor = nil
            }
            if let monitor = globalKeyMonitor {
                NSEvent.removeMonitor(monitor)
                globalKeyMonitor = nil
            }
            // Re-register the global hotkey for the next step.
            GlobalShortcutManager.shared.registerShortcuts()
        }
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
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func keyCap(_ label: String) -> some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(shortcutDetected ? Color.white : OmiColors.backgroundTertiary)
            .frame(width: 48, height: 48)
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
            }
    }

    // MARK: - Shortcut Choice Buttons

    private func shortcutChoiceButton(_ key: ShortcutSettings.AskOmiKey) -> some View {
        let isSelected = shortcutSettings.askOmiKey == key
        return Button {
            shortcutSettings.askOmiKey = key
            shortcutDetected = false
            showContinue = false
        } label: {
            HStack(spacing: 4) {
                ForEach(Array(key.hintKeys.enumerated()), id: \.offset) { _, symbol in
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

    // MARK: - Key Monitor

    private func installKeyMonitor() {
        localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if handleShortcutEvent(event) {
                return nil
            }
            return event
        }
        globalKeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { event in
            _ = handleShortcutEvent(event)
        }
    }

    private func handleShortcutEvent(_ event: NSEvent) -> Bool {
        guard !shortcutDetected else { return false }
        guard shortcutSettings.askOmiKey.matches(event) else { return false }
        DispatchQueue.main.async {
            shortcutDetected = true
            withAnimation(.easeInOut(duration: 0.3)) {
                showContinue = true
            }
        }
        return true
    }
}

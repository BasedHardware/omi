import SwiftUI

/// Settings section for keyboard shortcuts and push-to-talk configuration.
struct ShortcutsSettingsSection: View {
    @ObservedObject private var settings = ShortcutSettings.shared
    @Binding var highlightedSettingId: String?
    @State private var recordingTarget: ShortcutTarget?
    @State private var captureError: String?
    @State private var localShortcutCaptureMonitor: Any?

    init(highlightedSettingId: Binding<String?> = .constant(nil)) {
        self._highlightedSettingId = highlightedSettingId
    }

    private enum ShortcutTarget {
        case askOmi
        case pushToTalk
    }

    var body: some View {
        VStack(spacing: 20) {
            aiModelCard
            backgroundStyleCard
            draggableBarCard
            askOmiKeyCard
            pttKeyCard
            pttTranscriptionModeCard
            doubleTapCard
            pttSoundsCard
            referenceCard
        }
        .onDisappear {
            stopShortcutCapture()
        }
    }

    private var aiModelCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("AI Model")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Choose the AI model for Ask omi conversations.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }

            HStack(spacing: 12) {
                ForEach(ShortcutSettings.availableModels, id: \.id) { model in
                    aiModelButton(model)
                }
                Spacer()
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.model", highlightedSettingId: $highlightedSettingId))
    }

    private func aiModelButton(_ model: (id: String, label: String)) -> some View {
        let isSelected = settings.selectedModel == model.id
        return Button {
            settings.selectedModel = model.id
        } label: {
            Text(model.label)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected
                              ? OmiColors.purplePrimary.opacity(0.3)
                              : OmiColors.backgroundTertiary.opacity(0.5))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(isSelected ? OmiColors.purplePrimary : Color.clear, lineWidth: 1.5)
                )
        }
        .buttonStyle(.plain)
    }

    private var backgroundStyleCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Background Style")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            HStack(spacing: 16) {
                Text("Transparent")
                    .scaledFont(size: 13, weight: settings.solidBackground ? .regular : .semibold)
                    .foregroundColor(settings.solidBackground ? OmiColors.textTertiary : OmiColors.textPrimary)

                Toggle("", isOn: $settings.solidBackground)
                    .toggleStyle(.switch)
                    .tint(OmiColors.purplePrimary)
                    .labelsHidden()

                Text("Solid Dark")
                    .scaledFont(size: 13, weight: settings.solidBackground ? .semibold : .regular)
                    .foregroundColor(settings.solidBackground ? OmiColors.textPrimary : OmiColors.textTertiary)

                Spacer()
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.background", highlightedSettingId: $highlightedSettingId))
    }

    private var draggableBarCard: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Draggable Floating Bar")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Allow repositioning the floating bar by dragging it.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }
            Spacer()
            Toggle("", isOn: $settings.draggableBarEnabled)
                .toggleStyle(.switch)
                .tint(OmiColors.purplePrimary)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.draggable", highlightedSettingId: $highlightedSettingId))
    }

    private var askOmiKeyCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Ask omi Shortcut")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Global shortcut to open Ask omi from anywhere.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }

            HStack(spacing: 12) {
                ForEach(ShortcutSettings.askOmiPresets, id: \.self) { shortcut in
                    askOmiKeyButton(shortcut)
                }
                customShortcutButton(for: .askOmi, isSelected: settings.askOmiUsesCustomShortcut)
                Spacer()
            }

            if recordingTarget == .askOmi || settings.askOmiUsesCustomShortcut || (captureError != nil && recordingTarget == .askOmi) {
                shortcutRecorderCard(
                    title: recordingTarget == .askOmi ? "Press your custom Ask omi shortcut now" : "Custom Ask omi shortcut",
                    shortcut: settings.askOmiShortcut,
                    action: { startShortcutCapture(.askOmi) },
                    helperText: "Use at least one non-modifier key."
                )
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.shortcut", highlightedSettingId: $highlightedSettingId))
    }

    private func askOmiKeyButton(_ shortcut: ShortcutSettings.KeyboardShortcut) -> some View {
        let isSelected = settings.askOmiShortcut == shortcut && !settings.askOmiUsesCustomShortcut
        return Button {
            stopShortcutCapture()
            settings.askOmiShortcut = shortcut
        } label: {
            HStack(spacing: 4) {
                ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                    Text(token)
                        .scaledFont(size: 13, weight: .medium)
                }
            }
            .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected
                              ? OmiColors.purplePrimary.opacity(0.3)
                              : OmiColors.backgroundTertiary.opacity(0.5))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(isSelected ? OmiColors.purplePrimary : Color.clear, lineWidth: 1.5)
                )
        }
        .buttonStyle(.plain)
    }

    private var pttKeyCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Push to Talk")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Hold the key to speak, release to send your question to AI.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }

            HStack(spacing: 12) {
                ForEach(ShortcutSettings.pttPresets, id: \.self) { shortcut in
                    pttKeyButton(shortcut)
                }
                customShortcutButton(for: .pushToTalk, isSelected: settings.pttUsesCustomShortcut)
                Spacer()
            }

            if recordingTarget == .pushToTalk || settings.pttUsesCustomShortcut || (captureError != nil && recordingTarget == .pushToTalk) {
                shortcutRecorderCard(
                    title: recordingTarget == .pushToTalk ? "Press your custom push-to-talk shortcut now" : "Custom push-to-talk shortcut",
                    shortcut: settings.pttShortcut,
                    action: { startShortcutCapture(.pushToTalk) },
                    helperText: "One key or a key combination both work."
                )
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.ptt", highlightedSettingId: $highlightedSettingId))
    }

    private func pttKeyButton(_ shortcut: ShortcutSettings.KeyboardShortcut) -> some View {
        let isSelected = settings.pttShortcut == shortcut && !settings.pttUsesCustomShortcut
        return Button {
            stopShortcutCapture()
            settings.pttShortcut = shortcut
        } label: {
            HStack(spacing: 6) {
                ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                    Text(token)
                        .scaledFont(size: 13, weight: .medium)
                }
            }
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isSelected
                          ? OmiColors.purplePrimary.opacity(0.3)
                          : OmiColors.backgroundTertiary.opacity(0.5))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isSelected ? OmiColors.purplePrimary : Color.clear, lineWidth: 1.5)
            )
        }
        .buttonStyle(.plain)
    }

    private var pttTranscriptionModeCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Transcription Mode")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text(settings.pttTranscriptionMode.description)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }

            HStack(spacing: 12) {
                ForEach(ShortcutSettings.PTTTranscriptionMode.allCases, id: \.self) { mode in
                    pttTranscriptionModeButton(mode)
                }
                Spacer()
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.transcriptionmode", highlightedSettingId: $highlightedSettingId))
    }

    private func pttTranscriptionModeButton(_ mode: ShortcutSettings.PTTTranscriptionMode) -> some View {
        let isSelected = settings.pttTranscriptionMode == mode
        return Button {
            settings.pttTranscriptionMode = mode
        } label: {
            Text(mode.rawValue)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected
                              ? OmiColors.purplePrimary.opacity(0.3)
                              : OmiColors.backgroundTertiary.opacity(0.5))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(isSelected ? OmiColors.purplePrimary : Color.clear, lineWidth: 1.5)
                )
        }
        .buttonStyle(.plain)
    }

    private var doubleTapCard: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Double-tap for Locked Mode")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Double-tap the push-to-talk key to keep listening hands-free. Tap again to send.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }
            Spacer()
            Toggle("", isOn: $settings.doubleTapForLock)
                .toggleStyle(.switch)
                .tint(OmiColors.purplePrimary)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.doubletap", highlightedSettingId: $highlightedSettingId))
    }

    private var pttSoundsCard: some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Push-to-Talk Sounds")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Play audio feedback when starting and ending voice input.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }
            Spacer()
            Toggle("", isOn: $settings.pttSoundsEnabled)
                .toggleStyle(.switch)
                .tint(OmiColors.purplePrimary)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
        .modifier(SettingHighlightModifier(settingId: "floatingbar.pttsounds", highlightedSettingId: $highlightedSettingId))
    }

    private var referenceCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Keyboard Shortcuts")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            shortcutRow(label: "Ask omi", keys: settings.askOmiShortcut.displayLabel)
            shortcutRow(label: "Toggle floating bar", keys: "\u{2318}\\")
            shortcutRow(label: "Push to talk", keys: settings.pttShortcut.displayLabel + " hold")
            if settings.doubleTapForLock {
                shortcutRow(label: "Locked listening", keys: settings.pttShortcut.displayLabel + " \u{00D7}2")
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
    }

    private func shortcutRow(label: String, keys: String) -> some View {
        HStack {
            Text(label)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textSecondary)
            Spacer()
            Text(keys)
                .scaledMonospacedFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(OmiColors.backgroundTertiary.opacity(0.8))
                .cornerRadius(6)
        }
    }

    private func customShortcutButton(for target: ShortcutTarget, isSelected: Bool) -> some View {
        Button {
            startShortcutCapture(target)
        } label: {
            Text("Custom")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(isSelected || recordingTarget == target ? .black : OmiColors.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(isSelected || recordingTarget == target
                              ? OmiColors.purplePrimary.opacity(0.3)
                              : OmiColors.backgroundTertiary.opacity(0.5))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(isSelected || recordingTarget == target ? OmiColors.purplePrimary : Color.clear, lineWidth: 1.5)
                )
        }
        .buttonStyle(.plain)
    }

    private func shortcutRecorderCard(
        title: String,
        shortcut: ShortcutSettings.KeyboardShortcut,
        action: @escaping () -> Void,
        helperText: String
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            HStack(spacing: 10) {
                HStack(spacing: 6) {
                    ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                        Text(token)
                            .scaledFont(size: 13, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, token.count > 2 ? 10 : 8)
                            .padding(.vertical, 7)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(OmiColors.backgroundPrimary)
                            )
                    }
                }

                Spacer()

                Button(action: action) {
                    Text(recordingTarget != nil ? "Listening..." : "Change")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(OmiColors.backgroundPrimary)
                        )
                }
                .buttonStyle(.plain)
            }

            Text(helperText)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textSecondary)

            if let captureError, recordingTarget != nil {
                Text(captureError)
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(.red.opacity(0.9))
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundSecondary.opacity(0.85))
        )
    }

    private func startShortcutCapture(_ target: ShortcutTarget) {
        stopShortcutCapture()
        recordingTarget = target
        captureError = nil

        localShortcutCaptureMonitor = NSEvent.addLocalMonitorForEvents(matching: [.flagsChanged, .keyDown]) { event in
            handleShortcutCapture(event) ? nil : event
        }
    }

    private func stopShortcutCapture() {
        if let monitor = localShortcutCaptureMonitor {
            NSEvent.removeMonitor(monitor)
            localShortcutCaptureMonitor = nil
        }
        recordingTarget = nil
        captureError = nil
    }

    private func handleShortcutCapture(_ event: NSEvent) -> Bool {
        guard let target = recordingTarget else { return false }

        switch target {
        case .askOmi:
            if event.type == .flagsChanged {
                captureError = "Ask omi needs a non-modifier key."
                return true
            }
            guard let shortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(event, allowModifierOnly: false) else {
                return false
            }
            settings.askOmiShortcut = shortcut
        case .pushToTalk:
            guard let shortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(event, allowModifierOnly: true) else {
                return false
            }
            settings.pttShortcut = shortcut
        }

        stopShortcutCapture()
        return true
    }
}

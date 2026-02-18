import SwiftUI

/// Settings section for keyboard shortcuts and push-to-talk configuration.
struct ShortcutsSettingsSection: View {
    @ObservedObject private var settings = ShortcutSettings.shared

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
    }

    private var aiModelCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("AI Model")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Choose the AI model for Ask Omi conversations.")
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
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Background Style")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text(settings.solidBackground
                     ? "Solid dark background"
                     : "Semi-transparent with blur")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }
            Spacer()
            Toggle("", isOn: $settings.solidBackground)
                .toggleStyle(.switch)
                .tint(OmiColors.purplePrimary)
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
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
    }

    private var askOmiKeyCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Ask Omi Shortcut")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text("Global shortcut to open Ask Omi from anywhere.")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
            }

            HStack(spacing: 12) {
                ForEach(ShortcutSettings.AskOmiKey.allCases, id: \.self) { key in
                    askOmiKeyButton(key)
                }
                Spacer()
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
    }

    private func askOmiKeyButton(_ key: ShortcutSettings.AskOmiKey) -> some View {
        let isSelected = settings.askOmiKey == key
        return Button {
            settings.askOmiKey = key
        } label: {
            Text(key.rawValue)
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
                ForEach(ShortcutSettings.PTTKey.allCases, id: \.self) { key in
                    pttKeyButton(key)
                }
                Spacer()
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
        )
    }

    private func pttKeyButton(_ key: ShortcutSettings.PTTKey) -> some View {
        let isSelected = settings.pttKey == key
        return Button {
            settings.pttKey = key
        } label: {
            HStack(spacing: 8) {
                Text(key.symbol)
                    .scaledFont(size: 16)
                Text(key.rawValue)
                    .scaledFont(size: 13, weight: .medium)
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
    }

    private var referenceCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Keyboard Shortcuts")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            shortcutRow(label: "Ask omi", keys: settings.askOmiKey.rawValue)
            shortcutRow(label: "Toggle floating bar", keys: "\u{2318}\\")
            shortcutRow(label: "Push to talk", keys: settings.pttKey.symbol + " hold")
            if settings.doubleTapForLock {
                shortcutRow(label: "Locked listening", keys: settings.pttKey.symbol + " \u{00D7}2")
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
}

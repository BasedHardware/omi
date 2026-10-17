import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// How Omi helps › Assistant: how Omi answers out loud and in which voice, how often it reaches out
/// with tips, and the daily recap. The one place for tips and the recap (Notifications links here).
struct AssistantScreen: View {
    @Environment(SettingsStore.self) private var settings

    var body: some View {
        @Bindable var settings = settings
        SettingsList {
            Section {
                Picker(selection: $settings.voiceResponseMode) {
                    Text(L("nativeSpokenOff")).tag(0)
                    Text(L("nativeSpokenHeadphones")).tag(1)
                    Text(L("nativeSpokenAlways")).tag(2)
                } label: {
                    SettingsRowLabel(title: L("nativeSpokenReplies"), systemImage: "speaker.wave.2")
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("assistant.spokenReplies")
                NavigationLink {
                    VoicePickerScreen()
                } label: {
                    SettingsRowLabel(title: L("nativeAssistantVoice"), systemImage: "person.wave.2", value: selectedVoiceName)
                }
                .accessibilityIdentifier("assistant.voice")
            }
            Section {
                Picker(selection: Binding(
                    get: { settings.notificationFrequency },
                    set: { value in Task { await settings.setNotificationFrequency(value) } }
                )) {
                    // Flutter's six levels (`mentor-notification-settings` 0…5; 3 is the backend default).
                    ForEach(0 ..< 6, id: \.self) { Text(Self.frequencyTitle($0)).tag($0) }
                } label: {
                    SettingsRowLabel(title: L("nativeProactiveNotifications"), systemImage: "lightbulb")
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("notifications.frequency")
            } footer: {
                Text(Self.frequencyDescription(settings.notificationFrequency))
            }
            Section {
                Toggle(isOn: Binding(
                    get: { settings.dailySummaryEnabled },
                    set: { value in Task { await settings.setDailySummary(enabled: value, hour: settings.dailySummaryHour) } }
                )) {
                    SettingsRowLabel(title: L("nativeDailyRecap"), systemImage: "sun.horizon")
                }
                .accessibilityIdentifier("assistant.dailyRecap")
                if settings.dailySummaryEnabled {
                    Picker(selection: Binding(
                        get: { settings.dailySummaryHour },
                        set: { hour in Task { await settings.setDailySummary(enabled: true, hour: hour) } }
                    )) {
                        ForEach(0 ..< 24, id: \.self) { Text(Self.hourLabel($0)).tag($0) }
                    } label: {
                        SettingsRowLabel(title: L("nativeDailySummaryTime"), systemImage: "clock")
                    }
                    .pickerStyle(.menu)
                }
            } footer: {
                Text(L("nativeDailySummaryFooter"))
            }
        }
        .omiPage(L("nativeAssistant"))
        .task { await settings.loadNotifications() }
        .task { await settings.loadVoices() }
    }

    private var selectedVoiceName: String? {
        settings.voices.first { $0.id == settings.selectedVoice }?.name
    }

    static func hourLabel(_ hour: Int) -> String {
        (Calendar.current.date(bySettingHour: hour, minute: 0, second: 0, of: .now) ?? .now)
            .formatted(date: .omitted, time: .shortened)
    }

    static func frequencyTitle(_ level: Int) -> String {
        switch level {
        case 1: L("frequencyMinimal")
        case 2: L("frequencyLow")
        case 3: L("frequencyBalanced")
        case 4: L("frequencyHigh")
        case 5: L("frequencyMaximum")
        default: L("frequencyOff")
        }
    }

    static func frequencyDescription(_ level: Int) -> String {
        switch level {
        case 1: L("frequencyDescMinimal")
        case 2: L("frequencyDescLow")
        case 3: L("frequencyDescBalanced")
        case 4: L("frequencyDescHigh")
        case 5: L("nativeFrequencyDescMaximum")
        default: L("nativeProactiveFooter")
        }
    }
}

/// Assistant › Voice: every voice with a play button; tapping a row picks it.
struct VoicePickerScreen: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(VoicePlaybackStore.self) private var playback

    var body: some View {
        SettingsList {
            Section {
                if settings.voices.isEmpty {
                    ProgressView().frame(maxWidth: .infinity)
                }
                ForEach(settings.voices, id: \.id) { voice in
                    HStack(spacing: DS.Spacing.md) {
                        previewButton(voice.id)
                        Button {
                            DSHaptics.selection()
                            Task { await settings.selectVoice(voice.id) }
                        } label: {
                            HStack {
                                Text(voice.name).foregroundStyle(DS.Palette.ink)
                                Spacer()
                                if settings.selectedVoice == voice.id {
                                    Image(systemName: "checkmark").font(.body.weight(.semibold)).foregroundStyle(DS.Palette.ink)
                                }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(settings.selectedVoice == voice.id ? .isSelected : [])
                    }
                }
            } footer: {
                Text(playback.previewFailed ? L("nativeVoicePreviewFailed") : L("nativeVoicePickerFooter"))
            }
        }
        .omiPage(L("nativeAssistantVoice"))
        .task { await settings.loadVoices() }
        .onDisappear { playback.stop() }
    }

    /// Plays a sample in that voice (the backend voice only, no system stand-in), or stops it.
    private func previewButton(_ voiceID: String) -> some View {
        let playing = playback.playingID == "preview:\(voiceID)"
        return Button {
            DSHaptics.selection()
            playback.preview(voiceID: voiceID, sample: L("voicePreviewSample"))
        } label: {
            ZStack {
                if playing, playback.isLoading {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: playing ? "stop.fill" : "play.fill")
                        .font(DS.Typography.micro)
                        .foregroundStyle(playing ? DS.Palette.onAccent : DS.Palette.ink)
                }
            }
            .frame(width: 30, height: 30)
            .background(playing ? DS.Palette.ink : Color.clear, in: Circle())
            .overlay(Circle().strokeBorder(playing ? Color.clear : DS.Palette.hairline, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(playing ? L("nativeStopReading") : L("nativePlayVoicePreview"))
    }
}

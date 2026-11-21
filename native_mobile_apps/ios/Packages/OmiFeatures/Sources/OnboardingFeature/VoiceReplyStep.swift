import AVFoundation
import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// "Hear Omi's answers" (Flutter `voice_reply_step`): a preview of the last answer (or a sample)
/// in the chosen assistant voice, and when answers are spoken: off, headphones only, always (the
/// same setting as Settings › Assistant › Spoken replies); one line says what happens right now.
struct VoiceReplyStep: View {
    let mode: VoicePlaybackStore.ReplyMode
    /// The answer from the ask step, when there was one.
    let lastAnswer: String?
    let onChoose: (VoicePlaybackStore.ReplyMode) -> Void
    let onContinue: () -> Void
    @Environment(VoicePlaybackStore.self) private var voice
    @State private var output = AudioRoute.current

    private var playing: Bool {
        voice.playingID == VoicePlaybackStore.replyPreviewID
    }

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourOmi"),
            title: L("deviceOnboardingVoiceReplyTitle"),
            subtitle: L("nativeVoiceReplyShort"),
            button: StepButton(title: L("continueButton"), action: onContinue)
        ) {
            preview
            RowList {
                choice(.off, "speaker.slash", L("nativeSpokenOff"))
                choice(.headphonesOnly, "headphones", L("nativeSpokenHeadphones"))
                choice(.always, "speaker.wave.2", L("nativeSpokenAlways"))
            }
            status
        }
        .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification)) { _ in
            Task { @MainActor in output = AudioRoute.current }
        }
        .onDisappear { if playing { voice.stop() } }
        .task {
            #if DEBUG
                // -omiPreviewReply YES: plays the preview on arrival (simulator check of the audio path).
                if UserDefaults.standard.bool(forKey: "omiPreviewReply") {
                    voice.previewReply(lastAnswer ?? L("deviceOnboardingVoiceReplySample"))
                }
            #endif
        }
    }

    private var preview: some View {
        Button {
            DSHaptics.tap(.light)
            voice.previewReply(lastAnswer ?? L("deviceOnboardingVoiceReplySample"))
        } label: {
            HStack(spacing: DS.Spacing.md) {
                ZStack {
                    Circle().fill(DS.Palette.ink)
                    if playing, voice.isLoading {
                        ProgressView().tint(DS.Palette.onAccent)
                    } else {
                        Image(systemName: playing ? "stop.fill" : "play.fill")
                            .font(.body.weight(.bold))
                            .foregroundStyle(DS.Palette.onAccent)
                            .contentTransition(.symbolEffect(.replace))
                    }
                }
                .frame(width: 48, height: 48)
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(previewTitle).font(.body.weight(.semibold)).foregroundStyle(DS.Palette.ink)
                    Text(routeLine).font(.footnote).foregroundStyle(DS.Palette.inkSecondary)
                    SpeakingBars(active: playing && !voice.isLoading).frame(height: 16).padding(.top, DS.Spacing.xxs)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onboardingCard()
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, DS.Spacing.gutter)
        .accessibilityLabel(playing ? L("nativeStopReading") : previewTitle)
        .accessibilityIdentifier("onboarding.voiceReply.preview")
    }

    private var previewTitle: String {
        if playing { return lastAnswer == nil ? L("nativeVoiceReplyPreviewPlayingSample") : L("deviceOnboardingVoiceReplyPreviewPlaying") }
        return lastAnswer == nil ? L("nativeVoiceReplyPreviewSample") : L("nativeVoiceReplyPreviewLast")
    }

    private var routeLine: String {
        switch output {
        case let .headphones(name):
            L("deviceOnboardingVoiceReplyPreviewThroughDevice", name ?? L("deviceOnboardingVoiceReplyGenericHeadphones"))
        case .speaker: L("deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker")
        }
    }

    private func choice(_ value: VoicePlaybackStore.ReplyMode, _ symbol: String, _ title: String) -> some View {
        ChoiceRow(symbol: symbol, title: title, selected: mode == value) {
            onChoose(value)
        }
        .accessibilityIdentifier("onboarding.voiceReply.\(value)")
    }

    /// What the chosen mode does with the headphones connected (or not) right now.
    private var status: some View {
        let headphones: String? = if case let .headphones(name) = output {
            name ?? L("deviceOnboardingVoiceReplyGenericHeadphones")
        } else {
            nil
        }
        let line = switch (mode, headphones) {
        case (.off, _):
            StatusLine(L("deviceOnboardingVoiceReplyStatusOff"), "speaker.slash", DS.Palette.inkSecondary)
        case let (.headphonesOnly, name?):
            StatusLine(L("deviceOnboardingVoiceReplyStatusHeadphonesConnected", name), "headphones", DS.Palette.success)
        case (.headphonesOnly, nil):
            StatusLine(L("nativeVoiceReplyNoHeadphones"), "headphones", DS.Palette.warning)
        case let (.always, name?):
            StatusLine(L("nativeVoiceReplyAlwaysThrough", name), "headphones", DS.Palette.success)
        case (.always, nil):
            StatusLine(L("deviceOnboardingVoiceReplyStatusAlwaysSpeaker"), "speaker.wave.2", DS.Palette.warning)
        }
        return line.view
            .padding(.horizontal, DS.Spacing.gutter)
            .animation(DS.Motion.standard, value: line.text)
            .accessibilityIdentifier("onboarding.voiceReply.status")
    }
}

/// Bars that move while Omi speaks, flat and faint when it does not.
private struct SpeakingBars: View {
    let active: Bool

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 15, paused: !active)) { context in
            let phase = context.date.timeIntervalSinceReferenceDate * 6
            HStack(alignment: .center, spacing: 3) {
                ForEach(0 ..< 18, id: \.self) { index in
                    let base = active ? 0.3 + Double((index * 7) % 11) / 16 : 0.22
                    let pulse = active ? 0.55 + 0.45 * abs(sin(phase + Double(index) * 0.72)) : 1
                    Capsule()
                        .fill(DS.Palette.ink.opacity(active ? 1 : 0.24))
                        .frame(maxWidth: .infinity)
                        .frame(height: max(3, 16 * base * pulse))
                }
            }
        }
        .accessibilityHidden(true)
    }
}

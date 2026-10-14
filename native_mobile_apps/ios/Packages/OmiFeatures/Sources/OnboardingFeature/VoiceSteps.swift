import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// "Whisper to your Omi" (or "Say something" on the iPhone): everything said appears live, word
/// by word, utterance after utterance. The session keeps running into the voice step.
struct HelloStep: View {
    let store: OnboardingStore

    var body: some View {
        if let voice = store.voice {
            content(voice)
        } else {
            Color.clear.onAppear(perform: store.next)
        }
    }

    private func content(_ voice: VoiceIntroStore) -> some View {
        let heard = voice.heardSomething
        let device = store.voiceSource == .device
        return OnboardingLayout(
            kicker: L("nativeKickerTryIt"),
            title: heard ? L("nativeOmiHearsYouTitle") : device ? L("nativeWhisperToYourOmi") : L("nativeSaySomethingTitle"),
            subtitle: heard ? L("nativeOmiHearsYouBody") : L("nativeWhisperShort"),
            button: StepButton(title: L("continueButton"), isEnabled: heard, action: store.next),
            secondary: heard ? nil : StepButton(title: L("skip"), action: store.next)
        ) {
            VoiceLiveCard(voice: voice, text: voice.transcript, placeholder: device ? L("nativeWhisperPlaceholder") : L("saySomething"))
        }
        .task { await voice.start(source: store.voiceSource, language: store.language) }
        .onChange(of: heard) { _, heard in if heard { DSHaptics.success() } }
    }
}

/// Three sentences out loud through the same microphone; the audio becomes the voice profile.
struct VoiceStep: View {
    let store: OnboardingStore

    var body: some View {
        if let voice = store.voice {
            switch voice.phase {
            case .saved: VoiceSaved(voice: voice, savesAnswers: true, onContinue: store.next)
            case .saving: saving
            case .failed(.upload): uploadFailed(voice)
            default: Prompting(voice: voice, source: store.voiceSource, language: store.language, onSkip: store.next)
            }
        } else {
            Color.clear.onAppear(perform: store.next)
        }
    }

    private var saving: some View {
        OnboardingLayout(kicker: L("nativeKickerYourVoice"), title: L("nativeSavingVoice")) {
            ProgressView().controlSize(.large).frame(maxWidth: .infinity).padding(.top, DS.Spacing.section)
        }
    }

    private func uploadFailed(_ voice: VoiceIntroStore) -> some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourVoice"), title: L("nativeVoiceNotSaved"), subtitle: L("nativeVoiceNotSavedBody"),
            button: StepButton(title: L("retry"), action: { Task { await voice.retryUpload() } }),
            secondary: StepButton(title: L("nativeSetUpVoiceLater"), action: store.next)
        ) { EmptyView() }
    }
}

/// Recording the voice again from Settings: the same three sentences, through the Omi when it is
/// connected, else the iPhone. Pushed inside Settings.
public struct VoiceProfileScreen: View {
    let voice: VoiceIntroStore
    let source: VoiceIntroStore.Source
    let language: String
    @Environment(\.dismiss) private var dismiss

    public init(voice: VoiceIntroStore, source: VoiceIntroStore.Source, language: String) {
        self.voice = voice
        self.source = source
        self.language = language
    }

    public var body: some View {
        Group {
            switch voice.phase {
            case .saved: VoiceSaved(voice: voice, onContinue: { dismiss() })
            case .saving:
                OnboardingLayout(kicker: L("nativeKickerYourVoice"), title: L("nativeSavingVoice")) {
                    ProgressView().controlSize(.large).frame(maxWidth: .infinity).padding(.top, DS.Spacing.section)
                }
            case .failed(.upload):
                OnboardingLayout(
                    kicker: L("nativeKickerYourVoice"), title: L("nativeVoiceNotSaved"), subtitle: L("nativeVoiceNotSavedBody"),
                    button: StepButton(title: L("retry"), action: { Task { await voice.retryUpload() } }),
                    secondary: StepButton(title: L("cancel"), action: { dismiss() })
                ) { EmptyView() }
            default:
                Prompting(voice: voice, source: source, language: language, onSkip: { dismiss() })
            }
        }
        .background(DS.Palette.background.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .onDisappear { voice.stop() }
    }
}

/// One sentence at a time, filling in as it is said; on by itself after a pause. When the sample
/// is still short, one more sentence with an example ("Today I ___.").
private struct Prompting: View {
    let voice: VoiceIntroStore
    let source: VoiceIntroStore.Source
    let language: String
    let onSkip: () -> Void

    /// The gap sentences: name, work, free time, and the extra one (literal keys, so the catalog
    /// has them).
    static let templates = ["nativeVoiceGap_name", "nativeVoiceGap_work", "nativeVoiceGap_free"]
    static let extra = "nativeVoiceGap_more"
    /// What to talk about, in the app's language, where the sentences have no translation into
    /// the language the user speaks.
    static let topics = ["nativeVoiceTopic_name", "nativeVoiceTopic_work", "nativeVoiceTopic_free"]
    static let extraTopic = "nativeVoiceTopic_more"

    /// The sentences in the language the user speaks (an English speaker on a German iPhone reads
    /// English sentences, the recognizer listens in English); nil when they are not translated.
    private var spokenTemplates: [String]? {
        let sentences = (Self.templates + [Self.extra]).compactMap { L($0, inLanguage: language) }
        return sentences.count == Self.templates.count + 1 ? sentences : nil
    }

    private var total: Int {
        Self.templates.count
    }

    private var isLast: Bool {
        voice.promptIndex >= total - 1
    }

    /// Without translated sentences: what to talk about for the current one.
    private var topic: String? {
        guard spokenTemplates == nil else { return nil }
        return voice.needsMore ? L(Self.extraTopic) : L(Self.topics[min(voice.promptIndex, total - 1)])
    }

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourVoice"), title: L("nativeLetOmiLearnYourVoice"),
            subtitle: spokenTemplates == nil ? L("nativeVoiceTalkAbout") : L("nativeVoiceReadAloud"),
            // Sentences move on by themselves after a pause; the button is for when they do not.
            button: StepButton(
                title: isLast || voice.needsMore ? L("nativeSaveMyVoice") : L("nextButton"),
                isEnabled: voice.canAdvance,
                action: { Task { await advance() } }
            ),
            secondary: StepButton(title: L("nativeSetUpVoiceLater"), action: {
                voice.stop()
                onSkip()
            })
        ) {
            VStack(alignment: .leading, spacing: DS.Spacing.lg) {
                SentenceSteps(done: voice.promptIndex, total: total, current: voice.match?.progress ?? 0, needsMore: voice.needsMore)
                Text(voice.needsMore ? L("nativeVoiceOneMoreExample") : L(
                    "nativeVoiceSentenceOf", String(min(voice.promptIndex + 1, total)), String(total)
                ))
                .font(.footnote.weight(.semibold))
                .foregroundStyle(DS.Palette.inkSecondary)
                .contentTransition(.numericText())
                VStack(alignment: .leading, spacing: DS.Spacing.md) {
                    if let topic {
                        Text(topic)
                            .font(DS.Typography.sectionTitle)
                            .foregroundStyle(DS.Palette.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let match = voice.match {
                        GapSentenceText(match: match)
                    }
                }
                .frame(minHeight: 120, alignment: .topLeading)
                .id(voice.needsMore ? -1 : voice.promptIndex)
                .transition(.asymmetric(insertion: .move(edge: .bottom).combined(with: .opacity), removal: .identity))
                ListeningLine(voice: voice)
            }
            .onboardingCard(padding: DS.Spacing.xl)
            .padding(.horizontal, DS.Spacing.gutter)
            .animation(DS.Motion.standard, value: voice.promptIndex)
            .animation(DS.Motion.standard, value: voice.needsMore)
        }
        .task {
            // Arriving here directly (debug, or back from a later step) starts the session too.
            await voice.start(source: source, language: language)
            if let sentences = spokenTemplates {
                voice.beginTraining(templates: Array(sentences.prefix(total)), extra: sentences.last)
            } else {
                voice.beginTraining(templates: Array(repeating: "___", count: total), extra: "___")
            }
        }
        // A finished sentence is a clear step: a soft tap as the next one comes up.
        .onChange(of: voice.promptIndex) { _, _ in DSHaptics.soft() }
        .onChange(of: voice.phase) { _, phase in if phase == .saved { DSHaptics.success() } }
    }

    private func advance() async {
        DSHaptics.tap(.light)
        if isLast || voice.needsMore {
            await voice.saveVoice()
        } else {
            voice.nextPrompt()
        }
    }
}

/// "Omi knows your voice": a calm check and one line, then on by itself. In onboarding the answers
/// are kept as memories in the background, as Flutter keeps them by default; nothing to review.
private struct VoiceSaved: View {
    let voice: VoiceIntroStore
    var savesAnswers = false
    let onContinue: () -> Void
    @State private var left = false

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourVoice"), title: L("nativeVoiceSaved"), subtitle: L("nativeVoiceSavedBody"),
            button: StepButton(title: L("continueButton"), action: leave),
            centered: true
        ) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 72, weight: .ultraLight))
                .foregroundStyle(DS.Palette.success)
                .frame(maxWidth: .infinity)
                .padding(.top, DS.Spacing.section)
                .accessibilityHidden(true)
        }
        .task {
            if savesAnswers { Task { await voice.saveAnswers() } }
            try? await Task.sleep(for: .seconds(2))
            leave()
        }
    }

    private func leave() {
        guard !left else { return }
        left = true
        onContinue()
    }
}

/// The live transcript: where the audio comes from, the input level, and every word as it arrives
/// (the newest at the bottom, older ones fading off the top).
struct VoiceLiveCard: View {
    let voice: VoiceIntroStore
    let text: String
    let placeholder: String

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            ListeningLine(voice: voice)
            Group {
                if text.isEmpty {
                    Text(placeholder).foregroundStyle(DS.Palette.inkTertiary)
                } else {
                    Text(String(text.suffix(220))).foregroundStyle(DS.Palette.ink)
                }
            }
            .font(.title3.weight(.medium))
            .lineSpacing(3)
            .frame(maxWidth: .infinity, minHeight: 130, alignment: .topLeading)
            .contentTransition(.opacity)
            .animation(DS.Motion.standard, value: text)
            if case .failed(.input) = voice.phase {
                Label(L("nativeMicrophoneUnavailable"), systemImage: "exclamationmark.triangle.fill")
                    .font(.footnote)
                    .foregroundStyle(DS.Palette.warning)
            }
        }
        .onboardingCard(padding: DS.Spacing.xl)
        .padding(.horizontal, DS.Spacing.gutter)
        .accessibilityElement(children: .combine)
    }
}

/// A row of bars that follows the input level, newest on the right.
struct LevelBars: View {
    let level: Float
    var height: CGFloat = 28
    @State private var history = Array(repeating: Float(0), count: 28)

    var body: some View {
        HStack(alignment: .center, spacing: 3) {
            ForEach(Array(history.enumerated()), id: \.offset) { _, value in
                Capsule()
                    .fill(DS.Palette.ink.opacity(0.2 + Double(min(1, value * 4)) * 0.6))
                    .frame(maxWidth: .infinity)
                    .frame(height: max(2, CGFloat(min(1, value * 4)) * height))
            }
        }
        .frame(height: height)
        .animation(.linear(duration: 0.08), value: history)
        .onChange(of: level) { _, level in
            history.removeFirst()
            history.append(level)
        }
        .accessibilityHidden(true)
    }
}

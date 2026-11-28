import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// The onboarding steps after the voice sample: the Omi's button (ask, hear the answer, double
/// press) and the Apple Watch. A step whose store is missing passes straight on.
struct OmiButtonAndWatchSteps: View {
    let store: OnboardingStore

    var body: some View {
        switch store.step {
        case .askOmi:
            if let tutorial = store.buttonTutorial {
                AskOmiStep(tutorial: tutorial, onContinue: store.next)
            } else {
                Color.clear.onAppear(perform: store.next)
            }
        case .voiceReply:
            VoiceReplyStep(
                mode: store.voiceReplyMode ?? .off,
                lastAnswer: store.buttonTutorial?.askOmi.lastExchange?.answer,
                onChoose: store.chooseVoiceReply,
                onContinue: store.next
            )
            .onAppear(perform: store.showVoiceReply)
        case .doublePress:
            if let tutorial = store.buttonTutorial {
                DoublePressStep(tutorial: tutorial, onContinue: store.next)
            } else {
                Color.clear.onAppear(perform: store.next)
            }
        default:
            WatchStep(watch: store.watch, onContinue: store.next)
        }
    }
}

/// My Devices › How to use your Omi (Flutter's device tutorial, reopened from device settings):
/// the three button lessons again, over the app, closable at any point.
public struct OmiButtonTutorialScreen: View {
    private enum Lesson: CaseIterable { case ask, voiceReply, doublePress }

    let tutorial: ButtonTutorialStore
    @Environment(VoicePlaybackStore.self) private var voice
    @Environment(\.dismiss) private var dismiss
    @State private var lesson = Lesson.ask
    @State private var mode: VoicePlaybackStore.ReplyMode = .headphonesOnly

    public init(tutorial: ButtonTutorialStore) {
        self.tutorial = tutorial
    }

    public var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: DS.Spacing.md) {
                OnboardingProgress(value: Double((Lesson.allCases.firstIndex(of: lesson) ?? 0) + 1) / Double(Lesson.allCases.count))
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .frame(width: 36, height: 36)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(L("close"))
            }
            .frame(height: 36)
            .padding(.horizontal, DS.Spacing.lg)
            .padding(.top, DS.Spacing.sm)
            Group {
                switch lesson {
                case .ask: AskOmiStep(tutorial: tutorial) { lesson = .voiceReply }
                case .voiceReply:
                    VoiceReplyStep(
                        mode: mode, lastAnswer: tutorial.askOmi.lastExchange?.answer,
                        onChoose: { chosen in
                            mode = chosen
                            voice.setReplyMode(chosen)
                        },
                        onContinue: { lesson = .doublePress }
                    )
                case .doublePress: DoublePressStep(tutorial: tutorial) { dismiss() }
                }
            }
            .id(lesson)
            .transition(.opacity)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .animation(.easeOut(duration: 0.28), value: lesson)
        .background(DS.Palette.background.ignoresSafeArea())
        .environment(\.colorScheme, .dark)
        .onAppear { mode = voice.replyMode }
        .onDisappear {
            tutorial.end()
            voice.stop()
        }
    }
}

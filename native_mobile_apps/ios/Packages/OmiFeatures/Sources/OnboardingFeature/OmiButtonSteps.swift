import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// "Ask Omi a question" (Flutter `single_press_step`): press once, speak, pause (or press again).
/// The words show as they are said, the question really goes to Omi, and its answer shows here
/// (the next step can read it aloud). A question without an answer says why; Skip stays.
struct AskOmiStep: View {
    let tutorial: ButtonTutorialStore
    let onContinue: () -> Void
    @Environment(DeviceStore.self) private var devices
    /// The exchange from before this step: only a new one counts.
    @State private var earlier: AskOmiStore.Exchange?
    @State private var started = false

    private var ask: AskOmiStore {
        tutorial.askOmi
    }

    private var answer: AskOmiStore.Exchange? {
        guard started, let exchange = ask.lastExchange, exchange != earlier, ask.phase == .idle else { return nil }
        return exchange
    }

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourOmi"),
            title: answer == nil ? L("nativePressOnceTitle") : L("nativeOmiAnswered"),
            subtitle: answer == nil ? L("nativePressOnceShort") : nil,
            button: StepButton(title: L("continueButton"), isEnabled: answer != nil, action: onContinue),
            secondary: answer == nil ? StepButton(title: L("skip"), action: onContinue) : nil
        ) {
            if let answer {
                AnswerCard(exchange: answer)
            } else {
                PendantImage(size: 120) {
                    Text(L("deviceOnboardingAllSetSinglePressBadge"))
                        .font(.footnote.weight(.bold).monospacedDigit())
                        .foregroundStyle(DS.Palette.onAccent)
                        .padding(.horizontal, DS.Spacing.sm)
                        .padding(.vertical, DS.Spacing.xxs)
                        .background(DS.Palette.ink, in: Capsule())
                }
                live
            }
        }
        .onAppear {
            earlier = ask.lastExchange
            started = true
            tutorial.begin(.ask)
        }
        .onDisappear { tutorial.end(.ask) }
        .onChange(of: answer != nil) { _, answered in if answered { DSHaptics.success() } }
        .connectsPairedOmi()
        .animation(DS.Motion.standard, value: ask.phase)
        .animation(DS.Motion.standard, value: ask.question)
    }

    /// What happens right now: a hint, the words of the question, Omi thinking, or why it failed.
    @ViewBuilder
    private var live: some View {
        switch ask.phase {
        case .listening:
            QuestionCard(label: L("nativeListening"), question: ask.question, placeholder: L("nativeAskYourQuestion"), thinking: false)
        case .sending:
            QuestionCard(label: L("nativeOmiThinking"), question: ask.question, placeholder: "", thinking: true)
        case .idle:
            Group {
                if devices.connection != .connected {
                    StatusLine(L("nativeOmiOnAndNearby"), "antenna.radiowaves.left.and.right.slash", DS.Palette.warning).view
                } else if ask.problem == .nothingHeard {
                    StatusLine(L("nativeAskNothingHeard"), "ear", DS.Palette.warning).view
                } else if ask.problem == .noAnswer {
                    StatusLine(L("nativeAskNoAnswer"), "exclamationmark.bubble", DS.Palette.warning).view
                } else {
                    StatusLine(L("nativePressOnceToAsk"), "hand.tap", DS.Palette.inkSecondary).view
                }
            }
            .padding(.horizontal, DS.Spacing.gutter)
        }
    }
}

/// The question as it is spoken (or sent), in quotes, with a small label above it.
private struct QuestionCard: View {
    let label: String
    let question: String
    let placeholder: String
    let thinking: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            HStack(spacing: DS.Spacing.sm) {
                if thinking {
                    ProgressView().controlSize(.small)
                } else {
                    Circle().fill(DS.Palette.live).frame(width: 7, height: 7)
                }
                Text(label).font(.footnote.weight(.semibold)).foregroundStyle(DS.Palette.inkSecondary)
            }
            Text(question.isEmpty ? placeholder : "\u{201C}\(question)\u{201D}")
                .font(.title3.weight(.medium))
                .foregroundStyle(question.isEmpty ? DS.Palette.inkTertiary : DS.Palette.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .contentTransition(.opacity)
        }
        .onboardingCard(padding: DS.Spacing.xl)
        .padding(.horizontal, DS.Spacing.gutter)
        .accessibilityElement(children: .combine)
    }
}

/// The question, a hairline, Omi's answer.
private struct AnswerCard: View {
    let exchange: AskOmiStore.Exchange

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            if !exchange.question.isEmpty {
                Text("\u{201C}\(exchange.question)\u{201D}")
                    .font(.subheadline)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(2)
                Rectangle().fill(DS.Palette.ink.opacity(0.08)).frame(height: 0.5)
            }
            Text(VoicePlaybackStore.speakableText(exchange.answer))
                .font(.body)
                .foregroundStyle(DS.Palette.ink)
                .lineLimit(9)
        }
        .onboardingCard(padding: DS.Spacing.xl)
        .padding(.horizontal, DS.Spacing.gutter)
        .accessibilityElement(children: .combine)
    }
}

/// "Customize double tap" (Flutter `double_press_config_step`): the same choice as My Devices ›
/// Controls › Double tap, then a press to try it. Practice presses only count; nothing ends or mutes.
struct DoublePressStep: View {
    let tutorial: ButtonTutorialStore
    let onContinue: () -> Void
    @Environment(DeviceStore.self) private var devices

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerYourOmi"),
            title: L("nativePressTwiceTitle"),
            subtitle: L("nativeDoublePressShort"),
            button: StepButton(title: L("continueButton"), action: onContinue)
        ) {
            RowList {
                row(.endConversation, "stop.circle", L("nativePressTwiceEnd"))
                row(.toggleMute, "mic.slash", L("nativePressTwiceMute"))
                row(.star, "star", L("nativePressTwiceStar"))
            }
            hint.padding(.horizontal, DS.Spacing.gutter)
        }
        .onAppear { tutorial.begin(.doublePress) }
        .onDisappear { tutorial.end(.doublePress) }
        .onChange(of: tutorial.doublePresses) { _, count in if count > 0 { DSHaptics.success() } }
        .connectsPairedOmi()
    }

    private func row(_ action: DoubleTapAction, _ symbol: String, _ title: String) -> some View {
        ChoiceRow(symbol: symbol, title: title, selected: tutorial.doublePressAction == action) {
            tutorial.choose(action)
        }
        .accessibilityIdentifier("onboarding.doublePress.\(action)")
    }

    private var hint: some View {
        let line = if devices.connection != .connected {
            StatusLine(L("nativeOmiOnAndNearby"), "antenna.radiowaves.left.and.right.slash", DS.Palette.warning)
        } else if tutorial.singlePressHint {
            StatusLine(L("nativeDoublePressSingleHint"), "hand.tap", DS.Palette.warning)
        } else if tutorial.doublePresses > 0 {
            StatusLine(L("nativeDoublePressWorked"), "checkmark.circle.fill", DS.Palette.success)
        } else {
            StatusLine(L("nativePressTwiceTry"), "hand.tap", DS.Palette.inkSecondary)
        }
        return line.view.animation(DS.Motion.standard, value: line.text)
    }
}

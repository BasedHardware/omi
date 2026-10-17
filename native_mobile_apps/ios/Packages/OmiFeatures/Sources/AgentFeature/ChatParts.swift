import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// One message in the thread, as in Messages: yours in soft blue on the right, Omi's on the card
/// color on the left, a long answer in a few bubbles (split at its paragraphs), bubbles of one
/// sender grouped, Omi's avatar beside the last bubble of its group. What Omi did (steps, the
/// cards the app draws) sits above its answer in Omi's column, sources and the follow-up below it
/// (only on the newest answer; an older one folds its sources into "2 sources").
/// Everything you can do with a message is in its long-press menu (reply, copy, rate, delete);
/// a tap shows when it was sent; a swipe toward the middle replies.
struct MessageBubble: View {
    let message: ChatMessage
    let isStreaming: Bool
    /// The newest answer: it keeps its source chips and offers its follow-up question.
    var isLatest = false
    /// Where the message sits in its group of one sender.
    var position = ChatGrouping.Position.alone
    /// Nothing typed in the composer (the follow-up question only shows then).
    var draftIsEmpty = true
    /// The failure row's retry (on a failed answer).
    var onRetry: () -> Void = {}
    /// A question whose answer failed: "Try again" in its menu.
    var onTryAgain: (() -> Void)?
    var onReply: () -> Void = {}
    var onDelete: () -> Void = {}
    var onOpenConversation: ((String) -> Void)?
    var onUpgrade: (() -> Void)?
    var onFollowUp: (String) -> Void = { _ in }
    /// A prepared answer on a question card: sent as if the user had typed it.
    var onSend: (String) -> Void = { _ in }
    /// "Ask about it" on a sent file: a question about it waits in the composer.
    var onAskAboutFile: ((ChatFile) -> Void)?
    @Environment(VoicePlaybackStore.self) private var voice
    @Environment(\.chatBubbleWidth) private var bubbleWidth
    @State private var showsTime = false
    @State private var showsSources = false

    var body: some View {
        if message.sender == .user { question } else { answer }
    }

    // MARK: Yours

    private var question: some View {
        let (quote, text) = ChatQuote.split(message.text)
        return VStack(alignment: .trailing, spacing: DS.Spacing.xs) {
            if !message.files.isEmpty { MessageFiles(files: message.files, onAsk: onAskAboutFile) }
            if !text.isEmpty {
                VStack(alignment: .leading, spacing: DS.Spacing.xs + 2) {
                    if let quote { QuoteLine(quote: quote, onInk: true) }
                    Text(verbatim: text)
                        .font(DS.Typography.bubble)
                        .foregroundStyle(DS.Palette.onBubbleUser)
                }
                .chatBubble(DS.Palette.bubbleUser, isUser: true, position: position)
                .contextMenu { questionMenu(text) }
                .onTapGesture(perform: toggleTime)
                .frame(maxWidth: bubbleWidth, alignment: .trailing)
            }
            if showsTime { timeLabel }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .accessibilityIdentifier("chat.question")
    }

    @ViewBuilder
    private func questionMenu(_ text: String) -> some View {
        Section(Self.time(message.createdAt)) {
            Button(action: onReply) { Label(L("reply"), systemImage: "arrowshape.turn.up.left") }
            Button {
                UIPasteboard.general.string = text
                DSHaptics.success()
            } label: {
                Label(L("copy"), systemImage: "doc.on.doc")
            }
            if let onTryAgain {
                Button(action: onTryAgain) { Label(L("tryAgain"), systemImage: "arrow.clockwise") }
            }
        }
        Button(action: onDelete) { Label(L("nativeChatHide"), systemImage: "eye.slash") }
    }

    // MARK: Omi's

    private var answer: some View {
        // Keep-alive frames ("Preparing response…") say nothing about the work.
        let steps = message.steps.filter { !AgentStore.isHeartbeat($0) }
        let citations = message.citations()
        let extras = ChatAnswerExtras.shown(
            ChatAnswerExtras.Answer(
                isLatest: isLatest, isStreaming: isStreaming, failed: answerFailure != nil, citations: citations.count,
                hasFollowUp: message.followUp != nil && message.failure == nil && !message.isServiceFailure
            ),
            draftIsEmpty: draftIsEmpty, isSpeaking: voice.playingID == message.id, sourcesExpanded: showsSources
        )
        return VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            if !steps.isEmpty { StepList(steps: steps, isWorking: isStreaming && message.text.isEmpty).omiColumn() }
            AnswerCards(message: message).omiColumn()
            ChatBlocks(message: message, onSend: onSend, onOpenConversation: onOpenConversation).omiColumn()
            if message.text.isEmpty, isStreaming, steps.isEmpty {
                omiRow(isLast: true) { TypingBubble() }
            } else if let failure = answerFailure {
                // No reply came through (the backend also streams canned failures as text).
                failureRow(failure).omiColumn()
            } else if message.kind == .daySummary, !message.text.isEmpty {
                DaySummaryCard(message: message).omiColumn()
            } else if !message.text.isEmpty, !ChatBlockLayout.blocksReplaceBody(message) {
                answerBubbles
            } else {
                // The cards carry the turn; only the lines they cannot draw stay as text.
                ChatBlockFallbacks(lines: ChatBlockLayout.fallbackLines(message.blocks)).omiColumn()
            }
            Group {
                if let chart = message.chart, answerFailure == nil { ChartCard(chart: chart) }
                if message.failure == .interrupted {
                    failureRow(.interrupted)
                } else if message.failure == .stopped {
                    Label(L("nativeChatStopped"), systemImage: "stop.circle")
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                }
                if extras.stopReading { stopReading }
                switch extras.sources {
                case .chips: CitationChips(citations: citations, onOpen: onOpenConversation)
                case let .collapsed(count): sourcesLine(count)
                case .none: EmptyView()
                }
                if showsTime { timeLabel }
                if extras.followUp, let followUp = message.followUp { followUpChip(followUp) }
            }
            .omiColumn()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("chat.answer")
    }

    /// The answer in a few bubbles, split where its paragraphs end; each one's menu is the whole answer's.
    private var answerBubbles: some View {
        let parts = ChatBubbleSplit.split(message.text)
        return VStack(alignment: .leading, spacing: Self.groupSpacing) {
            ForEach(Array(parts.enumerated()), id: \.offset) { index, part in
                let isLastPart = index == parts.count - 1
                let place = ChatGrouping.Position(isFirst: position.isFirst && index == 0, isLast: position.isLast && isLastPart)
                omiRow(isLast: place.isLast) {
                    MarkdownBlocks(part, font: DS.Typography.bubble, selectable: false)
                        .foregroundStyle(DS.Palette.ink)
                        .chatBubble(DS.Palette.bubbleAssistant, isUser: false, position: place)
                        .contextMenu {
                            AnswerMenu(message: message, onReply: onReply, onDelete: onDelete, title: Self.time(message.createdAt))
                        }
                        .onTapGesture(perform: toggleTime)
                }
            }
        }
    }

    /// Between the bubbles of one group (and the parts of one answer).
    static let groupSpacing: CGFloat = 3

    /// One bubble in Omi's column: the avatar beside the group's last one.
    private func omiRow(isLast: Bool, @ViewBuilder bubble: () -> some View) -> some View {
        HStack(alignment: .bottom, spacing: OmiAvatar.column - DS.Size.chatAvatar) {
            OmiAvatar(shows: isLast)
            bubble().frame(maxWidth: bubbleWidth, alignment: .leading)
            Spacer(minLength: 0)
        }
    }

    /// An older answer's sources, folded: "2 sources", a tap shows the chips.
    private func sourcesLine(_ count: Int) -> some View {
        Button {
            DSHaptics.selection()
            withAnimation(DS.Motion.snappy) { showsSources = true }
        } label: {
            HStack(spacing: DS.Spacing.xs) {
                Image(systemName: "bubble.left").imageScale(.small)
                Text(count == 1 ? L("nativeChatOneSource") : L("nativeChatSourcesCount", String(count)))
            }
            .font(DS.Typography.caption)
            .foregroundStyle(DS.Palette.inkTertiary)
            .padding(.horizontal, DS.Spacing.xs)
            .frame(minHeight: 24)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("chat.sources")
    }

    /// The failure shown instead of the answer (an interrupted or stopped answer keeps its text).
    private var answerFailure: ChatMessage.Failure? {
        switch message.failure {
        case .couldNotAnswer, .offline, .timeout, .quotaExceeded: message.failure
        case .interrupted, .stopped: nil
        case nil: message.isServiceFailure ? .couldNotAnswer : nil
        }
    }

    /// While this answer is read aloud, stopping is one tap away.
    private var stopReading: some View {
        Button {
            DSHaptics.selection()
            voice.toggle(message)
        } label: {
            HStack(spacing: DS.Spacing.xs) {
                if voice.isLoading { ProgressView().controlSize(.mini) } else { Image(systemName: "stop.fill").imageScale(.small) }
                Text(L("nativeStopReading"))
            }
            .font(DS.Typography.caption.weight(.medium))
            .foregroundStyle(DS.Palette.ink)
            .padding(.horizontal, DS.Spacing.md)
            .frame(minHeight: 30)
            .background(DS.Palette.fill, in: Capsule())
        }
        .buttonStyle(.plain)
        .transition(.opacity)
    }

    private func followUpChip(_ question: String) -> some View {
        Button {
            DSHaptics.tap()
            onFollowUp(question)
        } label: {
            Text(question.split(whereSeparator: \.isWhitespace).joined(separator: " "))
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.ink)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
                .padding(.horizontal, DS.Spacing.lg)
                .padding(.vertical, DS.Spacing.sm)
                .frame(minHeight: 40)
                .overlay { Capsule().stroke(DS.Palette.hairline, lineWidth: 1) }
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("chat.followUp")
    }

    private func failureRow(_ failure: ChatMessage.Failure) -> some View {
        let text = switch failure {
        case .offline: L("chatReplyOffline")
        case .timeout: L("chatReplyTimeout")
        case .quotaExceeded: L("chatQuotaExceededReply")
        case .interrupted: L("nativeChatInterrupted")
        case .couldNotAnswer, .stopped: L("nativeChatCouldNotAnswer")
        }
        return HStack(spacing: DS.Spacing.md) {
            Label(text, systemImage: failure == .quotaExceeded ? "sparkles" : "exclamationmark.triangle.fill")
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
            if failure == .quotaExceeded {
                if let onUpgrade {
                    Button(L("upgrade"), action: onUpgrade)
                        .font(DS.Typography.callout.weight(.semibold))
                        .foregroundStyle(DS.Palette.agent)
                }
            } else {
                Button(L("retry"), action: onRetry)
                    .font(DS.Typography.callout.weight(.semibold))
                    .foregroundStyle(DS.Palette.agent)
            }
        }
    }

    // MARK: Shared

    private var timeLabel: some View {
        Text(Self.time(message.createdAt))
            .font(DS.Typography.micro.weight(.regular))
            .foregroundStyle(DS.Palette.inkTertiary)
            .padding(.horizontal, DS.Spacing.xs)
            .transition(.opacity)
    }

    private func toggleTime() {
        DSHaptics.selection()
        withAnimation(DS.Motion.snappy) { showsTime.toggle() }
    }

    /// "14:05" today, "Tue 14:05" this week, "3 Oct, 14:05" before.
    static func time(_ date: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        if calendar.isDate(date, inSameDayAs: now) { return date.formatted(date: .omitted, time: .shortened) }
        if now.timeIntervalSince(date) < 6 * 86400 { return date.formatted(.dateTime.weekday(.abbreviated).hour().minute()) }
        return date.formatted(.dateTime.day().month(.abbreviated).hour().minute())
    }
}

/// What a reply refers to, at the top of its bubble: who, and the first words.
struct QuoteLine: View {
    let quote: ChatQuote
    /// In your bubble rather than on the page.
    var onInk = false

    var body: some View {
        let color = onInk ? DS.Palette.onBubbleUser.opacity(0.7) : DS.Palette.inkSecondary
        HStack(alignment: .top, spacing: DS.Spacing.sm) {
            Capsule().fill(color.opacity(0.6)).frame(width: 2)
            (Text(quote.quotesOmi ? "Omi" : L("you")).fontWeight(.semibold) + Text(verbatim: "  " + quote.snippet))
                .font(DS.Typography.caption)
                .foregroundStyle(color)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }
}

/// Omi is thinking: three dots in a bubble until the first words arrive.
struct TypingBubble: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: reduceMotion)) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.1) / 1.1
            HStack(spacing: 5) {
                ForEach(0 ..< 3, id: \.self) { index in
                    let wave = (sin((phase - Double(index) * 0.33) * 2 * .pi) + 1) / 2
                    Circle()
                        .fill(DS.Palette.inkTertiary)
                        .frame(width: 7, height: 7)
                        .scaleEffect(reduceMotion ? 1 : 0.7 + wave * 0.5)
                        .opacity(reduceMotion ? 0.7 : 0.35 + wave * 0.65)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 13)
            .background(DS.Palette.bubbleAssistant, in: ChatBubbleShape(isUser: false, position: .alone))
        }
        .transition(.scale(scale: 0.8, anchor: .bottomLeading).combined(with: .opacity))
        .accessibilityLabel(L("nativeChatOmiIsTyping"))
        .accessibilityIdentifier("chat.typing")
    }
}

/// "Today", "Yesterday", "Monday", "3 Oct": a quiet line where a new day starts in the thread.
struct DayDivider: View {
    let date: Date

    var body: some View {
        Text(Self.title(ChatDay(date)))
            .font(DS.Typography.micro)
            .foregroundStyle(DS.Palette.inkTertiary)
            .frame(maxWidth: .infinity)
            .padding(.top, DS.Spacing.sm)
            .accessibilityAddTraits(.isHeader)
    }

    static func title(_ day: ChatDay) -> String {
        switch day {
        case .today: L("today")
        case .yesterday: L("yesterday")
        case let .weekday(date): date.formatted(.dateTime.weekday(.wide))
        case let .date(date, true): date.formatted(.dateTime.day().month(.abbreviated).year())
        case let .date(date, false): date.formatted(.dateTime.day().month(.wide))
        }
    }
}

/// The agent's tool steps: done ones checked, the current one spinning.
public struct StepList: View {
    /// Each distinct step once, in the order it first happened, with how often Omi did it:
    /// an agent searching six times reads as one line, not six.
    let steps: [(title: String, count: Int)]
    let isWorking: Bool

    public init(steps: [String], isWorking: Bool) {
        var grouped: [(title: String, count: Int)] = []
        for step in steps where !step.isEmpty {
            if let index = grouped.firstIndex(where: { $0.title == step }) {
                grouped[index].count += 1
            } else {
                grouped.append((step, 1))
            }
        }
        self.steps = grouped
        self.isWorking = isWorking
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                HStack(spacing: DS.Spacing.sm) {
                    if isWorking, index == steps.count - 1 {
                        ProgressView().controlSize(.mini)
                    } else {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(DS.Palette.agent)
                    }
                    Text(step.title)
                    if step.count > 1 {
                        Text(verbatim: "×\(step.count)").foregroundStyle(DS.Palette.inkTertiary).monospacedDigit()
                    }
                }
                .font(DS.Typography.caption)
                .foregroundStyle(DS.Palette.inkSecondary)
            }
        }
    }
}

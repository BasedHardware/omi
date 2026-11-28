import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// One "For you" row: an icon in a small tinted circle, a title, a one-line subtitle, a chevron.
/// One accent per row (the icon); text stays ink and secondary ink. Grows with Dynamic Type.
struct ForYouRow: View {
    struct Content {
        enum Tint { case agent, attention, neutral }

        let symbol: String
        let tint: Tint
        let title: String
        let subtitle: String
        /// Omi is working: the icon breathes.
        var pulses = false
    }

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    /// The icon circle grows with the text (a little), so large sizes keep their balance.
    @ScaledMetric(relativeTo: .body) private var scaledIcon: CGFloat = 32
    let content: Content
    let isTappable: Bool
    let action: () -> Void

    /// 32 pt at the default size, at most 44 pt.
    static func circleSize(_ scaled: CGFloat) -> CGFloat {
        min(scaled, 44)
    }

    var body: some View {
        if isTappable {
            Button(action: action) { label }
                .buttonStyle(.hapticTap)
                .accessibilityElement(children: .combine)
        } else {
            label.accessibilityElement(children: .combine)
        }
    }

    private var label: some View {
        // Centered while titles are short; at accessibility sizes the icon stays with the first line.
        HStack(alignment: dynamicTypeSize.isAccessibilitySize ? .top : .center, spacing: DS.Spacing.md) {
            icon
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                Text(content.title)
                    .font(DS.Typography.cardTitle)
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(dynamicTypeSize.isAccessibilitySize ? 4 : 2)
                    .fixedSize(horizontal: false, vertical: true)
                if !content.subtitle.isEmpty {
                    Text(content.subtitle)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? 3 : 1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .multilineTextAlignment(.leading)
        .padding(.vertical, DS.Spacing.sm + 2)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
    }

    private var icon: some View {
        // A thin line glyph, no tinted circle: only Omi's own work carries the accent.
        let color: Color = content.tint == .agent ? DS.Palette.agent : DS.Palette.inkSecondary
        let iconSize = Self.circleSize(scaledIcon)
        return Image(systemName: content.symbol)
            .font(.system(size: iconSize * 0.56, weight: .regular))
            .foregroundStyle(color)
            .symbolEffect(.pulse, isActive: content.pulses)
            .frame(width: iconSize, height: iconSize)
            .accessibilityHidden(true)
    }
}

extension ForYouRow.Content {
    /// The words and icon for one attention item.
    @MainActor
    init(_ item: HomeAttention.Item, taskSource: (ActionItem) -> String?) {
        switch item {
        case let .finished(run):
            let result = Self.firstLine(run.state)
            self.init(
                symbol: "sparkles", tint: .agent, title: run.taskTitle,
                subtitle: result.isEmpty ? L("nativeOmiFinished") : "\(L("nativeOmiFinished")) · \(result)"
            )
        case let .finishedGroup(runs):
            self.init(
                symbol: "sparkles", tint: .agent, title: L("nativeHomeOmiFinishedCount", String(runs.count)),
                subtitle: runs.map(\.taskTitle).joined(separator: " · ")
            )
        case let .working(run):
            let step: String = if case let .working(step) = run.state, !step.isEmpty { step } else { L("nativeOmiOnIt") }
            self.init(symbol: "sparkles", tint: .agent, title: run.taskTitle, subtitle: step, pulses: true)
        case let .recommendation(recommendation):
            // Asked, in the backend's own next-action words: "Send Anna the Thursday follow-up?"
            self.init(symbol: "flag", tint: .attention, title: recommendation.question, subtitle: recommendation.whyNow)
        case let .task(card):
            self.init(symbol: "checklist", tint: .neutral, title: card.task.description, subtitle: taskSource(card.task) ?? "")
        case let .tidyUp(proposal):
            self.init(symbol: "sparkles", tint: .agent, title: TidyUpWording.title(proposal), subtitle: L("nativeTidyUpSubtitle"))
        case let .needsHelp(run):
            // Why it stopped, in plain words ("Omi got stuck and stopped").
            let reason = run.failure.map(AgentWording.words) ?? L("nativeHomeNeedsYourHelp")
            self.init(symbol: "hand.raised", tint: .attention, title: run.taskTitle, subtitle: reason)
        case let .omiAsks(pending):
            let presentation = OmiAsksPresentation(pending)
            self.init(symbol: "questionmark.bubble", tint: .agent, title: presentation.title, subtitle: presentation.subtitle)
        case let .speakerPrompt(prompt):
            self.init(
                symbol: "person.wave.2.fill",
                tint: .neutral,
                title: SpeakerPromptCard.question(prompt),
                subtitle: Self.context(prompt)
            )
        case let .nudge(nudge):
            self.init(symbol: "lightbulb", tint: .neutral, title: nudge.title, subtitle: Self.oneLine(nudge.body))
        case .siriTip:
            self.init(symbol: "mic", tint: .neutral, title: L("nativeHomeSiriTitle"), subtitle: L("nativeHomeSiriSubtitle"))
        case let .connect(id):
            self.init(
                symbol: "link", tint: .agent, title: L("nativeForYouConnectTitle", ConnectSuggestion.name(id)),
                subtitle: ConnectSuggestion.purpose(id)
            )
        }
    }

    private static func firstLine(_ state: AgentStore.RunState) -> String {
        guard case let .done(result) = state else { return "" }
        // Results are Markdown: the first line without its heading or emphasis marks.
        // The agent often opens with a plan ("I'll start by …"); the first line after it says what it did.
        let lines = result.split(whereSeparator: \.isNewline).map(String.init).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        let preamble = ["I'll ", "I will ", "Let me ", "First, I'll "]
        let line = lines.first { line in !preamble.contains { line.hasPrefix($0) } } ?? lines.first ?? ""
        return line.trimmingCharacters(in: CharacterSet(charactersIn: "#*_> ").union(.whitespaces))
    }

    private static func oneLine(_ text: String) -> String {
        text.replacingOccurrences(of: "\n", with: " ")
    }

    private static func context(_ prompt: SpeakerPrompt) -> String {
        let title = prompt.conversationTitle.isEmpty ? L("untitledConversation") : prompt.conversationTitle
        return prompt.excerpt.isEmpty ? title : "“\(oneLine(prompt.excerpt))” · \(title)"
    }
}

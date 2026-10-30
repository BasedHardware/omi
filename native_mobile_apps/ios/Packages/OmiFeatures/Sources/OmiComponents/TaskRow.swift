import OmiCore
import OmiDesign
import SwiftUI

/// One task: check circle, text, then quiet lines: due date and where it came from (the
/// conversation's emoji and title, tappable), the words it was extracted from, Omi's status;
/// "Omi takes over" at the end.
public struct TaskRow: View {
    let task: ActionItem
    let source: String?
    let sourceEmoji: String?
    let quote: String?
    let onOpenSource: (() -> Void)?
    let onToggle: () -> Void
    let onHandOver: (() -> Void)?
    /// Set when Omi worked or works on this task; tapping it opens Omi's work (`onHandOver`).
    let agentStatus: AgentTaskStatus?

    /// `source` is the conversation's title (with `sourceEmoji`), `quote` one line of what was
    /// said; `onOpenSource` opens the conversation.
    public init(
        _ task: ActionItem,
        source: String? = nil,
        sourceEmoji: String? = nil,
        quote: String? = nil,
        onOpenSource: (() -> Void)? = nil,
        agentStatus: AgentTaskStatus? = nil,
        onToggle: @escaping () -> Void,
        onHandOver: (() -> Void)? = nil
    ) {
        self.task = task
        self.source = source
        self.sourceEmoji = sourceEmoji
        self.quote = quote
        self.onOpenSource = onOpenSource
        self.agentStatus = agentStatus
        self.onToggle = onToggle
        self.onHandOver = onHandOver
    }

    public var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            Button {
                if !task.isCompleted { DSHaptics.success() }
                onToggle()
            } label: {
                Image(systemName: task.isCompleted ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(task.isCompleted ? DS.Palette.success : DS.Palette.inkTertiary)
                    .contentTransition(.symbolEffect(.replace))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(task.isCompleted ? L("nativeMarkOpen") : L("nativeMarkDone"))

            VStack(alignment: .leading, spacing: 3) {
                Text(task.description)
                    .font(DS.Typography.body)
                    .strikethrough(task.isCompleted, color: DS.Palette.inkTertiary)
                    .foregroundStyle(task.isCompleted ? DS.Palette.inkTertiary : DS.Palette.ink)
                if hasMeta { meta }
                if let quote, !quote.isEmpty {
                    Text(verbatim: "\u{201C}\(quote)\u{201D}")
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .lineLimit(1)
                }
                if let agentStatus {
                    AgentStatusChip(status: agentStatus, action: onHandOver)
                        .padding(.top, DS.Spacing.xxs)
                }
            }
            Spacer(minLength: 0)
            // Hand-over as one small round button at the end, not a labeled chip under every task.
            if agentStatus == nil, let onHandOver, !task.isCompleted {
                HandOverButton(action: onHandOver)
                    .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 5 }
                    .accessibilityIdentifier("task.handOver.\(task.id)")
            }
        }
        .padding(.vertical, DS.Spacing.xs)
    }

    private var hasMeta: Bool {
        task.dueAt != nil || source != nil
    }

    /// Due date (red when overdue) and the source conversation, which stays quiet either way.
    private var meta: some View {
        HStack(spacing: DS.Spacing.xs) {
            if let due = task.dueAt {
                Text(Formatting.relativeDay(due))
                    .foregroundStyle(isOverdue ? DS.Palette.live : DS.Palette.inkSecondary)
                    .fixedSize()
            }
            if task.dueAt != nil, source != nil {
                Text(verbatim: "·").foregroundStyle(DS.Palette.inkTertiary)
            }
            if let source {
                let label = Text(sourceEmoji.map { "\($0) \(source)" } ?? source).foregroundStyle(DS.Palette.inkSecondary)
                if let onOpenSource {
                    Button(action: onOpenSource) { label }
                        .buttonStyle(.plain)
                        .accessibilityLabel(L("nativeFromConversation", source))
                        .accessibilityIdentifier("task.source.\(task.id)")
                } else {
                    label
                }
            }
        }
        .font(DS.Typography.caption)
        .lineLimit(1)
    }

    private var isOverdue: Bool {
        guard let due = task.dueAt, !task.isCompleted else { return false }
        return due < Calendar.current.startOfDay(for: .now)
    }
}

public extension Formatting {
    /// "Today", "Tomorrow", "Yesterday", or "Fri, 9 Oct".
    static func relativeDay(_ date: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        if calendar.isDate(date, inSameDayAs: now) { return L("today") }
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(date, inSameDayAs: tomorrow) {
            return L("nativeTomorrow")
        }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now), calendar.isDate(date, inSameDayAs: yesterday) {
            return L("yesterday")
        }
        return date.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated))
    }
}

/// Omi's state on a task; opens the run (live progress or result) when tapped.
struct AgentStatusChip: View {
    let status: AgentTaskStatus
    let action: (() -> Void)?

    var body: some View {
        // One quiet line: the colored glyph says the state, the words say what Omi is doing or why
        // it stopped, and while it works, how long ago that was. An overdue date stays louder.
        let label = HStack(alignment: .firstTextBaseline, spacing: 5) {
            Image(systemName: status.symbol)
                .font(.system(size: 11, weight: .regular))
                .foregroundStyle(status.tint)
                .symbolEffect(.pulse, isActive: status.kind == .working && status.isLive)
                .accessibilityHidden(true)
            Text(status.title).lineLimit(2)
            if let age = status.age() {
                Text(verbatim: "· \(age)").foregroundStyle(DS.Palette.inkTertiary).fixedSize()
            }
        }
        .font(DS.Typography.caption)
        .foregroundStyle(DS.Palette.inkSecondary)
        .multilineTextAlignment(.leading)
        .contentShape(Rectangle())
        if let action {
            Button(action: action) { label }.buttonStyle(.hapticTap)
        } else {
            label
        }
    }
}

/// "Omi takes over" as a thin sparkles glyph at the end of a task row (Omi blue: Omi's work).
struct HandOverButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "sparkles")
                .font(.system(size: 16, weight: .regular))
                .foregroundStyle(DS.Palette.agent)
                .frame(width: 36, height: 36)
                .contentShape(Rectangle())
        }
        .buttonStyle(.hapticTap)
        .accessibilityLabel(L("nativeOmiTakesOver"))
    }
}

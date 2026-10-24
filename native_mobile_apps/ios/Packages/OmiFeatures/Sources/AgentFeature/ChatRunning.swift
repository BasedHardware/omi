import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// "Running now", pinned under the chat tab's header: every hand-over Omi is working on, with what
/// it is doing right now and for how long, so the state never scrolls away in the thread. Tap
/// opens the run, "Stop" ends it. Not there while nothing runs.
struct RunningStrip: View {
    @Environment(AgentStore.self) private var agent
    let onOpen: (AgentStore.Run) -> Void

    var body: some View {
        let runs = agent.activeRuns
        if !runs.isEmpty {
            VStack(spacing: 0) {
                ForEach(Array(runs.enumerated()), id: \.element.id) { index, run in
                    if index > 0 { OmiHairline(leading: DS.Spacing.lg + 22) }
                    RunningRow(run: run, onOpen: { onOpen(run) }, onStop: { agent.stop(run.id) })
                }
            }
            .background(DS.Palette.cardRaised, in: RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous).strokeBorder(DS.Palette.cardStroke, lineWidth: 1)
            }
            .transition(.move(edge: .top).combined(with: .opacity))
            .accessibilityElement(children: .contain)
            .accessibilityLabel(L("nativeChatRunningNow"))
            .accessibilityIdentifier("chat.running")
        }
    }
}

private struct RunningRow: View {
    @Environment(AgentStore.self) private var agent
    let run: AgentStore.Run
    let onOpen: () -> Void
    let onStop: () -> Void

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            Button(action: onOpen) {
                HStack(spacing: DS.Spacing.md) {
                    Image(systemName: agent.deviceToolRequests[run.id] == nil ? "sparkles" : "questionmark.bubble")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(DS.Palette.agent)
                        .symbolEffect(.pulse, isActive: agent.deviceToolRequests[run.id] == nil)
                        .frame(width: 22)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(run.taskTitle)
                            .font(DS.Typography.callout.weight(.medium))
                            .foregroundStyle(DS.Palette.ink)
                            .lineLimit(1)
                        HStack(spacing: DS.Spacing.xs) {
                            Text(detail).lineLimit(1)
                            Text(verbatim: "·")
                            TimelineView(.periodic(from: run.startedAt, by: 1)) { context in
                                Text(Self.elapsed(from: run.startedAt, to: context.date)).monospacedDigit()
                            }
                        }
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint(L("nativeChatRunOpenHint"))
            Button(L("nativeChatRunStop"), action: onStop)
                .font(DS.Typography.caption.weight(.semibold))
                .foregroundStyle(DS.Palette.ink)
                .padding(.horizontal, DS.Spacing.md)
                .frame(minHeight: 32)
                .overlay { Capsule().strokeBorder(DS.Palette.hairline, lineWidth: 1) }
                .buttonStyle(.plain)
                .accessibilityIdentifier("chat.running.stop.\(run.id)")
        }
        .padding(.horizontal, DS.Spacing.lg)
        .padding(.vertical, DS.Spacing.sm + 2)
    }

    /// What Omi is doing, in plain words; a question waiting comes first.
    private var detail: String {
        if agent.deviceToolRequests[run.id] != nil { return L("nativeChatRunWaitsForYou") }
        if case let .working(step) = run.state, let words = AgentWording.step(step) { return words }
        if let last = run.steps.last(where: { AgentWording.step($0) != nil }).flatMap(AgentWording.step) { return last }
        return L("nativeChatRunStarting")
    }

    /// "0:42", "12:05", "1:02:10".
    static func elapsed(from start: Date, to now: Date) -> String {
        let seconds = max(0, Int(now.timeIntervalSince(start)))
        let (hours, minutes, rest) = (seconds / 3600, seconds / 60 % 60, seconds % 60)
        return hours > 0 ? String(format: "%d:%02d:%02d", hours, minutes, rest) : String(format: "%d:%02d", minutes, rest)
    }
}

/// A finished hand-over in the thread, where it ended: "Done: <its first line>" (or why it
/// stopped). Tap opens the result.
struct RunOutcomeRow: View {
    @Environment(\.chatBubbleWidth) private var bubbleWidth
    let run: AgentStore.Run
    let onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                Image(systemName: symbol)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(run.failure == nil ? DS.Palette.success : DS.Palette.inkTertiary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(run.taskTitle)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .lineLimit(1)
                    Text(line)
                        .font(DS.Typography.callout)
                        .foregroundStyle(DS.Palette.ink)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(DS.Palette.inkTertiary)
            }
            // In Omi's column, in the bubbles' family: their radius and fill, as wide as one.
            .padding(.horizontal, 14)
            .padding(.vertical, DS.Spacing.sm + 1)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.bubble, style: .continuous))
            .frame(maxWidth: bubbleWidth, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("chat.runOutcome.\(run.id)")
    }

    private var symbol: String {
        run.failure == nil ? "checkmark.circle.fill" : "pause.circle"
    }

    private var line: String {
        switch run.state {
        case let .done(result): L("nativeChatRunDone", Self.firstLine(result))
        case let .failed(code): AgentWording.failure(code)
        case .starting, .working: ""
        }
    }

    /// The result's first real line, without Markdown marks.
    static func firstLine(_ text: String) -> String {
        let line = text.split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .first { !$0.isEmpty && !$0.allSatisfy { "#-*_>".contains($0) } } ?? ""
        return line.trimmingCharacters(in: CharacterSet(charactersIn: "#*_> -")).replacingOccurrences(of: "**", with: "")
    }
}
